import asyncio
import io
import json
import time

import pytest
from PIL import Image
from sqlalchemy import func, select

from chatabae.db import Job, Quota, Report
from conftest import character_conversation, register, wait_job


@pytest.mark.parametrize("capability,endpoint,payload", [
    ("chat", "messages", {"content": "Hello"}),
    ("profile", "generate", {"idea": "Invented botanist"}),
    ("profile", "improve", {"field": "personality"}),
    ("image", "images", {"prompt": "Portrait"}),
    ("piper", "speech", {"text": "Hallo", "voice": "piper:de_DE-thorsten-medium"}),
    ("moderation", "moderate", {}),
])
def test_unavailable_capabilities_reject_before_generation_admission(service, capability, endpoint, payload):
    client, app, provider = service
    headers, _, _ = register(client)
    char, convo = character_conversation(client, headers)
    provider.capabilities[capability]["available"] = False
    route = "/api/v1/characters/generate" if endpoint == "generate" else f"/api/v1/characters/{char['id']}/{endpoint}" if endpoint in {"improve", "moderate"} else f"/api/v1/conversations/{convo['id']}/{endpoint}"
    response = client.post(route, headers=headers, json=payload)
    assert response.status_code == 503
    with app.state.runtime.db.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        keys = db.scalars(select(Quota.key)).all()
        assert not any(key.startswith(("chatday:", "profileday:", "imageday:", "imagegap:", "ttsmin:")) for key in keys)
    assert client.get(f"/api/v1/conversations/{convo['id']}/messages", headers=headers).json() == []


def test_usage_right_gate_precedes_missing_image_or_xtts_runtime(service):
    client, app, provider = service
    headers, _, _ = register(client)
    _, convo = character_conversation(client, headers)
    provider.capabilities["image"]["available"] = False
    provider.capabilities["xtts"]["available"] = False
    app.state.runtime.settings.mode = "online"
    assert client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "Portrait"}).status_code == 403
    assert client.post("/api/v1/tts-jobs", headers=headers, json={"text": "Hallo", "voice": "xtts:Ana Florence"}).status_code == 403
    app.state.runtime.settings.mode = "local"
    app.state.runtime.settings.xtts_enabled = True
    assert client.post("/api/v1/tts-jobs", headers=headers, json={"text": "Hallo", "voice": "xtts:Ana Florence"}).status_code == 503


def test_internal_unavailable_moderation_holds_private_revision_and_reported_snapshot(service):
    client, app, provider = service
    alice, _, _ = register(client)
    provider.capabilities["moderation"]["available"] = False
    created = client.post("/api/v1/characters", headers=alice, json={"name": "Held", "visibility": "public"})
    assert created.status_code == 201 and created.json()["moderation_status"] == "held"
    assert client.get(f"/api/v1/characters/{created.json()['id']}").status_code == 404
    generated = client.post("/api/v1/characters/generate", headers=alice, json={"idea": "A botanist", "visibility": "public"}).json()
    completed = wait_job(client, alice, generated["id"])
    assert completed["status"] == "completed" and completed["output"]["character"]["moderation_status"] == "held"
    provider.capabilities["moderation"]["available"] = True
    char, _ = character_conversation(client, alice, description="Approved description", visibility="public")
    wait_job(client, alice, client.get("/api/v1/jobs", headers=alice).json()[0]["id"])
    provider.capabilities["moderation"]["available"] = False
    changed = client.patch(f"/api/v1/characters/{char['id']}", headers=alice, json={"description": "Unreviewed description"})
    assert changed.status_code == 200 and changed.json()["moderation_status"] == "held"
    assert client.get(f"/api/v1/characters/{char['id']}").json()["description"] == "Approved description"
    bob, _, _ = register(client, "bob")
    response = client.post("/api/v1/reports", headers=bob, json={"character_id": char["id"], "reason": "Please check this profile"})
    assert response.status_code == 201
    assert client.get(f"/api/v1/characters/{char['id']}").status_code == 404
    with app.state.runtime.db.sessions() as db:
        assert db.get(Report, response.json()["id"])


