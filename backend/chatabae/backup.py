"""Consistent local snapshots and verified offline restoration (no model copies)."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import load_settings


def sha256(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def remove_owned(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if path.parent != root or not path.name.startswith(("daily-", "weekly-", ".partial-")):
        raise ValueError("Refusing to remove a path outside the backup directory")
    shutil.rmtree(path)


def snapshot(data_dir: Path, *, weekly=False) -> Path:
    data_dir = Path(data_dir).resolve()
    backup_root = data_dir / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    needed = (data_dir / "chatabae.sqlite3").stat().st_size + sum(p.stat().st_size for p in (data_dir / "media").glob("*") if p.is_file())
    if shutil.disk_usage(data_dir).free < needed + 512 * 1024 * 1024:
        raise RuntimeError("Insufficient free space for a complete snapshot")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = backup_root / (("weekly-" if weekly else "daily-") + stamp + "-" + uuid.uuid4().hex[:8])
    work = backup_root / (".partial-" + uuid.uuid4().hex)
    work.mkdir()
    try:
        source = sqlite3.connect(str(data_dir / "chatabae.sqlite3"), timeout=30)
        copied = sqlite3.connect(str(work / "chatabae.sqlite3"))
        with source, copied:
            source.backup(copied)
            assets = copied.execute("SELECT filename FROM assets").fetchall()
            integrity = copied.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError("Database integrity check failed")
        source.close()
        copied.close()
        media = work / "media"
        media.mkdir()
        files = [work / "chatabae.sqlite3"]
        for (filename,) in assets:
            if not re.fullmatch(r"[a-f0-9-]{36}\.(png|wav)", filename):
                raise ValueError("Invalid media reference in database")
            original = (data_dir / "media" / filename).resolve()
            if original.parent != (data_dir / "media").resolve() or not original.is_file():
                raise RuntimeError("Media changed during snapshot; retry later")
            destination = media / filename
            shutil.copyfile(original, destination)
            files.append(destination)
        manifest = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "files": [{"path": p.relative_to(work).as_posix(), "size_bytes": p.stat().st_size, "sha256": sha256(p)} for p in files]}
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        work.rename(target)
        for prefix, retained in (("daily-", 7), ("weekly-", 4)):
            candidates = sorted([p for p in backup_root.iterdir() if p.is_dir() and p.name.startswith(prefix) and (p / "manifest.json").is_file()], key=lambda p: (p / "manifest.json").stat().st_mtime_ns, reverse=True)
            for expired in candidates[retained:]:
                remove_owned(expired, backup_root)
        return target
    except BaseException:
        if work.exists():
            remove_owned(work, backup_root)
        raise


def verify(path: Path):
    path = Path(path).resolve()
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError("Unsupported backup manifest")
    found = set()
    for entry in manifest["files"]:
        name = entry["path"]
        if name != "chatabae.sqlite3" and not re.fullmatch(r"media/[a-f0-9-]{36}\.(png|wav)", name):
            raise ValueError("Invalid path in backup manifest")
        item = (path / name).resolve()
        if not item.is_relative_to(path) or not item.is_file() or item.stat().st_size != entry["size_bytes"] or sha256(item) != entry["sha256"]:
            raise ValueError("Backup checksum verification failed")
        found.add(name)
    if "chatabae.sqlite3" not in found:
        raise ValueError("Backup database is missing")
    with sqlite3.connect(str(path / "chatabae.sqlite3")) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup database is corrupt")
        expected = {"media/" + row[0] for row in db.execute("SELECT filename FROM assets")}
        if expected != found - {"chatabae.sqlite3"}:
            raise ValueError("Database/media manifest mismatch")
    return manifest


def process_alive(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def restore(path: Path, data_dir: Path):
    path, data_dir = Path(path).resolve(), Path(data_dir).resolve()
    verify(path)
    marker = data_dir / "runtime/backend.pid"
    if marker.is_file() and process_alive(json.loads(marker.read_text())["pid"]):
        raise RuntimeError("Stop Chatabae before restoring a snapshot")
    data_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    staged_db = data_dir / (".restore-" + suffix + ".sqlite3")
    staged_media = data_dir / (".restore-media-" + suffix)
    shutil.copyfile(path / "chatabae.sqlite3", staged_db)
    shutil.copytree(path / "media", staged_media)
    with sqlite3.connect(str(staged_db)) as db:
        db.execute("UPDATE auth_sessions SET revoked=1")
        db.execute("DELETE FROM auth_codes")
        db.execute("UPDATE jobs SET status='failed', error='Interrupted by backup restore' WHERE status IN ('queued','running')")
        db.commit()
    db.close()
    # Keep the previous database/media recoverable. Models/tools/backups remain untouched.
    current_db = data_dir / "chatabae.sqlite3"
    current_media = data_dir / "media"
    if current_db.exists():
        current_db.rename(data_dir / ("chatabae.pre-restore-" + suffix + ".sqlite3"))
    if current_media.exists():
        current_media.rename(data_dir / ("media.pre-restore-" + suffix))
    for sidecar in (data_dir / "chatabae.sqlite3-wal", data_dir / "chatabae.sqlite3-shm"):
        if sidecar.parent.resolve() != data_dir:
            raise ValueError("Invalid database sidecar path")
        sidecar.unlink(missing_ok=True)
    staged_db.rename(current_db)
    staged_media.rename(current_media)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify", "restore"])
    parser.add_argument("snapshot", nargs="?")
    parser.add_argument("--data-dir")
    args = parser.parse_args()
    data_dir = Path(args.data_dir) if args.data_dir else load_settings().data_dir
    if args.action == "create":
        print(snapshot(data_dir))
    elif args.action == "verify":
        if not args.snapshot:
            parser.error("snapshot path required")
        verify(Path(args.snapshot))
        print("Snapshot verified")
    else:
        if not args.snapshot:
            parser.error("snapshot path required")
        restore(Path(args.snapshot), data_dir)
        print("Snapshot restored; all sessions revoked. Sign in again.")


if __name__ == "__main__":
    main()
