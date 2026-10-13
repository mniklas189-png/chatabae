"""Download and verify only the pinned core artifacts needed by this installation."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import time
import urllib.request
import zipfile
from pathlib import Path

ARTIFACTS = {
    "node": ("https://nodejs.org/dist/v24.21.0/node-v24.21.0-win-x64.zip",
             "158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541", None),
    "llama": ("https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-win-cuda-12.4-x64.zip",
              "dd6df685c1024e6aa55ca55ad35038692d5e284d4dc895e7a646c3245d3d14ff", 264478423),
    "cuda": ("https://github.com/ggml-org/llama.cpp/releases/download/b11429/cudart-llama-bin-win-cuda-12.4-x64.zip",
             "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6", 391443627),
    "chat": ("https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/3885219b6810b007914f3a7950a8d1b469d598a5/Qwen3.5-9B-Q4_K_M.gguf",
             "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8", 5680522464),
    "vision": ("https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/3885219b6810b007914f3a7950a8d1b469d598a5/mmproj-F16.gguf",
               "f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f", 918166080),
}


def data_directory() -> Path:
    marker = Path(__file__).resolve().parents[1] / "config/local.json"
    if marker.is_file() and not os.environ.get("CHATABAE_DATA_DIR"):
        return Path(json.loads(marker.read_text(encoding="utf-8"))["data_dir"])
    base = Path.home() / "AppData/Local" if os.name == "nt" else Path.home() / ".local/share"
    return Path(os.environ.get("CHATABAE_DATA_DIR") or (base / "Chatabae"))


def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def download_ranges(name: str, directory: Path) -> Path:
    """Resume a slow release download with eight bounded, verified byte ranges."""
    url, expected, size = ARTIFACTS[name]
    target = directory / url.rsplit("/", 1)[-1]
    partial = target.with_suffix(target.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > size:
        partial.unlink()
        offset = 0
    ranges = []
    stride = 16 * 1024 * 1024
    for start in range(offset, size, stride):
        end = min(start + stride, size) - 1
        ranges.append((start, end, directory / f"{target.name}.range-{start}-{end}"))
    def piece(spec):
        start, end, path = spec
        count = path.stat().st_size if path.exists() else 0
        if count > end - start + 1:
            path.unlink()
            count = 0
        if count == end - start + 1:
            return path
        for attempt in range(4):
            count = path.stat().st_size if path.exists() else 0
            request = urllib.request.Request(url, headers={"User-Agent": "Chatabae-Setup/1.0", "Range": f"bytes={start + count}-{end}"})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    content_range = response.headers.get("Content-Range", "")
                    if response.status != 206 or content_range != f"bytes {start + count}-{end}/{size}":
                        raise RuntimeError("Server returned an unexpected byte range")
                    with path.open("ab") as output:
                        while block := response.read(min(1024 * 1024, end - start + 1 - count)):
                            output.write(block)
                            count += len(block)
                            if count > end - start + 1:
                                raise RuntimeError("Oversized response")
                if count != end - start + 1:
                    raise RuntimeError("Incomplete byte range")
                return path
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("range download failed")
    print(f"{name}: resume {offset // 1048576} MiB; {len(ranges)} bounded release ranges", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(piece, spec): spec for spec in ranges}
        complete = offset
        for task in concurrent.futures.as_completed(futures):
            task.result()
            start, end, _ = futures[task]
            complete += end - start + 1
            print(f"{name}: {complete // 1048576}/{size // 1048576} MiB", flush=True)
    with partial.open("ab") as output:
        for _, _, path in ranges:
            with path.open("rb") as source:
                while block := source.read(4 * 1024 * 1024):
                    output.write(block)
    if partial.stat().st_size != size or file_hash(partial) != expected:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"{name}: checksum failed after range assembly")
    partial.replace(target)
    for _, _, path in ranges:
        path.unlink(missing_ok=True)
    print(f"{name}: SHA-256 verified", flush=True)
    return target


def download(name: str, directory: Path) -> Path:
    url, expected, size = ARTIFACTS[name]
    filename = url.rsplit("/", 1)[-1]
    target = directory / filename
    directory.mkdir(parents=True, exist_ok=True)
    if name in {"chat", "vision"}:
        installed = directory.parent / "models" / filename
        if installed.is_file() and installed.stat().st_size == size and file_hash(installed) == expected:
            print(f"{name}: verified installed model (no duplicate download)", flush=True)
            duplicate_partial = target.with_suffix(target.suffix + ".part")
            if duplicate_partial.parent.resolve() == directory.resolve():
                duplicate_partial.unlink(missing_ok=True)
            return installed
    if target.exists() and (size is None or target.stat().st_size == size) and file_hash(target) == expected:
        print(f"{name}: verified existing file", flush=True)
        return target
    if name in {"llama", "cuda"}:
        return download_ranges(name, directory)
    partial = target.with_suffix(target.suffix + ".part")
    for attempt in range(4):
        offset = partial.stat().st_size if partial.exists() else 0
        request = urllib.request.Request(url, headers={"User-Agent": "Chatabae-Setup/1.0", **({"Range": f"bytes={offset}-"} if offset else {})})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                resumed = offset > 0 and response.status == 206
                if not resumed:
                    offset = 0
                digest = hashlib.sha256()
                if resumed:
                    with partial.open("rb") as existing:
                        for block in iter(lambda: existing.read(8 * 1024 * 1024), b""):
                            digest.update(block)
                print(f"{name}: downloading {filename}" + (f" (resume {offset // 1048576} MiB)" if resumed else ""), flush=True)
                last_report = time.monotonic()
                with partial.open("ab" if resumed else "wb") as output:
                    while block := response.read(4 * 1024 * 1024):
                        output.write(block)
                        digest.update(block)
                        offset += len(block)
                        if time.monotonic() - last_report >= 30:
                            print(f"{name}: {offset // 1048576} MiB", flush=True)
                            last_report = time.monotonic()
            if size is not None and offset != size:
                raise RuntimeError(f"{name}: expected {size} bytes, received {offset}")
            if digest.hexdigest() != expected:
                partial.unlink(missing_ok=True)
                raise RuntimeError(f"{name}: checksum verification failed")
            partial.replace(target)
            print(f"{name}: SHA-256 verified", flush=True)
            return target
        except Exception as exc:
            if attempt == 3:
                raise
            print(f"{name}: retry {attempt + 1}: {type(exc).__name__}", flush=True)
            time.sleep(2 ** attempt)
    raise RuntimeError("download failed")


def extract_verified(archive: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            resolved = (destination / member.filename).resolve()
            if not resolved.is_relative_to(destination.resolve()):
                raise ValueError("Archive contains an unsafe path")
        source.extractall(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["node", "models", "runtime", "all"], default="all")
    parser.add_argument("--data-dir", type=Path, default=data_directory())
    args = parser.parse_args()
    names = {"node": ["node"], "models": ["chat", "vision"], "runtime": ["llama", "cuda"], "all": list(ARTIFACTS)}[args.only]
    downloads = args.data_dir / "downloads"
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        tasks = {pool.submit(download, name, downloads): name for name in names}
        files = {}
        for task in concurrent.futures.as_completed(tasks):
            files[tasks[task]] = task.result()
    for name, archive in files.items():
        if name == "node":
            extract_verified(archive, args.data_dir / "runtimes")
        elif name in ("llama", "cuda"):
            extract_verified(archive, args.data_dir / "tools" / "llama")
        elif name in ("chat", "vision"):
            models = args.data_dir / "models"
            models.mkdir(parents=True, exist_ok=True)
            target = models / archive.name
            if not target.exists():
                archive.replace(target)
    print(json.dumps({"data_dir": str(args.data_dir), "installed": names}), flush=True)


if __name__ == "__main__":
    main()
