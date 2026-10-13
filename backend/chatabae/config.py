from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Limits(BaseModel):
    queue_size: int = Field(32, ge=1, le=256)
    per_user_pending: int = Field(2, ge=1, le=8)
    chat_per_minute: int = Field(4, ge=1)
    chat_per_day: int = Field(100, ge=1)
    image_per_day: int = Field(3, ge=1)
    avatar_per_day: int = Field(10, ge=1)
    hq_tts_per_day: int = Field(5, ge=1)
    tts_per_minute: int = Field(10, ge=1)
    profile_per_day: int = Field(10, ge=1)
    upload_bytes: int = Field(5 * 1024 * 1024, ge=1024)
    voice_upload_bytes: int = Field(10 * 1024 * 1024, ge=1024)
    image_pixels: int = Field(16_000_000, ge=1024)
    user_storage_bytes: int = Field(500 * 1024 * 1024, ge=1024)
    global_storage_bytes: int = Field(20 * 1024**3, ge=1024)
    disk_reserve_bytes: int = Field(10 * 1024**3, ge=0)
    max_input_chars: int = Field(12000, ge=128)
    max_output_tokens: int = Field(1024, ge=32, le=8192)
    gpu_aging_seconds: float = Field(120, ge=0)
    chat_timeout: float = Field(120, gt=0)
    heavy_timeout: float = Field(600, gt=0)
    moderation_timeout: float = Field(180, gt=0)
    tts_timeout: float = Field(60, gt=0)


class Settings(BaseModel):
    data_dir: Path = Field(default_factory=lambda: Path.home() / "AppData/Local/Chatabae" if os.name == "nt" else Path.home() / ".local/share/Chatabae")
    mode: Literal["local", "online"] = "local"
    frontend_url: str = "http://localhost:5173/"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    public_api_url: str = "http://127.0.0.1:7810"
    port: int = 7810
    admin_port: int = 7811
    model_paths: dict = Field(default_factory=dict)
    runtime: dict = Field(default_factory=lambda: {"model_host": "127.0.0.1", "chat_port": 8792, "image_port": 8793, "chat_context": 8192, "chat_gpu_layers": 99, "chat_threads": 8})
    image: dict = Field(default_factory=dict)
    limits: Limits = Field(default_factory=Limits)
    public_image_allowed: bool = False
    public_image_license_evidence: str = ""
    xtts_enabled: bool = False
    instance_id: str = "local"
    control_token: str = ""
    access_seconds: int = 900
    refresh_seconds: int = 30 * 86400
    registration_enabled: bool = True
    backups_enabled: bool = True
    metrics_enabled: bool = True

    @model_validator(mode="after")
    def validate_public(self):
        self.data_dir = self.data_dir.expanduser().resolve()
        if self.mode == "online" and not self.public_api_url.startswith("https://"):
            raise ValueError("Online mode requires an HTTPS public_api_url")
        if self.public_image_allowed and not self.public_image_license_evidence.strip():
            raise ValueError("Public image generation needs documented license evidence")
        if "*" in self.allowed_origins:
            raise ValueError("Wildcard CORS origins are not allowed")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / "chatabae.sqlite3"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def secure_cookies(self) -> bool:
        return self.public_api_url.startswith("https://")


def load_settings() -> Settings:
    config_path = os.environ.get("CHATABAE_CONFIG")
    payload = json.loads(Path(config_path).read_text(encoding="utf-8-sig")) if config_path else {}
    for env, key in (("CHATABAE_DATA_DIR", "data_dir"), ("CHATABAE_MODE", "mode"), ("CHATABAE_INSTANCE_ID", "instance_id"), ("CHATABAE_CONTROL_TOKEN", "control_token")):
        if env in os.environ:
            payload[key] = os.environ[env]
    return Settings.model_validate(payload)
