from __future__ import annotations

import hashlib
import io
import re
import shutil
import time
import wave
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import LargeBinary, cast, func, select

from .db import Asset, Character, Conversation, Memory, Message, uid


def storage_check(rt, db, user_id, incoming=0):
    if shutil.disk_usage(rt.settings.data_dir).free - incoming < rt.settings.limits.disk_reserve_bytes:
        raise HTTPException(507, "Server storage reserve reached")
    def metadata_size(owner=None):
        total = 0
        for model, column in ((Character, Character.profile), (Character, Character.description), (Message, Message.content), (Memory, Memory.content), (Conversation, Conversation.summary)):
            query = select(func.coalesce(func.sum(func.length(cast(column, LargeBinary))), 0))
            if owner:
                query = query.where(model.user_id == owner)
            total += db.scalar(query) or 0
        return total
    used = (db.scalar(select(func.coalesce(func.sum(Asset.size_bytes), 0)).where(Asset.user_id == user_id)) or 0) + metadata_size(user_id)
    if used + incoming > rt.settings.limits.user_storage_bytes:
        raise HTTPException(413, "Account storage limit reached")
    total = (db.scalar(select(func.coalesce(func.sum(Asset.size_bytes), 0))) or 0) + metadata_size()
    if total + incoming > rt.settings.limits.global_storage_bytes:
        raise HTTPException(507, "Global media storage limit reached")


def normalized_image(data: bytes, max_pixels: int) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                raise ValueError("Only still JPEG, PNG and WebP images are accepted")
            if image.width * image.height > max_pixels:
                raise ValueError("Image dimensions exceed the limit")
            image.load()
            image = image.convert("RGB")
            image.thumbnail((1536, 1536))
            buffer = io.BytesIO()
            # Creating a fresh image strips metadata, trailing payloads and original filenames.
            image.save(buffer, "PNG")
            return buffer.getvalue()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Invalid image: " + str(exc)) from None


def adopt(rt, db, user_id: str, source: Path | bytes, kind: str, *, character_id=None, conversation_id=None, message_id=None, metadata=None):
    data = source if isinstance(source, bytes) else Path(source).read_bytes()
    if len(data) > 32 * 1024 * 1024:
        raise HTTPException(413, "Generated media exceeds the limit")
    if kind == "image":
        data = normalized_image(data, rt.settings.limits.image_pixels)
        if metadata is not None:
            with Image.open(io.BytesIO(data)) as saved:
                metadata = {**metadata, "width": saved.width, "height": saved.height}
        suffix, mime = ".png", "image/png"
    else:
        try:
            with wave.open(io.BytesIO(data), "rb") as audio:
                if audio.getframerate() <= 0 or audio.getnchannels() not in {1, 2} or audio.getnframes() / audio.getframerate() > 300:
                    raise ValueError("Invalid audio length")
        except (wave.Error, ValueError, EOFError):
            raise HTTPException(422, "Provider returned invalid WAV audio") from None
        suffix, mime = ".wav", "audio/wav"
    storage_check(rt, db, user_id, len(data))
    asset_id = uid()
    filename = asset_id + suffix
    target = rt.settings.media_dir / filename
    target.write_bytes(data)
    # Session close/rollback removes files whose database ownership never committed.
    db.info.setdefault("new_media_files", []).append(target)
    asset = Asset(id=asset_id, user_id=user_id, character_id=character_id, conversation_id=conversation_id, message_id=message_id, kind=kind, filename=filename, mime_type=mime, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), generation_metadata=metadata)
    db.add(asset)
    db.flush()
    if isinstance(source, Path):
        resolved = source.resolve()
        owned_output = (rt.settings.data_dir / "runtime/models/output").resolve()
        if resolved.is_relative_to(owned_output):
            resolved.unlink(missing_ok=True)
    return asset


def asset_path(rt, asset):
    target = (rt.settings.media_dir / asset.filename).resolve()
    if target.parent != rt.settings.media_dir.resolve() or not target.is_file():
        raise HTTPException(404, "Asset missing")
    return target


def cleanup_orphans(rt):
    """Delete stale application-owned intermediates; live/reference files remain untouched."""
    cutoff = time.time() - max(3600, rt.settings.limits.heavy_timeout * 2)
    with rt.db.sessions() as db:
        referenced = set(db.scalars(select(Asset.filename)).all())
    data_root = rt.settings.data_dir.resolve()
    media_root = rt.settings.media_dir.resolve()
    output_root = (data_root / "runtime/models/output").resolve()
    removed = 0
    for root, intermediate in ((media_root, False), (output_root, True)):
        if not root.is_relative_to(data_root) or not root.exists():
            continue
        candidates = root.rglob("*") if intermediate else root.iterdir()
        for candidate in candidates:
            path = candidate.resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.stat().st_mtime >= cutoff:
                continue
            relative = path.relative_to(root)
            owned = ((relative.parts[0] == "chatabae" and path.suffix == ".png") or re.fullmatch(r"speech_[a-f0-9]{32}\.wav", path.name)) if intermediate else bool(re.fullmatch(r"[a-f0-9-]{36}\.(png|wav)", path.name)) and path.name not in referenced
            if owned:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    # A served file can still be open on Windows; retry on a later sweep.
                    continue
    return removed
