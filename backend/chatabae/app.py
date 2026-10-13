from __future__ import annotations

import asyncio
import json
import secrets
import time
import io
import wave
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, or_, select

from .auth import current_user, make_auth_router, reserve_quota, user_json
from .body_limit import BodyLimitMiddleware
from .config import Settings, load_settings
from .db import Asset, AuthSession, Character, Conversation, Favorite, Job, JobEvent, Memory, Message, Report, User
from .jobs import Runtime, TERMINAL, UnavailableProviders, XTTS_LICENSE, asset_json, character_json, job_json, message_json, public_snapshot, timestamp
from .intent import explicit_image_request
from .media import adopt, asset_path, storage_check
from .schemas import AssetResponse, BranchInput, CharacterInput, CharacterResponse, CharacterPatch, ConversationCreate, ConversationInput, ConversationResponse, ImageRequest, JobResponse, MemoryInput, MemoryResponse, MessageResponse, AdultContent, AvatarRequest, GroupConversationCreate, ProfileGeneration, ProfileImprovement, ProfileRequest, Regenerate, ReportInput, SpeechRequest, TextUpdate, Turn, TurnResponse, UserResponse


def owned(db, model, identifier, user):
    record = db.get(model, identifier)
    if record is None or record.user_id != user.id:
        raise HTTPException(404, "Not found")
    return record


def readable_char(db, identifier, user=None):
    char = db.get(Character, identifier)
    if not char:
        raise HTTPException(404, "Character not found")
    if user and char.user_id == user.id:
        return char, False
    owner = db.get(User, char.user_id)
    if char.visibility != "public" or not char.approved_snapshot or not owner or owner.banned:
        raise HTTPException(404, "Character not found")
    return char, True


def conversation_json(c):
    return {"id": c.id, "character_id": c.character_id, "character_ids": c.member_ids or [c.character_id], "title": c.title, "parent_id": c.parent_id, "branch_message_id": c.branch_message_id, "created_at": timestamp(c.created_at), "updated_at": timestamp(c.updated_at)}


def memory_json(m):
    return {"id": m.id, "conversation_id": m.conversation_id, "character_id": m.character_id, "content": m.content, "enabled": m.enabled, "automatic": m.automatic, "source_message_id": m.source_message_id, "created_at": timestamp(m.created_at)}


