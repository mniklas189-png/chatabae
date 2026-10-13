import io
import os
import time
import wave

from PIL import Image
from sqlalchemy import select

from chatabae.db import Asset, Job
from chatabae.jobs import XTTS_LICENSE
from chatabae.media import adopt, cleanup_orphans
from conftest import character_conversation, register, wait_job


def png(width=32, height=32):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "blue").save(buffer, "PNG")
    return buffer.getvalue()


def test_image_presets_seed_metadata_and_canonical_avatar(service):
    client, app, provider = service
    headers, _, _ = register(client)
    char, convo = character_conversation(client, headers)
    avatar = client.post(f"/api/v1/characters/{char['id']}/avatar", headers=headers, files={"file": ("portrait.png", png(40, 64), "image/png")}).json()
    endpoint = f"/api/v1/conversations/{convo['id']}/images"
    assert client.post(endpoint, headers=headers, json={"prompt": "Cafe", "options": {"preset": "fast", "steps": 25}}).status_code == 422
    assert client.post(endpoint, headers=headers, json={"prompt": "Cafe", "options": {"width": 512, "height": 1024}}).status_code == 422
    response = client.post(endpoint, headers=headers, json={"prompt": "Cafe", "options": {"preset": "fast", "width": 512, "height": 512, "seed": -1}})
    assert response.status_code == 202
    completed = wait_job(client, headers, response.json()["id"])
    assert completed["status"] == "completed"
    metadata = completed["output"]["assets"][0]["metadata"]
    assert metadata == {"preset": "fast", "steps": 15, "seed": provider.image_options[-1]["seed"], "width": 64, "height": 64, "reference": True}
    assert 0 <= metadata["seed"] <= 2**32 - 1
    with app.state.runtime.db.sessions() as db:
        canonical = db.get(Asset, avatar["id"])
        assert provider.received_images[-1]["avatar_path"] == str(app.state.runtime.settings.media_dir / canonical.filename)
        assert db.get(Job, response.json()["id"]).payload["options"]["seed"] == metadata["seed"]
    assert client.get(f"/api/v1/assets/{completed['output']['assets'][0]['id']}", headers=headers).json()["metadata"] == metadata
    assert client.get(f"/api/v1/characters/{char['id']}", headers=headers).json()["avatar_asset_id"] == avatar["id"]


def test_automatic_avatar_shares_image_quota_and_keeps_profile_usable(service):
    client, _, provider = service
    headers, _, _ = register(client)
    _, convo = character_conversation(client, headers)
    first = client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "Portrait", "options": {"seed": 42}}).json()
    assert wait_job(client, headers, first["id"])["status"] == "completed"
    response = client.post("/api/v1/characters/generate", headers=headers, json={"idea": "An imagined botanist", "mode": "automatic", "language": "de"})
    completed = wait_job(client, headers, response.json()["id"])
    assert completed["status"] == "completed" and completed["output"]["image_error"]
    profile = completed["output"]["character"]
    assert profile["avatar_asset_id"] is None and len(provider.image_options) == 1
    assert {"gender", "interests", "communication_style", "relationship", "instructions", "appearance", "background"} <= profile["profile"].keys()
    assert profile["language"] == "de" and profile["voice"].startswith("piper:de_DE-")


def test_media_files_follow_transaction_commit_or_rollback(service):
    _, app, _ = service
    client = service[0]
    headers, token, _ = register(client)
    char, _ = character_conversation(client, headers)
    rt = app.state.runtime
    before = set(rt.settings.media_dir.iterdir())
    with rt.db.sessions() as db:
        transient = adopt(rt, db, token["user"]["id"], png(), "image", character_id=char["id"])
        assert (rt.settings.media_dir / transient.filename).is_file()
    assert set(rt.settings.media_dir.iterdir()) == before
    with rt.db.sessions() as db:
        saved = adopt(rt, db, token["user"]["id"], png(), "image", character_id=char["id"])
        db.commit()
    assert (rt.settings.media_dir / saved.filename).is_file()


def test_voice_sample_over_5mib_is_allowed_up_to_voice_limit(service):
    client, app, _ = service
    headers, _, _ = register(client)
    app.state.runtime.settings.xtts_enabled = True
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(b"\x00\x00\x00\x00" * 48000 * 30)
    assert 5 * 1024**2 < len(buffer.getvalue()) < 10 * 1024**2
    response = client.post("/api/v1/voice-references", headers=headers, data={"consent": "true"}, files={"file": ("voice.wav", buffer.getvalue(), "audio/wav")})
    assert response.status_code == 201


def test_empty_provider_image_fails_without_empty_assistant_message(service):
    client, _, provider = service
    headers, _, _ = register(client)
    _, convo = character_conversation(client, headers)
    async def no_image(*args):
        return []
    provider.generate_image = no_image
    response = client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "Portrait"})
    assert wait_job(client, headers, response.json()["id"])["status"] == "failed"
    assert client.get(f"/api/v1/conversations/{convo['id']}/messages", headers=headers).json() == []


def test_xtts_output_persists_and_delivers_license_url(service):
    client, app, _ = service
    headers, _, _ = register(client)
    app.state.runtime.settings.xtts_enabled = True
    response = client.post("/api/v1/tts-jobs", headers=headers, json={"text": "Hallo", "voice": "xtts:Ana Florence"})
    completed = wait_job(client, headers, response.json()["id"])
    asset = completed["output"]["assets"][0]
    assert asset["metadata"] is None and asset["license_url"] == XTTS_LICENSE
    assert f'<{XTTS_LICENSE}>; rel="license"' == client.get(asset["url"], headers=headers).headers["Link"]
    with app.state.runtime.db.sessions() as db:
        assert db.get(Asset, asset["id"]).generation_metadata["license_url"] == XTTS_LICENSE


def test_owned_intermediate_cleanup_preserves_references_fresh_files_and_models(service):
    client, app, _ = service
    headers, tokens, _ = register(client)
    char, _ = character_conversation(client, headers)
    rt = app.state.runtime
    with rt.db.sessions() as db:
        saved = adopt(rt, db, tokens["user"]["id"], png(), "image", character_id=char["id"])
        db.commit()
    referenced = rt.settings.media_dir / saved.filename
    output = rt.settings.data_dir / "runtime/models/output"
    output.mkdir(parents=True)
    stale = output / ("speech_" + "a" * 32 + ".wav")
    fresh = output / ("speech_" + "b" * 32 + ".wav")
    unrelated = output / "operator-file.wav"
    model = rt.settings.data_dir / "runtime/models/model.gguf"
    for path in (stale, fresh, unrelated, model):
        path.write_bytes(b"test")
    old = time.time() - 7200
    for path in (stale, referenced, unrelated, model):
        os.utime(path, (old, old))
    assert cleanup_orphans(rt) == 1
    assert not stale.exists()
    assert all(path.exists() for path in (fresh, referenced, unrelated, model))
