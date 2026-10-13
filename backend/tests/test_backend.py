import io
import re
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from chatabae.app import create_admin_app, create_app
from chatabae.config import Limits, Settings
from chatabae.db import Character, Job, User
from conftest import FakeProviders, character_conversation, register, wait_job


def test_pkce_one_time_and_refresh_reuse_revoke_family(service):
    client, app, _ = service
    headers, token, exchange = register(client)
    assert client.post("/api/v1/auth/exchange", json=exchange).status_code == 400
    wrong = dict(exchange, code_verifier="b" * 64)
    assert client.post("/api/v1/auth/exchange", json=wrong).status_code == 400
    origin = {"Origin": "http://localhost:5173"}
    rotation = client.post("/api/v1/auth/refresh", json={}, headers=origin).json()
    second = client.post("/api/v1/auth/refresh", json={}, headers=origin).json()
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + second["access_token"]}).status_code == 200
    # Even an older spent token revokes the whole family, not just the previous rotation.
    assert client.post("/api/v1/auth/refresh", json={}, headers={**origin, "Cookie": "chatabae_refresh=" + token["test_refresh_cookie"]}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + second["access_token"]}).status_code == 401


def test_pkce_wrong_redirect_and_csrf_are_rejected(service):
    client, _, _ = service
    assert client.get("/auth/authorize", params={"client_id": "chatabae", "redirect_uri": "https://attacker.example/", "code_challenge": "a" * 43, "code_challenge_method": "S256", "state": "b" * 32}).status_code == 400
    assert client.post("/auth/register", data={"username": "alice", "password": "a" * 20, "flow": "bad", "csrf": "bad"}).status_code == 403


def test_auth_forms_let_browsers_send_their_origin(service):
    client, _, _ = service
    query = {"client_id": "chatabae", "redirect_uri": "http://localhost:5173/", "code_challenge": "a" * 43, "code_challenge_method": "S256", "state": "safe_state_1234567890"}
    form = client.get("/auth/authorize", params=query)
    flow = re.search(r'name="flow" value="([^"]+)"', form.text).group(1)
    # Browsers send `Origin: null` on form POSTs from no-referrer pages, which the origin check must reject.
    assert form.headers["Referrer-Policy"] == "same-origin"
    assert client.get("/auth/recover", params={"flow": flow}).headers["Referrer-Policy"] == "same-origin"
    assert client.get("/api/v1/status").headers["Referrer-Policy"] == "no-referrer"
    assert client.post("/auth/login", headers={"Origin": "null"}, data={"username": "alice", "password": "a" * 20, "flow": flow, "csrf": "x"}).status_code == 403


def test_ownership_stream_replay_memory_edit_search(service):
    client, _, _ = service
    alice, _, _ = register(client, "alice")
    char, convo = character_conversation(client, alice)
    bob, _, _ = register(client, "bob")
    assert client.get(f"/api/v1/conversations/{convo['id']}/messages", headers=bob).status_code == 404
    assert client.patch(f"/api/v1/characters/{char['id']}", headers=bob, json={"name": "Stolen"}).status_code == 404
    memory = client.post(f"/api/v1/conversations/{convo['id']}/memories", headers=alice, json={"content": "My favorite color is green"}).json()
    assert client.patch(f"/api/v1/memories/{memory['id']}", headers=bob, json={"content": "bad"}).status_code == 404
    result = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=alice, json={"content": "Hello Ada"}).json()
    job = wait_job(client, alice, result["job"]["id"])
    assert job["status"] == "completed"
    events = client.get(f"/api/v1/jobs/{job['id']}/events", headers=alice).text
    assert "event: token" in events and "Hello" in events and "event: completed" in events
    cursor = int([line[4:] for line in events.splitlines() if line.startswith("id: ")][-1])
    assert client.get(f"/api/v1/jobs/{job['id']}/events?after={cursor}", headers=alice).text == ""
    assert client.get(f"/api/v1/jobs/{job['id']}/events", headers=bob).status_code == 404
    reply = job["output"]["message"]
    assert client.patch(f"/api/v1/messages/{reply['id']}", headers=alice, json={"content": "Edited reply"}).status_code == 200
    search = client.get("/api/v1/search?q=Edited", headers=alice).json()
    assert search["messages"][0]["content"] == "Edited reply"
    assert client.get("/api/v1/search?q=Edited", headers=bob).json()["messages"] == []


def test_public_revision_is_snapshot_and_moderation_fail_closed(service):
    client, app, provider = service
    headers, _, _ = register(client)
    char, _ = character_conversation(client, headers, visibility="public", description="A kind adult character")
    jobs = client.get("/api/v1/jobs", headers=headers).json()
    wait_job(client, headers, jobs[0]["id"])
    public = client.get(f"/api/v1/characters/{char['id']}").json()
    assert public["description"] == "A kind adult character"
    provider.hold_moderation = True
    client.patch(f"/api/v1/characters/{char['id']}", headers=headers, json={"description": "New unchecked revision"})
    jobs = client.get("/api/v1/jobs", headers=headers).json()
    assert wait_job(client, headers, jobs[0]["id"])["status"] == "failed"
    assert client.get(f"/api/v1/characters/{char['id']}").json()["description"] == "A kind adult character"
    owned = client.get(f"/api/v1/characters/{char['id']}", headers=headers).json()
    assert owned["moderation_status"] == "held"