def create_app(settings: Settings | None = None, providers=None) -> FastAPI:
    settings = settings or load_settings()
    rt = Runtime(settings, providers)

    @asynccontextmanager
    async def lifespan(app):
        await rt.start()
        try:
            yield
        finally:
            await rt.stop()

    app = FastAPI(title="Chatabae API", version="0.1.0", lifespan=lifespan, docs_url="/docs" if settings.mode == "local" else None, redoc_url=None)
    app.state.runtime = rt
    app.add_middleware(BodyLimitMiddleware, upload_bytes=settings.limits.upload_bytes, voice_upload_bytes=settings.limits.voice_upload_bytes)
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "Last-Event-ID"], expose_headers=["Retry-After"])
    app.include_router(make_auth_router())

    @app.middleware("http")
    async def guards(request, call_next):
        size = request.headers.get("content-length")
        upload_limit = settings.limits.voice_upload_bytes if request.url.path == "/api/v1/voice-references" else settings.limits.upload_bytes
        limit = upload_limit + 1024 * 1024 if "multipart/form-data" in request.headers.get("content-type", "") else 128 * 1024
        if size:
            try:
                if int(size) > limit or int(size) < 0:
                    return JSONResponse({"detail": "Request body too large"}, 413)
            except ValueError:
                return JSONResponse({"detail": "Invalid content length"}, 400)
        if request.url.path.startswith("/api/v1/") and request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.startswith("/api/v1/auth/"):
            try:
                user = current_user(request)
                async with rt.admission_lock:
                    with rt.db.sessions() as db:
                        if request.method != "DELETE":
                            storage_check(rt, db, user.id)
                        reserve_quota(db, f"writes:{user.id}", 60, 60)
                        db.commit()
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, exc.status_code, headers=exc.headers)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    @app.get("/api/v1/status")
    async def status():
        with rt.db.sessions() as db:
            queued = db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued"))
            running = db.scalar(select(func.count()).select_from(Job).where(Job.status == "running"))
        raw = rt.providers.status()
        capabilities = {}
        for key, values in raw.items():
            if isinstance(values, dict):
                capabilities[key] = {name: value for name, value in values.items() if name in {"available", "ready", "enabled", "vision_available", "public_allowed", "device", "languages", "voices"}}
                if not values.get("available"):
                    capabilities[key]["reason"] = "This local capability is unavailable; check the operator dashboard."
        return {"state": rt.state, "online": rt.state == "ready", "instance_id": settings.instance_id, "mode": settings.mode, "queue": {"queued": queued, "running": running, "capacity": settings.limits.queue_size, "active_gpu_kind": rt.active_gpu_kind}, "capabilities": capabilities, "public_images": settings.public_image_allowed, "xtts": settings.xtts_enabled}

    @app.get("/api/v1/voices")
    async def voices(request: Request):
        catalog = getattr(rt.providers, "voices", None)
        if catalog and not isinstance(rt.providers, UnavailableProviders):
            results = catalog()
            if request.headers.get("authorization"):
                user = current_user(request)
                with rt.db.sessions() as db:
                    refs = db.scalars(select(Asset).where(Asset.user_id == user.id, Asset.kind == "voice_reference")).all()
                    results.extend({"id": "xtts:ref:" + ref.id, "name": "Eigene Stimme " + ref.id[:8], "engine": "xtts", "language": "de", "gender": "unspecified", "available": settings.xtts_enabled, "reference_asset_id": ref.id} for ref in refs)
            return results
        model_paths = settings.model_paths
        return [
            {"id": "kokoro:af_heart", "name": "Heart", "language": "en", "gender": "female", "engine": "kokoro", "available": bool(model_paths.get("kokoro_model"))},
            {"id": "kokoro:am_michael", "name": "Michael", "language": "en", "gender": "male", "engine": "kokoro", "available": bool(model_paths.get("kokoro_model"))},
            {"id": "piper:de", "name": "Thorsten", "language": "de", "gender": "male", "engine": "piper", "available": bool(model_paths.get("piper_model"))},
            {"id": "piper:kerstin", "name": "Kerstin", "language": "de", "gender": "female", "engine": "piper", "available": bool(model_paths.get("piper_kerstin_model"))},
            {"id": "xtts:Ana Florence", "name": "Ana Florence · HQ", "language": "de", "gender": "female", "engine": "xtts", "available": settings.xtts_enabled and bool(model_paths.get("xtts_model_dir"))},
            {"id": "xtts:Craig Gutsy", "name": "Craig Gutsy · HQ", "language": "en", "gender": "male", "engine": "xtts", "available": settings.xtts_enabled and bool(model_paths.get("xtts_model_dir"))},
        ]

    @app.get("/api/v1/preferences")
    async def preferences(user: User = Depends(current_user)):
        return user.preferences

    @app.put("/api/v1/preferences")
    async def save_preferences(body: dict, user: User = Depends(current_user)):
        allowed = {"theme", "autoplay", "language", "voice", "speed", "volume"}
        if set(body) - allowed or len(json.dumps(body)) > 1000:
            raise HTTPException(422, "Invalid preferences")
        for key, low, high in (("speed", 0.7, 1.3), ("volume", 0, 1)):
            if key in body and (type(body[key]) not in {int, float} or not low <= body[key] <= high):
                raise HTTPException(422, f"{key} is outside the supported range")
        with rt.db.sessions() as db:
            live = db.get(User, user.id)
            live.preferences = body
            db.commit()
            return live.preferences

    @app.get("/api/v1/me")
    async def me(user: User = Depends(current_user)):
        return {"id": user.id, "username": user.username, "adult_content": user.adult_confirmed_at is not None, "preferences": user.preferences, "created_at": timestamp(user.created_at)}

    @app.put("/api/v1/me/adult-content", response_model=UserResponse)
    async def adult_content(body: AdultContent, user: User = Depends(current_user)):
        if body.enabled and not body.confirm_adult:
            raise HTTPException(422, "Confirm that you are at least 18 years old")
        with rt.db.sessions() as db:
            live = db.get(User, user.id)
            live.adult_confirmed_at = time.time() if body.enabled else None
            db.commit()
            return user_json(live)

    @app.patch("/api/v1/me")
    async def update_me(body: dict, user: User = Depends(current_user)):
        if set(body) != {"preferences"} or not isinstance(body["preferences"], dict):
            raise HTTPException(422, "Only preferences can be changed here")
        preferences = await save_preferences(body["preferences"], user)
        return {"id": user.id, "username": user.username, "preferences": preferences}

    def detach_from_groups(db, char, owner_only):
        """Drop a character from group chats; a group left with one member becomes a normal chat."""
        query = select(Conversation).where(Conversation.member_ids.is_not(None))
        query = query.where(Conversation.user_id == char.user_id) if owner_only else query.where(Conversation.user_id != char.user_id)
        for convo in db.scalars(query).all():
            if char.id not in (convo.member_ids or []):
                continue
            remaining = [member for member in convo.member_ids if member != char.id]
            if not remaining:
                continue
            convo.character_id = remaining[0]
            convo.member_ids = remaining if len(remaining) > 1 else None
        db.flush()

    def preserve_shared_conversations(db, char):
        # Removing one's profile must not erase another account's private chat history.
        detach_from_groups(db, char, owner_only=False)
        conversations = db.scalars(select(Conversation).where(Conversation.character_id == char.id, Conversation.user_id != char.user_id)).all()
        clones = {}
        snapshot = public_snapshot(char.approved_snapshot or {"name": "Removed character", "description": "This public character was removed", "profile": {"age": 18, "fictional": True}, "language": char.language, "voice": ""})
        for convo in conversations:
            if convo.user_id not in clones:
                clone = Character(user_id=convo.user_id, name=snapshot["name"], description=snapshot["description"], profile=snapshot["profile"], language=snapshot["language"], voice=snapshot["voice"], visibility="private", moderation_status="pending")
                db.add(clone)
                db.flush()
                clones[convo.user_id] = clone.id
            convo.character_id = clones[convo.user_id]
            for memory in db.scalars(select(Memory).where(Memory.conversation_id == convo.id)).all():
                memory.character_id = convo.character_id
            for asset in db.scalars(select(Asset).where(Asset.conversation_id == convo.id, Asset.user_id == convo.user_id)).all():
                asset.character_id = convo.character_id
        db.flush()

    @app.delete("/api/v1/me")
    async def delete_me(request: Request, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            rt.cancel_user_jobs(db, user.id)
            for char in db.scalars(select(Character).where(Character.user_id == user.id)).all():
                preserve_shared_conversations(db, char)
            filenames = db.scalars(select(Asset.filename).where(Asset.user_id == user.id)).all()
            db.delete(db.get(User, user.id))
            db.commit()
        for filename in filenames:
            path = (settings.media_dir / filename).resolve()
            if path.parent == settings.media_dir.resolve():
                path.unlink(missing_ok=True)
        return {"ok": True}

    @app.get("/api/v1/me/export")
    async def export_me(user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            return {"user": {"id": user.id, "username": user.username, "preferences": user.preferences, "adult_confirmed_at": timestamp(user.adult_confirmed_at)}, "characters": [character_json(c) for c in db.scalars(select(Character).where(Character.user_id == user.id)).all()], "conversations": [conversation_json(c) for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id)).all()], "messages": [message_json(db, m) for m in db.scalars(select(Message).where(Message.user_id == user.id)).all()], "memories": [memory_json(m) for m in db.scalars(select(Memory).where(Memory.user_id == user.id)).all()], "assets": [asset_json(a) for a in db.scalars(select(Asset).where(Asset.user_id == user.id)).all()]}

    @app.get("/api/v1/characters", response_model=list[CharacterResponse])
    async def list_characters(user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            return [character_json(c) for c in db.scalars(select(Character).where(Character.user_id == user.id).order_by(Character.updated_at.desc())).all()]

    @app.post("/api/v1/characters", status_code=201, response_model=CharacterResponse)
    async def add_character(body: CharacterInput, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            storage_check(rt, db, user.id)
            reserve_quota(db, f"profilechanges:{user.id}", settings.limits.profile_per_day, 86400)
            char = Character(user_id=user.id, **body.model_dump())
            db.add(char)
            db.flush()
            if char.visibility == "public":
                await rt.schedule_moderation(user.id, {"character_id": char.id, "revision": char.revision}, db=db)
            db.commit()
            return character_json(char)

    @app.post("/api/v1/characters/generate", status_code=202, response_model=JobResponse)
    async def generate_character(body: ProfileRequest, user: User = Depends(current_user)):
        return job_json(await rt.enqueue(user.id, "profile", body.model_dump()))

    @app.get("/api/v1/characters/{identifier}", response_model=CharacterResponse)
    async def get_character(identifier: str, request: Request):
        user = current_user(request) if request.headers.get("authorization") else None
        with rt.db.sessions() as db:
            char, public = readable_char(db, identifier, user)
            return character_json(char, public)

    @app.patch("/api/v1/characters/{identifier}", response_model=CharacterResponse)
    async def change_character(identifier: str, body: CharacterPatch, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            char = owned(db, Character, identifier, user)
            values = {"name": char.name, "description": char.description, "profile": char.profile, "language": char.language, "voice": char.voice, "visibility": char.visibility}
            updates = body.model_dump(exclude_unset=True)
            if body.profile is not None and set(body.profile) == {"generation_settings"}:
                updates["profile"] = {**char.profile, **body.profile}
            values.update(updates)
            try:
                verified = CharacterInput.model_validate(values)
            except ValidationError:
                raise HTTPException(422, "Character values are invalid") from None
            if char.visibility == "public" and verified.visibility == "private":
                preserve_shared_conversations(db, char)
            reserve_quota(db, f"profilechanges:{user.id}", settings.limits.profile_per_day, 86400)
            for key, value in verified.model_dump().items():
                setattr(char, key, value)
            char.revision += 1
            char.updated_at, char.moderation_status, char.moderation_reason = time.time(), "pending", ""
            if char.visibility == "public":
                await rt.schedule_moderation(user.id, {"character_id": char.id, "revision": char.revision}, db=db)
            else:
                char.approved_snapshot = None
                char.approved_internal = None
            db.commit()
            return character_json(char)

    @app.delete("/api/v1/characters/{identifier}")
    async def remove_character(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            char = owned(db, Character, identifier, user)
            preserve_shared_conversations(db, char)
            detach_from_groups(db, char, owner_only=True)
            paths = [a.filename for a in db.scalars(select(Asset).where(Asset.character_id == identifier)).all()]
            db.delete(char)
            db.commit()
        for filename in paths:
            (settings.media_dir / filename).unlink(missing_ok=True)
        return {"ok": True}

    @app.post("/api/v1/characters/{identifier}/copy", status_code=201, response_model=CharacterResponse)
    async def copy_character(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            source, public = readable_char(db, identifier, user)
            data = character_json(source, public)
            char = Character(user_id=user.id, name=data["name"], description=data["description"], profile=data["profile"], language=data["language"], voice=data["voice"], visibility="private")
            db.add(char)
            db.flush()
            if data.get("avatar_asset_id"):
                original = db.get(Asset, data["avatar_asset_id"])
                if original:
                    asset = adopt(rt, db, user.id, asset_path(rt, original), "image", character_id=char.id)
                    char.avatar_asset_id = asset.id
            db.commit()
            return character_json(char)

    @app.post("/api/v1/characters/{identifier}/moderate", status_code=202, response_model=JobResponse)
    async def moderate_character(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            char = owned(db, Character, identifier, user)
            return job_json(await rt.enqueue(user.id, "moderation", {"character_id": char.id, "revision": char.revision}, internal=True))

    @app.post("/api/v1/characters/{identifier}/improve", status_code=202, response_model=JobResponse)
    async def improve_character(identifier: str, body: ProfileImprovement, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            char = owned(db, Character, identifier, user)
            return job_json(await rt.enqueue(user.id, "profile_improve", {"character_id": char.id, "revision": char.revision, **body.model_dump()}))

    @app.post("/api/v1/characters/{identifier}/avatar", status_code=201, response_model=AssetResponse)
    async def avatar(identifier: str, file: UploadFile, user: User = Depends(current_user)):
        data = await file.read(settings.limits.upload_bytes + 1)
        await file.close()
        if len(data) > settings.limits.upload_bytes:
            raise HTTPException(413, "Upload too large")
        with rt.db.sessions() as db:
            char = owned(db, Character, identifier, user)
            asset = adopt(rt, db, user.id, data, "image", character_id=char.id)
            char.avatar_asset_id = asset.id
            char.revision += 1
            char.moderation_status = "pending"
            if char.visibility == "public":
                await rt.schedule_moderation(user.id, {"character_id": char.id, "revision": char.revision}, db=db)
            db.commit()
            return asset_json(asset)

    @app.get("/api/v1/library", response_model=list[CharacterResponse])
    async def library(q: str = "", limit: int = 50):
        if len(q) > 200:
            raise HTTPException(422, "Search query too long")
        with rt.db.sessions() as db:
            chars = db.scalars(select(Character).join(User, User.id == Character.user_id).where(Character.visibility == "public", Character.approved_snapshot.is_not(None), User.banned == False).order_by(Character.updated_at.desc()).limit(min(max(limit, 1), 100))).all()
            return [character_json(c, True) for c in chars if q.lower() in str(c.approved_snapshot).lower()]

    @app.post("/api/v1/characters/{identifier}/favorite")
    async def favorite(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            readable_char(db, identifier, user)
            if not db.get(Favorite, (user.id, identifier)):
                db.add(Favorite(user_id=user.id, character_id=identifier))
                db.commit()
        return {"ok": True}

    @app.delete("/api/v1/characters/{identifier}/favorite")
    async def unfavorite(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            item = db.get(Favorite, (user.id, identifier))
            if item:
                db.delete(item)
                db.commit()
        return {"ok": True}

    @app.get("/api/v1/favorites", response_model=list[CharacterResponse])
    @app.get("/api/v1/library/favorites", response_model=list[CharacterResponse])
    async def favorite_list(user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            ids = db.scalars(select(Favorite.character_id).where(Favorite.user_id == user.id)).all()
            results = []
            for identifier in ids:
                try:
                    char, public = readable_char(db, identifier, user)
                    results.append(character_json(char, public))
                except HTTPException:
                    pass
            return results

    @app.get("/api/v1/conversations", response_model=list[ConversationResponse])
    async def all_conversations(user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            return [conversation_json(c) for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())).all()]

    @app.get("/api/v1/characters/{identifier}/conversations", response_model=list[ConversationResponse])
    async def conversations(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            readable_char(db, identifier, user)
            return [conversation_json(c) for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id, Conversation.character_id == identifier).order_by(Conversation.updated_at.desc())).all()]

    @app.post("/api/v1/characters/{identifier}/conversations", status_code=201, response_model=ConversationResponse)
    async def add_conversation(identifier: str, body: ConversationInput, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            readable_char(db, identifier, user)
            convo = Conversation(user_id=user.id, character_id=identifier, title=body.title)
            db.add(convo)
            db.flush()
            db.commit()
            return conversation_json(convo)

    @app.post("/api/v1/group-conversations", status_code=201, response_model=ConversationResponse)
    async def add_group_conversation(body: GroupConversationCreate, user: User = Depends(current_user)):
        identifiers = list(dict.fromkeys(body.character_ids))
        if not 2 <= len(identifiers) <= 4:
            raise HTTPException(422, "A group chat needs two to four different characters")
        with rt.db.sessions() as db:
            names = [character_json(*readable_char(db, identifier, user))["name"] for identifier in identifiers]
            title = body.title.strip() or ", ".join(names)[:120]
            convo = Conversation(user_id=user.id, character_id=identifiers[0], member_ids=identifiers, title=title)
            db.add(convo)
            db.commit()
            return conversation_json(convo)

    @app.post("/api/v1/avatar-jobs", status_code=202, response_model=JobResponse)
    async def avatar_job(body: AvatarRequest, user: User = Depends(current_user)):
        profile = {"name": body.name, "description": body.description, "age": body.age if body.age is not None else 25, "gender": body.gender, "appearance": body.appearance, "fictional": True}
        prompt = "Portrait of this character, facing the viewer, suitable as a profile picture" + (". " + body.prompt.strip() if body.prompt.strip() else "")
        return job_json(await rt.enqueue(user.id, "image", {"avatar": profile, "prompt": prompt, "options": {"preset": "fast", "width": 1024, "height": 1024}}))

    @app.post("/api/v1/conversations", status_code=201, response_model=ConversationResponse)
    async def conversation_alias(body: ConversationCreate, user: User = Depends(current_user)):
        return await add_conversation(body.character_id, ConversationInput(title=body.title), user)

    @app.get("/api/v1/conversations/{identifier}", response_model=ConversationResponse)
    async def get_conversation(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            return conversation_json(owned(db, Conversation, identifier, user))

    @app.patch("/api/v1/conversations/{identifier}", response_model=ConversationResponse)
    async def change_conversation(identifier: str, body: ConversationInput, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            convo = owned(db, Conversation, identifier, user)
            convo.title, convo.updated_at = body.title, time.time()
            db.commit()
            return conversation_json(convo)

    @app.delete("/api/v1/conversations/{identifier}")
    async def delete_conversation(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            db.delete(owned(db, Conversation, identifier, user))
            db.commit()
        return {"ok": True}

    @app.get("/api/v1/conversations/{identifier}/messages", response_model=list[MessageResponse])
    async def messages(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            owned(db, Conversation, identifier, user)
            return [message_json(db, m) for m in db.scalars(select(Message).where(Message.conversation_id == identifier).order_by(Message.created_at)).all()]

    def character_generation(char, public=False):
        profile = character_json(char, public)["profile"]
        try:
            generation = ProfileGeneration.model_validate(profile.get("generation_settings", {})).model_dump()
        except ValidationError:
            generation = ProfileGeneration().model_dump()
        generation["max_tokens"] = min(generation["max_tokens"], settings.limits.max_output_tokens)
        return generation

    @app.post("/api/v1/conversations/{identifier}/messages", status_code=202, response_model=TurnResponse)
    async def add_message(identifier: str, body: Turn, user: User = Depends(current_user)):
        if len(body.content) > settings.limits.max_input_chars or ("generation" in body.model_fields_set and body.generation.max_tokens > settings.limits.max_output_tokens):
            raise HTTPException(422, "Generation settings exceed server limits")
        with rt.db.sessions() as db:
            convo = owned(db, Conversation, identifier, user)
            char, public = readable_char(db, convo.character_id, user)
            active = db.scalars(select(Job).where(Job.user_id == user.id, Job.kind.in_(["chat", "image"]), Job.status.in_(["queued", "running"]))).all()
            if any(job.payload.get("conversation_id") == identifier for job in active):
                raise HTTPException(409, "A turn is already running in this conversation")
            message = Message(user_id=user.id, conversation_id=identifier, role="user", content=body.content)
            db.add(message)
            db.flush()
            if explicit_image_request(body.content):
                job = await rt.enqueue(user.id, "image", {"conversation_id": identifier, "prompt": body.content, "options": {}}, db=db)
            else:
                generation = body.generation.model_dump() if "generation" in body.model_fields_set else character_generation(char, public)
                job = await rt.enqueue(user.id, "chat", {"conversation_id": identifier, "generation": generation}, db=db)
            convo.updated_at = time.time()
            db.commit()
            return {"message": message_json(db, message), "job": job_json(job)}

    def ensure_convo_idle(db, identifier):
        active = db.scalars(select(Job).where(Job.status.in_(["queued", "running"]))).all()
        if any(j.payload.get("conversation_id") == identifier for j in active):
            raise HTTPException(409, "Wait for or cancel the active generation first")

    def invalidate_derived(db, conversation_id):
        convo = db.get(Conversation, conversation_id)
        if convo:
            convo.summary = ""
        for memory in db.scalars(select(Memory).where(Memory.conversation_id == conversation_id, Memory.automatic == True)).all():
            db.delete(memory)

    @app.patch("/api/v1/messages/{identifier}", response_model=MessageResponse)
    async def change_message(identifier: str, body: TextUpdate, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            message = owned(db, Message, identifier, user)
            ensure_convo_idle(db, message.conversation_id)
            invalidate_derived(db, message.conversation_id)
            message.content, message.edited_at = body.content, time.time()
            db.commit()
            return message_json(db, message)

    @app.delete("/api/v1/messages/{identifier}")
    async def remove_message(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            message = owned(db, Message, identifier, user)
            ensure_convo_idle(db, message.conversation_id)
            invalidate_derived(db, message.conversation_id)
            db.delete(message)
            db.commit()
        return {"ok": True}

    @app.post("/api/v1/messages/{identifier}/regenerate", status_code=202, response_model=JobResponse)
    async def regenerate(identifier: str, body: Regenerate, user: User = Depends(current_user)):
        if "generation" in body.model_fields_set and body.generation.max_tokens > settings.limits.max_output_tokens:
            raise HTTPException(422, "Output limit exceeded")
        with rt.db.sessions() as db:
            message = owned(db, Message, identifier, user)
            ensure_convo_idle(db, message.conversation_id)
            if message.role != "assistant":
                raise HTTPException(422, "Only assistant replies can be regenerated")
            convo = owned(db, Conversation, message.conversation_id, user)
            char, public = readable_char(db, convo.character_id, user)
            generation = body.generation.model_dump() if "generation" in body.model_fields_set else character_generation(char, public)
            invalidate_derived(db, message.conversation_id)
            job = await rt.enqueue(user.id, "chat", {"conversation_id": message.conversation_id, "regenerate_message_id": identifier, "generation": generation}, db=db)
            db.commit()
            return job_json(job)

    @app.post("/api/v1/conversations/{identifier}/branch", status_code=201, response_model=ConversationResponse)
    async def branch(identifier: str, body: BranchInput, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            source = owned(db, Conversation, identifier, user)
            ensure_convo_idle(db, identifier)
            message = owned(db, Message, body.message_id, user)
            if message.conversation_id != identifier:
                raise HTTPException(404, "Message is outside this conversation")
            convo = Conversation(user_id=user.id, character_id=source.character_id, member_ids=source.member_ids, title=body.title or (source.title[:108] + " · Branch"), parent_id=source.id, branch_message_id=message.id)
            db.add(convo)
            db.flush()
            entries = db.scalars(select(Message).where(Message.conversation_id == identifier, Message.created_at <= message.created_at).order_by(Message.created_at)).all()
            for entry in entries:
                db.add(Message(user_id=user.id, conversation_id=convo.id, role=entry.role, content=entry.content, created_at=entry.created_at, edited_at=entry.edited_at, character_id=entry.character_id))
            for memory in db.scalars(select(Memory).where(Memory.conversation_id == identifier, Memory.automatic == False)).all():
                db.add(Memory(user_id=user.id, conversation_id=convo.id, character_id=source.character_id, content=memory.content, enabled=memory.enabled))
            db.commit()
            return conversation_json(convo)

    @app.get("/api/v1/conversations/{identifier}/memories", response_model=list[MemoryResponse])
    async def memories(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            owned(db, Conversation, identifier, user)
            return [memory_json(m) for m in db.scalars(select(Memory).where(Memory.conversation_id == identifier)).all()]

    @app.post("/api/v1/conversations/{identifier}/memories", status_code=201, response_model=MemoryResponse)
    async def add_memory(identifier: str, body: MemoryInput, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            convo = owned(db, Conversation, identifier, user)
            count = db.scalar(select(func.count()).select_from(Memory).where(Memory.conversation_id == identifier))
            if count >= 100:
                raise HTTPException(429, "Memory limit reached")
            memory = Memory(user_id=user.id, conversation_id=identifier, character_id=convo.character_id, **body.model_dump())
            db.add(memory)
            db.flush()
            db.commit()
            return memory_json(memory)

    @app.patch("/api/v1/memories/{identifier}", response_model=MemoryResponse)
    async def change_memory(identifier: str, body: MemoryInput, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            memory = owned(db, Memory, identifier, user)
            memory.content, memory.enabled = body.content, body.enabled
            db.commit()
            return memory_json(memory)

    @app.delete("/api/v1/memories/{identifier}")
    async def remove_memory(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            db.delete(owned(db, Memory, identifier, user))
            db.commit()
        return {"ok": True}

    @app.post("/api/v1/conversations/{identifier}/images", status_code=202, response_model=JobResponse)
    async def image(identifier: str, body: ImageRequest, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            owned(db, Conversation, identifier, user)
        return job_json(await rt.enqueue(user.id, "image", {"conversation_id": identifier, **body.model_dump()}))

    @app.post("/api/v1/conversations/{identifier}/speech", status_code=202, response_model=JobResponse)
    async def speech(identifier: str, body: SpeechRequest, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            convo = owned(db, Conversation, identifier, user)
            char, public = readable_char(db, convo.character_id, user)
            data = character_json(char, public=public)
            payload = body.model_dump()
            payload["voice"] = body.voice or data["voice"]
            payload["language"] = body.language or data["language"]
        return job_json(await rt.enqueue(user.id, "speech", {"conversation_id": identifier, **payload}))

    @app.post("/api/v1/tts-jobs", status_code=202, response_model=JobResponse)
    async def tts_preview(body: SpeechRequest, user: User = Depends(current_user)):
        payload = body.model_dump()
        payload["language"] = body.language or "de"
        payload["voice"] = body.voice or ("kokoro:af_heart" if payload["language"] == "en" else "piper:de_DE-thorsten-medium")
        return job_json(await rt.enqueue(user.id, "speech", payload))

    @app.post("/api/v1/voice-references", status_code=201)
    async def voice_reference(file: UploadFile, consent: bool = Form(...), user: User = Depends(current_user)):
        if not consent or not settings.xtts_enabled:
            raise HTTPException(403, "Voice cloning needs your consent and enabled XTTS usage rights")
        data = await file.read(settings.limits.voice_upload_bytes + 1)
        await file.close()
        if len(data) > settings.limits.voice_upload_bytes:
            raise HTTPException(413, "Voice sample too large")
        try:
            with wave.open(io.BytesIO(data), "rb") as sample:
                length = sample.getnframes() / sample.getframerate()
                if not 6 <= length <= 30 or sample.getnchannels() not in {1, 2} or not 8000 <= sample.getframerate() <= 48000 or sample.getsampwidth() != 2:
                    raise ValueError()
                normalized = io.BytesIO()
                with wave.open(normalized, "wb") as output:
                    output.setparams(sample.getparams())
                    output.writeframes(sample.readframes(sample.getnframes()))
                data = normalized.getvalue()
        except (wave.Error, ValueError, ZeroDivisionError, EOFError):
            raise HTTPException(422, "Use a 6–30 second PCM WAV sample, 8–48 kHz and 16-bit") from None
        with rt.db.sessions() as db:
            reserve_quota(db, f"voiceref:{user.id}", 5, 86400)
            asset = adopt(rt, db, user.id, data, "voice_reference")
            db.commit()
            return {"id": "xtts:ref:" + asset.id, "name": "Eigene Stimme " + asset.id[:8], "reference_asset_id": asset.id, "engine": "xtts", "language": "de", "available": True}

    @app.get("/api/v1/jobs", response_model=list[JobResponse])
    async def list_jobs(user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            return [job_json(j) for j in db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc()).limit(100)).all()]

    @app.get("/api/v1/jobs/{identifier}", response_model=JobResponse)
    async def get_job(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            return job_json(owned(db, Job, identifier, user))

    @app.post("/api/v1/jobs/{identifier}/cancel", response_model=JobResponse)
    async def cancel_job(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            job = owned(db, Job, identifier, user)
            if job.status not in TERMINAL:
                job.cancel_requested = True
                if job.status == "queued":
                    job.status, job.finished_at = "cancelled", time.time()
                    rt.event(db, job, "cancelled", {})
                elif identifier in rt.cancellations:
                    rt.cancellations[identifier].set()
                db.commit()
            return job_json(job)

    @app.get("/api/v1/jobs/{identifier}/events")
    async def job_events(identifier: str, request: Request, after: int = 0, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            owned(db, Job, identifier, user)
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")), 0)
        except ValueError:
            raise HTTPException(400, "Invalid event cursor") from None
        if rt.sse_counts.get(user.id, 0) >= 3:
            raise HTTPException(429, "Too many event streams", headers={"Retry-After": "10"})
        rt.sse_counts[user.id] = rt.sse_counts.get(user.id, 0) + 1

        async def stream():
            nonlocal cursor
            ping_at = time.monotonic()
            try:
                while not await request.is_disconnected():
                    try:
                        current_user(request)
                    except HTTPException:
                        yield 'event: auth_expired\ndata: {"reason":"Session expired; sign in again"}\n\n'
                        break
                    with rt.db.sessions() as db:
                        job = db.get(Job, identifier)
                        if not job or job.user_id != user.id:
                            break
                        events = db.scalars(select(JobEvent).where(JobEvent.job_id == identifier, JobEvent.id > cursor).order_by(JobEvent.id).limit(200)).all()
                        terminal = job.status in TERMINAL
                    for event in events:
                        cursor = event.id
                        yield f"id: {event.id}\nevent: {event.kind}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"
                    if terminal and len(events) < 200:
                        break
                    if time.monotonic() - ping_at > 15:
                        yield ": heartbeat\n\n"
                        ping_at = time.monotonic()
                    await asyncio.sleep(0.15)
            finally:
                rt.sse_counts[user.id] = max(0, rt.sse_counts.get(user.id, 1) - 1)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    def readable_asset(db, identifier, user=None):
        asset = db.get(Asset, identifier)
        if not asset:
            raise HTTPException(404, "Asset not found")
        if user and asset.user_id == user.id:
            return asset
        char = db.get(Character, asset.character_id) if asset.character_id else None
        owner = db.get(User, asset.user_id)
        if char and char.visibility == "public" and char.approved_snapshot and char.approved_snapshot.get("avatar_asset_id") == asset.id and owner and not owner.banned:
            return asset
        raise HTTPException(404, "Asset not found")

    @app.get("/api/v1/assets", response_model=list[AssetResponse])
    async def assets(user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            return [asset_json(a) for a in db.scalars(select(Asset).where(Asset.user_id == user.id).order_by(Asset.created_at.desc()).limit(200)).all()]

    @app.get("/api/v1/assets/{identifier}", response_model=AssetResponse)
    async def asset_metadata(identifier: str, request: Request):
        user = current_user(request) if request.headers.get("authorization") else None
        with rt.db.sessions() as db:
            return asset_json(readable_asset(db, identifier, user))

    @app.get("/api/v1/assets/{identifier}/content")
    async def content(identifier: str, request: Request):
        user = current_user(request) if request.headers.get("authorization") else None
        with rt.db.sessions() as db:
            asset = readable_asset(db, identifier, user)
            headers = {"Content-Security-Policy": "default-src 'none'; sandbox", "Content-Disposition": "inline"}
            if (asset.generation_metadata or {}).get("license_url") == XTTS_LICENSE:
                headers["Link"] = f'<{XTTS_LICENSE}>; rel="license"'
            return FileResponse(asset_path(rt, asset), media_type=asset.mime_type, headers=headers)

    @app.delete("/api/v1/assets/{identifier}")
    async def remove_asset(identifier: str, user: User = Depends(current_user)):
        with rt.db.sessions() as db:
            asset = owned(db, Asset, identifier, user)
            path = asset_path(rt, asset)
            if asset.character_id:
                char = db.get(Character, asset.character_id)
                if char and (char.avatar_asset_id == identifier or (char.approved_snapshot or {}).get("avatar_asset_id") == identifier):
                    char.avatar_asset_id, char.approved_snapshot, char.moderation_status = None, None, "pending"
                    char.approved_internal = None
            db.delete(asset)
            db.commit()
        path.unlink(missing_ok=True)
        return {"ok": True}

    @app.post("/api/v1/reports", status_code=201)
    async def report(body: ReportInput, user: User = Depends(current_user)):
        if bool(body.character_id) == bool(body.asset_id):
            raise HTTPException(422, "Report exactly one character or asset")
        with rt.db.sessions() as db:
            char = None
            if body.character_id:
                char, _ = readable_char(db, body.character_id, user)
            else:
                asset = readable_asset(db, body.asset_id, user)
                char = db.get(Character, asset.character_id) if asset.character_id else None
            key = f"character:{body.character_id}" if body.character_id else f"asset:{body.asset_id}"
            existing = db.scalar(select(Report).where(Report.user_id == user.id, Report.target_key == key))
            if existing:
                return {"id": existing.id, "status": existing.status, "created_at": timestamp(existing.created_at)}
            reserve_quota(db, f"reports:{user.id}", 10, 86400)
            item = Report(user_id=user.id, target_key=key, character_id=body.character_id, asset_id=body.asset_id, reason=body.reason)
            db.add(item)
            db.flush()
            if char and char.visibility == "public":
                await rt.schedule_moderation(char.user_id, {"character_id": char.id, "revision": char.revision, "report_recheck": True}, db=db)
            db.commit()
            return {"id": item.id, "status": item.status, "created_at": timestamp(item.created_at)}

    @app.get("/api/v1/search")
    async def search(q: str, user: User = Depends(current_user)):
        if not 1 <= len(q) <= 200:
            raise HTTPException(422, "Query must be 1–200 characters")
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with rt.db.sessions() as db:
            chars = db.scalars(select(Character).where(Character.user_id == user.id, or_(Character.name.ilike(pattern, escape="\\"), Character.description.ilike(pattern, escape="\\"))).limit(50)).all()
            convos = db.scalars(select(Conversation).where(Conversation.user_id == user.id, Conversation.title.ilike(pattern, escape="\\")).limit(50)).all()
            msgs = db.scalars(select(Message).where(Message.user_id == user.id, Message.content.ilike(pattern, escape="\\")).limit(50)).all()
            return {"characters": [character_json(c) for c in chars], "conversations": [conversation_json(c) for c in convos], "messages": [message_json(db, m) for m in msgs]}

    return app


def create_admin_app(settings: Settings | None = None, public_app: FastAPI | None = None) -> FastAPI:
    settings = settings or (public_app.state.runtime.settings if public_app else load_settings())
    app = FastAPI(title="Chatabae local control", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = public_app.state.runtime if public_app else Runtime(settings)
    rt = app.state.runtime

    @app.middleware("http")
    async def local_control(request, call_next):
        peer = request.client.host if request.client else ""
        supplied = request.headers.get("authorization", "")
        if peer not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"detail": "Local control authentication required"}, 403)
        request_origin = request.headers.get("origin")
        host = request.headers.get("host", "").lower()
        if host not in {f"127.0.0.1:{settings.admin_port}", f"localhost:{settings.admin_port}", f"[::1]:{settings.admin_port}", "testserver"}:
            return JSONResponse({"detail": "Local control host required"}, 403)
        if request_origin and request_origin not in {f"http://127.0.0.1:{settings.admin_port}", f"http://localhost:{settings.admin_port}"}:
            return JSONResponse({"detail": "Local control origin required"}, 403)
        if request.url.path != "/" or request.method != "GET":
            if not settings.control_token or not secrets.compare_digest(supplied, "Bearer " + settings.control_token):
                return JSONResponse({"detail": "Local control authentication required"}, 403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/")
    async def dashboard():
        page = Path(__file__).resolve().parents[2] / "launcher/admin.html"
        if not page.is_file():
            return HTMLResponse("<h1>Chatabae local control</h1><p>Admin dashboard file is not installed.</p>", status_code=503)
        return FileResponse(page, media_type="text/html", headers={"Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"})

    @app.get("/internal/status")
    async def status():
        with rt.db.sessions() as db:
            queued = db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued"))
            running = db.scalar(select(func.count()).select_from(Job).where(Job.status == "running"))
            sessions = db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.revoked == False, AuthSession.expires_at > time.time()))
        visitors = sum(time.monotonic() - seen <= 90 for seen in rt.recent_visitors.copy().values())
        return {"state": rt.state, "instance_id": settings.instance_id, "queue": {"queued": queued, "running": running}, "active_sessions": sessions, "active_visitors": visitors, "metrics": rt.metrics, "models": rt.providers.status(), "limits": settings.limits.model_dump(), "start_error": rt.start_error}

    @app.post("/internal/drain")
    async def drain():
        await rt.drain()
        return {"ok": True, "state": rt.state}

    @app.post("/internal/unload")
    async def unload():
        if rt.cancellations:
            raise HTTPException(409, "Drain active jobs before unloading")
        await rt.providers.unload_gpu()
        return {"ok": True}

    @app.post("/internal/backup")
    async def backup():
        from .backup import snapshot
        path = await asyncio.to_thread(snapshot, settings.data_dir)
        return {"ok": True, "snapshot": str(path)}

    @app.get("/internal/reports")
    async def reports():
        with rt.db.sessions() as db:
            items = db.scalars(select(Report).order_by(Report.created_at.desc()).limit(200)).all()
            return [{"id": r.id, "character_id": r.character_id, "asset_id": r.asset_id, "reason": r.reason, "status": r.status, "created_at": timestamp(r.created_at)} for r in items]

    @app.post("/internal/reports/{identifier}/resolve")
    async def resolve(identifier: str, body: dict):
        if body.get("action") not in {"dismiss", "hide"}:
            raise HTTPException(422, "Action must be dismiss or hide")
        with rt.db.sessions() as db:
            item = db.get(Report, identifier)
            if not item:
                raise HTTPException(404, "Report not found")
            item.status = "resolved"
            char_id = item.character_id
            if item.asset_id:
                asset = db.get(Asset, item.asset_id)
                char_id = asset.character_id if asset else None
            if body["action"] == "hide" and char_id:
                char = db.get(Character, char_id)
                if char:
                    char.approved_snapshot, char.approved_internal, char.moderation_status, char.moderation_reason = None, None, "held", "Hidden after local moderation review"
            db.commit()
        return {"ok": True}

    @app.post("/internal/users/{identifier}/ban")
    async def ban(identifier: str, body: dict | None = None):
        if body is not None and (set(body) != {"banned"} or type(body.get("banned")) is not bool):
            raise HTTPException(422, "Banned must be an explicit boolean")
        with rt.db.sessions() as db:
            user = db.get(User, identifier)
            if not user:
                raise HTTPException(404, "User not found")
            user.banned = body["banned"] if body else True
            if user.banned:
                rt.cancel_user_jobs(db, user.id)
            db.commit()
        return {"ok": True}

    @app.get("/internal/users")
    async def users():
        with rt.db.sessions() as db:
            return [{"id": u.id, "username": u.username, "banned": u.banned, "created_at": timestamp(u.created_at)} for u in db.scalars(select(User).order_by(User.created_at.desc()).limit(200)).all()]

    @app.post("/internal/characters/{identifier}/{decision}")
    async def review_character(identifier: str, decision: str):
        if decision not in {"approve", "hold"}:
            raise HTTPException(404, "Unknown review action")
        with rt.db.sessions() as db:
            char = db.get(Character, identifier)
            if not char:
                raise HTTPException(404, "Character not found")
            char.moderation_status = "approved" if decision == "approve" else "held"
            char.moderation_reason = "Reviewed by the local operator"
            char.approved_internal = character_json(char) if decision == "approve" else None
            char.approved_snapshot = public_snapshot(char.approved_internal) if char.approved_internal else None
            db.commit()
            return character_json(char)

    return app
