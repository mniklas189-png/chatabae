from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileGeneration(Strict):
    temperature: float = Field(0.7, ge=0, le=2)
    top_p: float = Field(0.8, gt=0, le=1)
    max_tokens: int = Field(512, ge=32, le=1024)


class CharacterInput(Strict):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)
    profile: dict = Field(default_factory=lambda: {"age": 18, "fictional": True})
    language: Literal["de", "en"] = "de"
    voice: str = Field(default="piper:de_DE-thorsten-medium", max_length=100)
    visibility: Literal["private", "public"] = "private"

    @field_validator("profile")
    @classmethod
    def check_profile(cls, value):
        import json
        if len(json.dumps(value, ensure_ascii=False)) > 16000:
            raise ValueError("Profile is too large")
        if type(value.get("age", 18)) is not int or not 0 <= value.get("age", 18) <= 10000:
            raise ValueError("Character age must be nonnegative")
        if type(value.get("fictional", True)) is not bool:
            raise ValueError("Fictional must be a boolean")
        if "generation_settings" in value:
            value = {**value, "generation_settings": ProfileGeneration.model_validate(value["generation_settings"]).model_dump()}
        return {**value, "age": value.get("age", 18), "fictional": value.get("fictional", True)}


class CharacterPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    profile: dict | None = None
    language: Literal["de", "en"] | None = None
    voice: str | None = Field(default=None, max_length=100)
    visibility: Literal["private", "public"] | None = None

    @field_validator("profile")
    @classmethod
    def check_profile(cls, value):
        if value is None:
            raise ValueError("Profile cannot be null")
        verified = CharacterInput.check_profile(value)
        # Preserve patch keys so a settings-only update cannot reset persona fields.
        return {**value, **({"generation_settings": verified["generation_settings"]} if "generation_settings" in value else {})}


class Generation(Strict):
    temperature: float = Field(0.7, ge=0, le=2)
    top_p: float = Field(0.8, gt=0, le=1)
    max_tokens: int = Field(512, ge=32, le=8192)


class Turn(Strict):
    content: str = Field(min_length=1, max_length=12000)
    generation: Generation = Field(default_factory=Generation)


class TextUpdate(Strict):
    content: str = Field(min_length=1, max_length=12000)


class Regenerate(Strict):
    generation: Generation = Field(default_factory=Generation)


class ConversationInput(Strict):
    title: str = Field("Neues Gespräch", min_length=1, max_length=120)


class ConversationCreate(ConversationInput):
    character_id: str


class MemoryInput(Strict):
    content: str = Field(min_length=1, max_length=2000)
    enabled: bool = True


class ProfileRequest(Strict):
    idea: str = Field(default="Create a new fictional adult character", min_length=1, max_length=4000)
    mode: Literal["assisted", "automatic"] = "assisted"
    language: Literal["de", "en"] = "de"
    visibility: Literal["private", "public"] = "private"
    # False when the creator uploads their own picture instead of an AI portrait.
    portrait: bool = True


class ImageOptions(Strict):
    width: Literal[512, 1024] = 1024
    height: Literal[512, 1024] = 1024
    preset: Literal["fast", "balanced"] = "balanced"
    steps: Literal[15, 25] = 25
    seed: int = Field(-1, ge=-1, le=2**32 - 1)

    @model_validator(mode="before")
    @classmethod
    def preset_steps(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            preset = value.get("preset", "fast" if value.get("steps") == 15 else "balanced")
            expected = 15 if preset == "fast" else 25
            if "steps" in value and value["steps"] != expected:
                raise ValueError("Image steps must match the selected preset")
            value.update(preset=preset, steps=expected)
        return value

    @model_validator(mode="after")
    def square_without_reference(self):
        if self.width != self.height:
            raise ValueError("Use a square format; a character avatar determines reference aspect ratio")
        return self


class ImageRequest(Strict):
    prompt: str = Field(min_length=1, max_length=2000)
    options: ImageOptions = Field(default_factory=ImageOptions)


class SpeechRequest(Strict):
    text: str = Field(min_length=1, max_length=2000)
    voice: str | None = Field(None, max_length=100)
    language: Literal["de", "en"] | None = None
    speed: float = Field(1.0, ge=0.7, le=1.3)


class ReportInput(Strict):
    character_id: str | None = None
    asset_id: str | None = None
    reason: str = Field(min_length=5, max_length=2000)


class CodeExchange(Strict):
    code: str = Field(min_length=20, max_length=200)
    code_verifier: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9._~-]+$")
    redirect_uri: str = Field(max_length=2000)


class RefreshRequest(Strict):
    pass


class UserResponse(BaseModel):
    id: str
    username: str
    adult_content: bool = False


class AdultContent(Strict):
    enabled: bool
    confirm_adult: bool = False


class GroupConversationCreate(Strict):
    character_ids: list[str] = Field(min_length=2, max_length=4)
    title: str = Field("", max_length=120)


class AvatarRequest(Strict):
    name: str = Field("", max_length=80)
    description: str = Field("", max_length=1000)
    age: int | None = Field(None, ge=0, le=10000)
    gender: str = Field("", max_length=100)
    appearance: str = Field("", max_length=8000)
    prompt: str = Field("", max_length=1000)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_in: int
    user: UserResponse


class ImageMetadata(BaseModel):
    seed: int
    preset: Literal["fast", "balanced"]
    width: int
    height: int
    steps: Literal[15, 25]
    reference: bool = False


class AssetResponse(BaseModel):
    id: str
    kind: Literal["image", "audio", "voice_reference"]
    mime_type: str
    size_bytes: int
    created_at: str
    url: str
    character_id: str | None = None
    conversation_id: str | None = None
    metadata: ImageMetadata | None = None
    license_url: str | None = None


class CharacterResponse(BaseModel):
    id: str
    name: str
    description: str
    profile: dict
    language: Literal["de", "en"]
    voice: str
    visibility: Literal["private", "public"]
    moderation_status: Literal["pending", "approved", "held"]
    moderation_reason: str = ""
    avatar_asset_id: str | None = None
    revision: int
    created_at: str | None = None
    updated_at: str | None = None


class ConversationResponse(BaseModel):
    id: str
    character_id: str
    character_ids: list[str]
    title: str
    parent_id: str | None = None
    branch_message_id: str | None = None
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str
    edited_at: str | None = None
    assets: list[AssetResponse]
    character_id: str | None = None


class MemoryResponse(BaseModel):
    id: str
    conversation_id: str
    character_id: str
    content: str
    enabled: bool
    automatic: bool
    source_message_id: str | None = None
    created_at: str


class JobResponse(BaseModel):
    id: str
    kind: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    output: dict
    error: str | None = None


class TurnResponse(BaseModel):
    message: MessageResponse
    job: JobResponse


class ProfileImprovement(Strict):
    field: Literal["name", "description", "personality", "appearance", "background", "interests", "communication_style", "instructions", "relationship", "scenario", "greeting"]
    idea: str = Field("", max_length=4000)


class BranchInput(Strict):
    message_id: str
    title: str | None = Field(None, max_length=120)