def test_upload_reencoding_ownership_and_public_approval(service):
    client, _, _ = service
    headers, _, _ = register(client)
    char, _ = character_conversation(client, headers)
    invalid = client.post(f"/api/v1/characters/{char['id']}/avatar", headers=headers, files={"file": ("photo.png", b"<svg onload='bad'/>", "image/png")})
    assert invalid.status_code == 422
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(buffer, "PNG")
    result = client.post(f"/api/v1/characters/{char['id']}/avatar", headers=headers, files={"file": ("../../unsafe.jpg.exe", buffer.getvalue() + b"SECRET TRAILING CONTENT", "application/octet-stream")})
    assert result.status_code == 201
    asset = result.json()
    assert client.get(asset["url"]).status_code == 404
    content = client.get(asset["url"], headers=headers)
    assert content.status_code == 200 and b"SECRET" not in content.content
    other, _, _ = register(client, "other")
    assert client.get(asset["url"], headers=other).status_code == 404
    assert client.delete(f"/api/v1/assets/{asset['id']}", headers=other).status_code == 404


def test_public_image_license_and_xtts_gate(service):
    client, app, _ = service
    headers, _, _ = register(client)
    _, convo = character_conversation(client, headers)
    app.state.runtime.settings.mode = "online"
    assert client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "Portrait"}).status_code == 403
    assert client.post(f"/api/v1/conversations/{convo['id']}/speech", headers=headers, json={"text": "Hello", "voice": "xtts:Ana Florence"}).status_code == 403
    app.state.runtime.settings.mode = "local"
    image = client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "Portrait"}).json()
    result = wait_job(client, headers, image["id"])
    assert result["status"] == "completed" and result["output"]["assets"][0]["kind"] == "image"


def test_public_images_are_moderated_before_and_after_generation(service):
    client, app, provider = service
    settings = app.state.runtime.settings
    settings.mode, settings.public_image_allowed = "online", True

    def image(username, prompt):
        # The per-account image gap allows one request per five minutes, so each case uses its own account.
        headers, _, _ = register(client, username)
        _, convo = character_conversation(client, headers)
        job = client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": prompt}).json()
        return headers, wait_job(client, headers, job["id"])

    _, allowed = image("alice", "Portrait")
    assert allowed["status"] == "completed" and provider.image_moderation == [("Scene: Portrait", False), ("Scene: Portrait", True)]
    generated = provider.started.count("image")
    _, blocked = image("bob", "forbidden scene")
    assert blocked["status"] == "failed" and "blocked by moderation" in blocked["error"]
    assert provider.started.count("image") == generated
    provider.hold_image_result = True
    carol, held = image("carol", "Cafe")
    assert held["status"] == "failed" and "blocked by moderation" in held["error"]
    assert not (provider.root / "test-provider-image.png").exists()
    assert [a for a in client.get("/api/v1/assets", headers=carol).json() if a["kind"] == "image"] == []


def test_adult_mode_needs_confirmation_and_an_adult_character(service):
    client, _, provider = service
    headers, _, _ = register(client)
    assert client.get("/api/v1/me", headers=headers).json()["adult_content"] is False
    assert client.put("/api/v1/me/adult-content", headers=headers, json={"enabled": True}).status_code == 422
    _, adult_convo = character_conversation(client, headers)
    _, young_convo = character_conversation(client, headers, profile={"age": 16, "fictional": True})

    def system_prompt(convo):
        job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Hi"}).json()["job"]
        assert wait_job(client, headers, job["id"])["status"] == "completed"
        return provider.received_chat[-1][0]["content"]

    assert "consenting adults" not in system_prompt(adult_convo)
    enabled = client.put("/api/v1/me/adult-content", headers=headers, json={"enabled": True, "confirm_adult": True})
    assert enabled.status_code == 200 and enabled.json()["adult_content"] is True
    assert client.get("/api/v1/me", headers=headers).json()["adult_content"] is True
    assert "consenting adults" in system_prompt(adult_convo)
    # A confirmed account never unlocks adult content for a character under 18.
    assert "consenting adults" not in system_prompt(young_convo)
    image = client.post(f"/api/v1/conversations/{adult_convo['id']}/images", headers=headers, json={"prompt": "Show me where you are"}).json()
    assert wait_job(client, headers, image["id"])["status"] == "completed"
    composed = provider.composed[-1]
    assert composed["profile"]["content_mode"] == "adult" and composed["request"] == "Show me where you are"
    assert any(message["content"] == "Hi" for message in composed["scene"]["messages"])
    assert client.put("/api/v1/me/adult-content", headers=headers, json={"enabled": False}).json()["adult_content"] is False
    assert "consenting adults" not in system_prompt(adult_convo)