@pytest.mark.parametrize("settings", [{"temperature": -0.1}, {"temperature": 2.1}, {"top_p": 0}, {"top_p": 1.1}, {"max_tokens": 31}, {"max_tokens": 1025}, {"unknown": "secret"}])
def test_profile_generation_defaults_are_bounded_on_create_and_patch(service, settings):
    client, _, _ = service
    headers, _, _ = register(client)
    assert client.post("/api/v1/characters", headers=headers, json={"name": "Invalid", "profile": {"generation_settings": settings}}).status_code == 422
    char, _ = character_conversation(client, headers)
    assert client.patch(f"/api/v1/characters/{char['id']}", headers=headers, json={"profile": {"generation_settings": settings}}).status_code == 422


def test_settings_only_patch_preserves_persona_and_drives_implicit_chat_and_regeneration(service):
    client, app, provider = service
    headers, _, _ = register(client)
    char, convo = character_conversation(client, headers, profile={"age": 31, "personality": "Original", "instructions": "Private"})
    defaults = {"temperature": 0.25, "top_p": 0.9, "max_tokens": 128}
    changed = client.patch(f"/api/v1/characters/{char['id']}", headers=headers, json={"profile": {"generation_settings": defaults}}).json()
    assert changed["profile"] == {**char["profile"], "generation_settings": defaults}
    assert changed["revision"] == char["revision"] + 1
    job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Hello"}).json()["job"]
    completed = wait_job(client, headers, job["id"])
    assert completed["status"] == "completed" and provider.received_generations[-1] == defaults
    regenerated = client.post(f"/api/v1/messages/{completed['output']['message']['id']}/regenerate", headers=headers, json={}).json()
    assert wait_job(client, headers, regenerated["id"])["status"] == "completed"
    assert provider.received_generations[-1] == defaults
    explicit = {"temperature": 0.5, "top_p": 0.6, "max_tokens": 64}
    next_job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Custom", "generation": explicit}).json()["job"]
    assert wait_job(client, headers, next_job["id"])["status"] == "completed"
    assert provider.received_generations[-1] == explicit
    assert provider.capabilities["chat"]["ready"] is False


def test_public_settings_patch_preserves_approved_snapshot_until_review(service):
    client, _, provider = service
    headers, _, _ = register(client)
    original = {"temperature": 0.7, "top_p": 0.8, "max_tokens": 512}
    char, _ = character_conversation(client, headers, visibility="public", profile={"age": 31, "personality": "Original", "generation_settings": original})
    wait_job(client, headers, client.get("/api/v1/jobs", headers=headers).json()[0]["id"])
    approved = client.get(f"/api/v1/characters/{char['id']}").json()
    provider.capabilities["moderation"]["available"] = False
    updated = {"temperature": 0.25, "top_p": 0.9, "max_tokens": 128}
    changed = client.patch(f"/api/v1/characters/{char['id']}", headers=headers, json={"profile": {"generation_settings": updated}}).json()
    assert changed["revision"] == char["revision"] + 1 and changed["moderation_status"] == "held"
    assert changed["profile"]["generation_settings"] == updated and changed["profile"]["personality"] == "Original"
    assert client.get(f"/api/v1/characters/{char['id']}").json() == approved
    provider.capabilities["moderation"]["available"] = True
    review = client.post(f"/api/v1/characters/{char['id']}/moderate", headers=headers).json()
    assert wait_job(client, headers, review["id"])["status"] == "completed"
    published = client.get(f"/api/v1/characters/{char['id']}").json()
    assert published["revision"] == changed["revision"] and published["profile"]["generation_settings"] == updated


def test_public_gpu_class_status_has_no_owner_job_prompt_or_paths(service):
    client, _, provider = service
    headers, _, _ = register(client)
    char, convo = character_conversation(client, headers)
    original = provider.generate_image
    async def slow_image(*args):
        await asyncio.sleep(0.5)
        return await original(*args)
    provider.generate_image = slow_image
    job = client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "UNIQUE_PRIVATE_PROMPT"}).json()
    deadline = time.time() + 2
    while time.time() < deadline:
        status = client.get("/api/v1/status").json()
        if status["queue"]["active_gpu_kind"] == "image":
            break
        time.sleep(0.01)
    assert status["queue"]["active_gpu_kind"] == "image"
    serialized = json.dumps(status)
    assert all(private not in serialized for private in ("UNIQUE_PRIVATE_PROMPT", job["id"], char["id"], "C:/", "C:\\"))
    assert wait_job(client, headers, job["id"])["status"] == "completed"
    assert client.get("/api/v1/status").json()["queue"]["active_gpu_kind"] is None
