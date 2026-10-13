import asyncio
import io
import html
import re
import time
import wave
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from chatabae.app import create_app
from chatabae.auth import pkce
from chatabae.config import Limits, Settings


class FakeProviders:
    """Explicit test double; never installed as a production fallback."""
    def __init__(self, root):
        self.root = root
        self.started = []
        self.hold_moderation = False
        self.chat_delay = 0.003
        self.stopped = False
        self.received_chat = []
        self.speech_calls = []
        self.received_images = []
        self.image_options = []
        self.image_moderation = []
        self.composed = []
        self.hold_image_result = False
        self.speech_version = "test-model-v1"
        self.received_generations = []
        self.capabilities = {kind: {"available": True, "ready": False} for kind in ("chat", "profile", "moderation", "image", "tts", "kokoro", "piper", "xtts")}

    async def start(self): pass
    async def ensure_chat_ready(self): pass
    async def unload_gpu(self): pass
    async def stop(self): self.stopped = True
    def status(self): return dict(self.capabilities)
    def voices(self): return [{"id": "kokoro:af_heart", "name": "Heart", "language": "en", "engine": "kokoro", "gender": "female", "available": True}]
    def speech_fingerprint(self, voice, language=""): return self.speech_version

    async def stream_chat(self, messages, generation, cancel_event):
        self.started.append("chat")
        self.received_chat.append(messages)
        self.received_generations.append(generation)
        for token in ["Hello", " fictional", " friend."]:
            await asyncio.sleep(self.chat_delay)
            if cancel_event.is_set():
                raise asyncio.CancelledError()
            yield token

    async def create_profile(self, idea, mode, adult=False):
        self.profile_adult = adult
        return {"name": "Mira", "age": 24, "fictional": True, "description": idea, "personality": "Curious", "backstory": "An invented story", "language": "en", "voice": "kokoro:af_heart"}

    async def moderate_profile(self, profile, avatar_path=None):
        if self.hold_moderation:
            raise RuntimeError("Classifier unavailable")
        description = profile.get("description", "")
        return {"decision": "hold" if "forbidden" in description else "allow", "adult": "explicit" in description, "reason": "Local test policy"}

    async def compose_image_prompt(self, profile, scene, request):
        self.composed.append({"profile": dict(profile), "scene": scene, "request": request})
        return "Scene: " + request

    async def moderate_image(self, profile, prompt, image_path=None):
        self.image_moderation.append((prompt, image_path is not None))
        held = "forbidden" in prompt or (image_path is not None and self.hold_image_result)
        return {"decision": "hold" if held else "allow", "reason": "Local test policy"}

    async def generate_image(self, profile, prompt, options, cancel_event, progress_callback):
        self.started.append("image")
        self.received_images.append(profile)
        self.image_options.append(options)
        await progress_callback({"stage": "sampling", "value": 0.5})
        target = self.root / "test-provider-image.png"
        Image.new("RGB", (64, 64), "orange").save(target)
        return [target]

    async def synthesize(self, text, voice, language, speed, cancel_event):
        self.speech_calls.append({"text": text, "voice": voice, "language": language, "speed": speed})
        target = self.root / "test-provider-speech.wav"
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x00\x00" * 2400)
        return target


@pytest.fixture
def service(tmp_path):
    settings = Settings(data_dir=tmp_path, control_token="test-control-secret", backups_enabled=False, metrics_enabled=False, limits=Limits(disk_reserve_bytes=0, chat_per_minute=100, chat_per_day=100, profile_per_day=100))
    provider = FakeProviders(tmp_path)
    app = create_app(settings, provider)
    with TestClient(app) as client:
        yield client, app, provider


def register(client, username="alice"):
    client.cookies.clear()
    verifier = "a" * 64
    query = {"client_id": "chatabae", "redirect_uri": "http://localhost:5173/", "code_challenge": pkce(verifier), "code_challenge_method": "S256", "state": "safe_state_1234567890"}
    response = client.get("/auth/authorize", params=query)
    flow = re.search(r'name="flow" value="([^"]+)"', response.text).group(1)
    csrf = re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
    response = client.post("/auth/register", data={"username": username, "password": "correct-horse-password", "flow": flow, "csrf": csrf}, follow_redirects=False)
    assert response.status_code == 200, response.text
    recovery_codes = re.findall(r"<code>([a-f0-9]{32})</code>", response.text)
    assert len(recovery_codes) == 8
    continuation = html.unescape(re.search(r'id="continue" href="([^"]+)"', response.text).group(1))
    response = client.get(continuation, follow_redirects=False)
    assert response.status_code == 303, response.text
    code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]
    body = {"code": code, "code_verifier": verifier, "redirect_uri": query["redirect_uri"]}
    response = client.post("/api/v1/auth/exchange", json=body)
    assert response.status_code == 200, response.text
    token = response.json()
    assert "refresh_token" not in token
    token["test_refresh_cookie"] = client.cookies.get("chatabae_refresh")
    token["test_recovery_codes"] = recovery_codes
    return {"Authorization": "Bearer " + token["access_token"]}, token, body


def character_conversation(client, headers, **extra):
    response = client.post("/api/v1/characters", headers=headers, json={"name": "Ada", "profile": {"age": 25, "fictional": True}, **extra})
    assert response.status_code == 201, response.text
    character = response.json()
    response = client.post("/api/v1/conversations", headers=headers, json={"character_id": character["id"], "title": "Testing"})
    assert response.status_code == 201, response.text
    return character, response.json()


def wait_job(client, headers, identifier, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/v1/jobs/{identifier}", headers=headers)
        assert response.status_code == 200
        result = response.json()
        if result["status"] in {"completed", "failed", "cancelled"}:
            return result
        time.sleep(0.025)
    raise AssertionError("Job did not finish")
