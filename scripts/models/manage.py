"""Explicit, revision-pinned downloads. Starting Chatabae never calls this script."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HF = "https://huggingface.co"
QWEN = "unsloth/Qwen3.5-9B-GGUF/resolve/3885219b6810b007914f3a7950a8d1b469d598a5"
HUIHUI = "mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF/resolve/9f646d7eda193ddf2348134f3bff3d49eed7a2c6"
PIPER = "rhasspy/piper-voices/resolve/c10ece1aade47bb51c153c893d14e5bf8e5b7117/de/de_DE/kerstin/low"
XTTS = "coqui/XTTS-v2/resolve/6c2b0d75eae4b7047358e3b6bd9325f857d43f77"
KOKORO_REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"
KOKORO = f"hexgrad/Kokoro-82M/resolve/{KOKORO_REVISION}"
LLAMA = "https://github.com/ggml-org/llama.cpp/releases/download/b11429"

ASSETS = {
    "chat": (f"{HF}/{HUIHUI}/Huihui-Qwen3.5-9B-abliterated.Q4_K_M.gguf", "data/models/Huihui-Qwen3.5-9B-abliterated.Q4_K_M.gguf", 5627045248, "ea1858ef4dc4b648b8dbb44612962a0333e945060dd0545ac0f28d7c4416e4b3"),
    "mmproj": (f"{HF}/{HUIHUI}/Huihui-Qwen3.5-9B-abliterated.mmproj-f16.gguf", "data/models/Huihui-Qwen3.5-9B-abliterated.mmproj-f16.gguf", 918166016, "56f07ff42fc9ab24fc06a93dce5a48fb2dbe08bff1a1c6e519d50af450820148"),
    "moderation_chat": (f"{HF}/{QWEN}/Qwen3.5-9B-Q4_K_M.gguf", "data/models/Qwen3.5-9B-Q4_K_M.gguf", 5680522464, "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8"),
    "moderation_mmproj": (f"{HF}/{QWEN}/mmproj-F16.gguf", "data/models/mmproj-F16.gguf", 918166080, "f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f"),
    "llama": (f"{LLAMA}/llama-b11429-bin-win-cuda-12.4-x64.zip", "tools/downloads/llama-b11429-cuda12.4.zip", 264478423, "dd6df685c1024e6aa55ca55ad35038692d5e284d4dc895e7a646c3245d3d14ff"),
    "llama_cuda": (f"{LLAMA}/cudart-llama-bin-win-cuda-12.4-x64.zip", "tools/downloads/cudart-b11429-cuda12.4.zip", 391443627, "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6"),
    "piper_kerstin": (f"{HF}/{PIPER}/de_DE-kerstin-low.onnx", "data/models/piper/de_DE-kerstin-low.onnx", 63104526, "d352a7641892cebf2903859af94e9ba81a141110215fe3943bcda7f7da401b7a"),
    "piper_kerstin_config": (f"{HF}/{PIPER}/de_DE-kerstin-low.onnx.json", "data/models/piper/de_DE-kerstin-low.onnx.json", 4158, "56e708556b7b9b7a53c4f8957e021421e69f11a600962bba554cffbe72cf2d47"),
    "piper_kerstin_card": (f"{HF}/{PIPER}/MODEL_CARD", "data/models/piper/kerstin_MODEL_CARD", 272, "7019006374a5fe5358186d5f3333e9f904385e7bdfbb68bc85dafce1a3cddae5"),
    "kokoro": (f"{HF}/{KOKORO}/kokoro-v1_0.pth", "data/models/kokoro/kokoro-v1_0.pth", 327212226, "496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4"),
    "kokoro_config": (f"{HF}/{KOKORO}/config.json", "data/models/kokoro/config.json", 2351, "5abb01e2403b072bf03d04fde160443e209d7a0dad49a423be15196b9b43c17f"),
    "kokoro_heart": (f"{HF}/{KOKORO}/voices/af_heart.pt", "data/models/kokoro/voices/af_heart.pt", 523425, "0ab5709b8ffab19bfd849cd11d98f75b60af7733253ad0d67b12382a102cb4ff"),
    "kokoro_michael": (f"{HF}/{KOKORO}/voices/am_michael.pt", "data/models/kokoro/voices/am_michael.pt", 523435, "9a443b79a4b22489a5b0ab7c651a0bcd1a30bef675c28333f06971abbd47bd37"),
    "kokoro_bella": (f"{HF}/{KOKORO}/voices/af_bella.pt", "data/models/kokoro/voices/af_bella.pt", 523425, "8cb64e02fcc8de0327a8e13817e49c76c945ecf0052ceac97d3081480e8e48d6"),
    "kokoro_adam": (f"{HF}/{KOKORO}/voices/am_adam.pt", "data/models/kokoro/voices/am_adam.pt", 523420, "ced7e284aba12472891be1da3ab34db84cc05cc02b5889535796dbf2d8b0cb34"),
    "xtts": (f"{HF}/{XTTS}/model.pth", "data/models/xtts/model.pth", 1867929118, "c7ea20001c6a0a841c77e252d8409f6a74fb423e79b3206a0771ba5989776187"),
    "xtts_speakers": (f"{HF}/{XTTS}/speakers_xtts.pth", "data/models/xtts/speakers_xtts.pth", 7754818, "f0f6137c19a4eab0cbbe4c99b5babacf68b1746e50da90807708c10e645b943b"),
    "xtts_config": (f"{HF}/{XTTS}/config.json", "data/models/xtts/config.json", 4368, "ef262b1454dd2a77e1461b0b2cd53e19b8a7624cc131b837d36df67356bc75e8"),
    "xtts_vocab": (f"{HF}/{XTTS}/vocab.json", "data/models/xtts/vocab.json", 361219, "928260878a59da8a72a2a5b7687fea29d5106137669d90945430fe17e415304a"),
    "xtts_license": (f"{HF}/{XTTS}/LICENSE.txt", "data/models/xtts/LICENSE.txt", 4014, "190f6d7c19b8984f91b97712b94ce92d2b2e640fc677dacab966e955ece9d043"),
}


def read_installed_config(data_dir: Path | None = None) -> dict:
    """Read the installation marker and its real config, without logging credentials."""
    marker = ROOT / "config/local.json"
    marker_data = json.loads(marker.read_text(encoding="utf-8-sig")) if marker.is_file() else {}
    selected = Path(data_dir or marker_data.get("data_dir") or Path.home() / "AppData/Local/Chatabae").expanduser().resolve()
    config = selected / "config.json"
    payload = json.loads(config.read_text(encoding="utf-8-sig")) if config.is_file() else dict(marker_data)
    payload["data_dir"] = str(selected)
    return payload


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def download(name: str, root: Path = ROOT) -> Path:
    url, relative, size, checksum = ASSETS[name]
    target = root / relative
    if target.is_file() and target.stat().st_size == size and digest(target) == checksum:
        print(f"{name}: verified existing {target}", flush=True)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    for attempt in range(3):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > size:
                partial.unlink()
                offset = 0
            if offset < size:
                request = urllib.request.Request(url, headers={"User-Agent": "Chatabae-explicit-setup/1", **({"Range": f"bytes={offset}-"} if offset else {})})
                with urllib.request.urlopen(request, timeout=60) as response:
                    resumed = offset and response.status == 206
                    if resumed and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise RuntimeError("Unexpected download range; refusing corrupt resume")
                    if not resumed:
                        offset = 0
                    with partial.open("ab" if resumed else "wb") as output:
                        last = 0.0
                        for block in iter(lambda: response.read(4 * 1024 * 1024), b""):
                            output.write(block)
                            offset += len(block)
                            if offset > size:
                                raise RuntimeError("Download exceeds pinned size")
                            if time.monotonic() - last >= 5:
                                print(f"{name}: {offset}/{size} bytes ({offset / size:.1%})", flush=True)
                                last = time.monotonic()
            if partial.stat().st_size != size:
                raise RuntimeError("Incomplete download")
            if digest(partial) != checksum:
                partial.unlink()
                raise RuntimeError("SHA256 mismatch")
            os.replace(partial, target)
            print(f"{name}: SHA256 verified", flush=True)
            return target
        except (OSError, RuntimeError) as exc:
            print(f"{name}: attempt {attempt + 1} failed: {exc}", file=sys.stderr, flush=True)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Download failed")


def extract_llama(root: Path) -> None:
    destination = (root / "tools/llama").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for key in ("llama", "llama_cuda"):
        archive = download(key, root)
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                candidate = (destination / member.filename).resolve()
                if not candidate.is_relative_to(destination) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise RuntimeError("Unsafe archive member")
            package.extractall(destination)
    binaries = list(destination.rglob("llama-server.exe"))
    if not binaries:
        raise RuntimeError("Archive contains no llama-server.exe")
    print(f"llama_cpp_executable={binaries[0]}", flush=True)


def ensure_kokoro(root: Path = ROOT, *, download_missing: bool = False) -> dict:
    """Prefer the existing immutable HF snapshot; fetching requires an explicit flag."""
    cached = Path.home() / ".cache/huggingface/hub/models--hexgrad--Kokoro-82M/snapshots" / KOKORO_REVISION
    local = root / "data/models/kokoro"
    required = ("config.json", "kokoro-v1_0.pth", "voices/af_heart.pt", "voices/am_michael.pt")
    for directory in (cached, local):
        if all((directory / relative).is_file() for relative in required):
            return {"kokoro_model": str(directory), "kokoro_voices": str(directory / "voices"), "source": "existing", "revision": KOKORO_REVISION}
    if not download_missing:
        raise RuntimeError("Kokoro weights are absent. Explicit model setup can download the pinned assets.")
    for asset in ("kokoro", "kokoro_config", "kokoro_heart", "kokoro_michael"):
        download(asset, root)
    return {"kokoro_model": str(local), "kokoro_voices": str(local / "voices"), "source": "downloaded", "revision": KOKORO_REVISION}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "download", "extract-llama", "prepare-kokoro"))
    parser.add_argument("assets", nargs="*", choices=tuple(ASSETS))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.command == "extract-llama":
        extract_llama(args.root)
    elif args.command == "prepare-kokoro":
        print(json.dumps(ensure_kokoro(args.root, download_missing=True)), flush=True)
    elif args.command == "download":
        if not args.assets:
            parser.error("Choose assets explicitly; optional XTTS is never downloaded implicitly")
        for name in args.assets:
            download(name, args.root)
    else:
        rows = []
        for name, (url, relative, size, checksum) in ASSETS.items():
            path = args.root / relative
            present = path.is_file() and path.stat().st_size == size
            rows.append({"id": name, "path": str(path), "url": url, "bytes": size, "sha256": checksum, "present": present, "verified": bool(present and args.verify and digest(path) == checksum)})
        print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
