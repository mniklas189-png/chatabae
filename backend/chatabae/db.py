from __future__ import annotations

import time
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def uid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String, unique=True)
    previous_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    expires_at: Mapped[float] = mapped_column(Float)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class AuthCode(Base):
    __tablename__ = "auth_codes"
    code_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=True)
    challenge: Mapped[str] = mapped_column(String)
    redirect_uri: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[float] = mapped_column(Float)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class SpentRefresh(Base):
    __tablename__ = "spent_refresh_tokens"
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("auth_sessions.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[float] = mapped_column(Float)


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"
    code_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Character(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    language: Mapped[str] = mapped_column(String, default="de")
    voice: Mapped[str] = mapped_column(String, default="piper:de")
    visibility: Mapped[str] = mapped_column(String, default="private", index=True)
    moderation_status: Mapped[str] = mapped_column(String, default="pending", index=True)
    moderation_reason: Mapped[str] = mapped_column(Text, default="")
    approved_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approved_internal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    avatar_asset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="Neues Gespräch")
    summary: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    branch_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    edited_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source_message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=True)
    automatic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String, unique=True)
    mime_type: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String)
    generation_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class JobEvent(Base):
    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("user_id", "target_key", name="uq_report_user_target"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    target_key: Mapped[str] = mapped_column(String)
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="open")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)


class Quota(Base):
    __tablename__ = "quotas"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False, "timeout": 15})

        @event.listens_for(self.engine, "connect")
        def sqlite_settings(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=15000")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

        @event.listens_for(self.sessions, "after_commit")
        def retain_committed_media(session):
            session.info.pop("new_media_files", None)

        @event.listens_for(self.sessions, "after_transaction_end")
        def remove_uncommitted_media(session, transaction):
            if transaction.parent is None:
                for filename in session.info.pop("new_media_files", []):
                    Path(filename).unlink(missing_ok=True)

        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent.parent / "migrations"))
        if path.exists() and path.stat().st_size:
            import sqlite3
            with sqlite3.connect(str(path)) as existing:
                versions = existing.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone()
                version = existing.execute("SELECT version_num FROM alembic_version").fetchone()[0] if versions else None
            if version and version != ScriptDirectory.from_config(config).get_current_head():
                from .backup import snapshot
                snapshot(path.parent)
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def close(self):
        self.engine.dispose()