def test_report_deduplication_and_admin_is_not_public(service):
    client, app, _ = service
    alice, _, _ = register(client)
    char, _ = character_conversation(client, alice, visibility="public")
    jobs = client.get("/api/v1/jobs", headers=alice).json()
    wait_job(client, alice, jobs[0]["id"])
    bob, _, _ = register(client, "bob")
    report = {"character_id": char["id"], "reason": "Please check this profile"}
    first = client.post("/api/v1/reports", headers=bob, json=report).json()
    assert client.post("/api/v1/reports", headers=bob, json=report).json()["id"] == first["id"]
    assert client.get("/internal/status", headers={"Authorization": "Bearer test-control-secret"}).status_code == 404
    with TestClient(create_admin_app(app.state.runtime.settings, app)) as admin:
        assert admin.get("/internal/reports").status_code == 403
        control = {"Authorization": "Bearer test-control-secret"}
        assert admin.get("/internal/reports", headers=control).json()[0]["id"] == first["id"]
        assert admin.post(f"/internal/reports/{first['id']}/resolve", headers=control, json={"action": "hide"}).status_code == 200
    assert client.get(f"/api/v1/characters/{char['id']}").status_code == 404


def test_cancellation_does_not_kill_scheduler_and_limits_persist(service):
    client, app, provider = service
    headers, _, _ = register(client)
    _, convo = character_conversation(client, headers)
    provider.chat_delay = 0.3
    first = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Cancel me"}).json()["job"]
    time.sleep(0.05)
    client.post(f"/api/v1/jobs/{first['id']}/cancel", headers=headers)
    assert wait_job(client, headers, first["id"])["status"] == "cancelled"
    provider.chat_delay = 0.003
    app.state.runtime.settings.limits.chat_per_day = 2
    second = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Next"}).json()["job"]
    assert wait_job(client, headers, second["id"])["status"] == "completed"
    assert client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Over quota"}).status_code == 429
    with app.state.runtime.db.sessions() as db:
        from chatabae.db import Quota
        assert db.scalars(select(Quota)).all()


def test_fair_choice_round_robin_and_heavy_aging(service):
    _, app, _ = service
    rt = app.state.runtime
    now = time.time()
    jobs = [Job(id="a1", user_id="a", kind="chat", status="queued", payload={}, created_at=now), Job(id="a2", user_id="a", kind="chat", status="queued", payload={}, created_at=now + 0.01), Job(id="b1", user_id="b", kind="chat", status="queued", payload={}, created_at=now + 0.02)]
    first = rt.choose(jobs, "gpu")
    assert first.id == "a1"
    assert rt.choose(jobs[1:], "gpu").id == "b1"
    heavy = Job(id="heavy", user_id="c", kind="image", status="queued", payload={}, created_at=now - 121)
    assert rt.choose(jobs + [heavy], "gpu").id == "heavy"


def test_drain_rejects_new_jobs(service):
    client, app, _ = service
    headers, _, _ = register(client)
    _, convo = character_conversation(client, headers)
    with TestClient(create_admin_app(app.state.runtime.settings, app)) as admin:
        assert admin.post("/internal/drain", headers={"Authorization": "Bearer test-control-secret"}).status_code == 200
    assert client.get("/health").json()["state"] == "draining"
    assert client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "No new job"}).status_code == 503


def test_restart_keeps_data_and_marks_interrupted_jobs(tmp_path):
    settings = Settings(data_dir=tmp_path, backups_enabled=False, metrics_enabled=False, limits=Limits(disk_reserve_bytes=0))
    fake = FakeProviders(tmp_path)
    first = create_app(settings, fake)
    with TestClient(first) as client:
        headers, tokens, _ = register(client)
        char, convo = character_conversation(client, headers)
        with first.state.runtime.db.sessions() as db:
            job = Job(user_id=tokens["user"]["id"], kind="chat", payload={"conversation_id": convo["id"]}, status="running")
            db.add(job)
            db.commit()
            job_id = job.id
    second = create_app(settings, FakeProviders(tmp_path))
    with TestClient(second) as client:
        assert client.get(f"/api/v1/characters/{char['id']}", headers=headers).status_code == 200
        result = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        assert result["status"] == "failed" and "restart" in result["error"]


def test_body_and_output_limits_and_general_character_scope(service):
    client, _, _ = service
    headers, _, _ = register(client)
    assert client.post("/api/v1/characters", headers=headers, json={"name": "Young", "profile": {"age": 17}}).status_code == 201
    assert client.post("/api/v1/characters", headers=headers, json={"name": "Real", "profile": {"age": 25, "fictional": False}}).status_code == 201
    assert client.post("/api/v1/characters", headers=headers, json={"name": "Invalid", "profile": {"age": -1}}).status_code == 422
    _, convo = character_conversation(client, headers)
    assert client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Hello", "generation": {"max_tokens": 4096}}).status_code == 422
    assert client.post("/api/v1/characters", headers=headers, content=(b"x" * 1024 for _ in range(140))).status_code == 413
