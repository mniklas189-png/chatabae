import html
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from chatabae.app import create_admin_app, create_app
from chatabae.auth import pkce
from chatabae.backup import restore, snapshot, verify
from chatabae.config import Limits, Settings
from chatabae.db import Character, Conversation, Job, Memory, Message, RecoveryCode, User
from conftest import FakeProviders, character_conversation, register, wait_job


def authorization_flow(client):
    response = client.get("/auth/authorize", params={"client_id": "chatabae", "redirect_uri": "http://localhost:5173/", "code_challenge": pkce("a" * 64), "code_challenge_method": "S256", "state": "safe_state_1234567890", "mode": "register"})
    return re.search(r'name="flow" value="([^"]+)"', response.text).group(1)


def test_recovery_code_once_only_and_old_sessions_revoked(service):
    client, app, _ = service
    headers, tokens, _ = register(client)
    flow = authorization_flow(client)
    page = client.get("/auth/recover", params={"flow": flow})
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    reset = {"username": "alice", "recovery_code": tokens["test_recovery_codes"][0], "password": "new-correct-horse-password", "flow": flow, "csrf": csrf}
    assert client.post("/auth/recover", data=reset, follow_redirects=False).status_code == 303
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert client.post("/auth/recover", data=reset, follow_redirects=False).status_code == 400
    with app.state.runtime.db.sessions() as db:
        rows = db.scalars(select(RecoveryCode)).all()
        assert len(rows) == 8 and sum(r.used for r in rows) == 1
        assert tokens["test_recovery_codes"][0] not in {r.code_hash for r in rows}


def test_cookie_only_origin_and_admin_host_allowlist(service):
    client, app, _ = service
    headers, _, _ = register(client)
    response = client.post("/api/v1/auth/refresh", json={}, headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200 and "refresh_token" not in response.json()
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.post("/api/v1/auth/refresh", json={}, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "ignored"}).status_code == 422
    with TestClient(create_admin_app(app.state.runtime.settings, app)) as admin:
        control = {"Authorization": "Bearer test-control-secret"}
        assert admin.get("/internal/status", headers={**control, "Host": "rebind.attacker.example:7811"}).status_code == 403
        assert admin.get("/internal/status", headers={**control, "Origin": "https://attacker.example"}).status_code == 403


def test_sse_revocation_logout_cancels_job_and_lane_recovers(service):
    client, app, provider = service
    headers, tokens, _ = register(client)
    _, convo = character_conversation(client, headers)
    provider.chat_delay = 0.8
    job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Long stream"}).json()["job"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.get, f"/api/v1/jobs/{job['id']}/events", headers=headers)
        time.sleep(0.2)
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        response = future.result(timeout=5)
    assert "event: auth_expired" in response.text
    with app.state.runtime.db.sessions() as db:
        live = db.get(Job, job["id"])
        assert live.cancel_requested
    assert app.state.runtime.sse_counts[tokens["user"]["id"]] == 0


def test_public_snapshot_never_leaks_private_instructions_or_references(service):
    client, app, _ = service
    headers, _, _ = register(client)
    char, _ = character_conversation(client, headers, visibility="public", profile={"age": 28, "instructions": "SECRET_PROMPT", "relationship": "PRIVATE_RELATIONSHIP", "voice_reference": "C:/private/reference.wav", "personality": "Friendly", "appearance": {"hair": "dark", "path": "PRIVATE_PATH"}})
    job = client.get("/api/v1/jobs", headers=headers).json()[0]
    wait_job(client, headers, job["id"])
    assert "SECRET" in client.get(f"/api/v1/characters/{char['id']}", headers=headers).text
    public = client.get(f"/api/v1/characters/{char['id']}").text
    assert "SECRET" not in public and "PRIVATE" not in public and "reference.wav" not in public
    with TestClient(create_admin_app(app.state.runtime.settings, app)) as admin:
        control = {"Authorization": "Bearer test-control-secret"}
        assert admin.post(f"/internal/characters/{char['id']}/approve", headers=control).status_code == 200
    assert "SECRET" not in client.get(f"/api/v1/characters/{char['id']}").text


def test_account_delete_keeps_other_users_private_conversations(service):
    client, app, _ = service
    alice, tokens, _ = register(client)
    char, own_convo = character_conversation(client, alice, visibility="public")
    job = client.get("/api/v1/jobs", headers=alice).json()[0]
    wait_job(client, alice, job["id"])
    bob, _, _ = register(client, "bob")
    bob_convo = client.post("/api/v1/conversations", headers=bob, json={"character_id": char["id"], "title": "Bob's private history"}).json()
    with app.state.runtime.db.sessions() as db:
        db.add(Message(user_id=client.get("/api/v1/me", headers=bob).json()["id"], conversation_id=bob_convo["id"], role="user", content="Bob's secret"))
        db.commit()
    assert client.delete("/api/v1/me", headers=alice).status_code == 200
    assert client.get("/api/v1/me", headers=alice).status_code == 401
    assert client.get(f"/api/v1/characters/{char['id']}").status_code == 404
    assert client.get(f"/api/v1/conversations/{bob_convo['id']}/messages", headers=bob).json()[0]["content"] == "Bob's secret"
    with app.state.runtime.db.sessions() as db:
        assert db.get(User, tokens["user"]["id"]) is None
        assert db.get(Conversation, own_convo["id"]) is None
        assert db.get(Conversation, bob_convo["id"]) is not None


def test_branch_prefix_and_edit_invalidates_only_derived_memories(service):
    client, app, _ = service
    headers, tokens, _ = register(client)
    char, convo = character_conversation(client, headers)
    with app.state.runtime.db.sessions() as db:
        first = Message(user_id=tokens["user"]["id"], conversation_id=convo["id"], role="user", content="First", created_at=1)
        later = Message(user_id=tokens["user"]["id"], conversation_id=convo["id"], role="assistant", content="Later", created_at=2)
        db.add_all([first, later])
        db.flush()
        db.add(Memory(user_id=tokens["user"]["id"], character_id=char["id"], conversation_id=convo["id"], content="Manual fact"))
        db.add(Memory(user_id=tokens["user"]["id"], character_id=char["id"], conversation_id=convo["id"], content="Generated fact", automatic=True, source_message_id=later.id))
        db.get(Conversation, convo["id"]).summary = "Stale summary"
        db.commit()
        first_id = first.id
    branch = client.post(f"/api/v1/conversations/{convo['id']}/branch", headers=headers, json={"message_id": first_id}).json()
    assert client.get(f"/api/v1/conversations/{branch['id']}/messages", headers=headers).json()[0]["content"] == "First"
    assert len(client.get(f"/api/v1/conversations/{branch['id']}/messages", headers=headers).json()) == 1
    assert client.patch(f"/api/v1/messages/{first_id}", headers=headers, json={"content": "Changed"}).status_code == 200
    assert [m["content"] for m in client.get(f"/api/v1/conversations/{convo['id']}/memories", headers=headers).json()] == ["Manual fact"]
    with app.state.runtime.db.sessions() as db:
        assert db.get(Conversation, convo["id"]).summary == ""


def test_consistent_snapshot_verify_restore_and_live_process_refusal(service, tmp_path):
    client, app, _ = service
    headers, _, _ = register(client)
    char, _ = character_conversation(client, headers)
    image = io.BytesIO()
    Image.new("RGB", (24, 24), "blue").save(image, "PNG")
    client.post(f"/api/v1/characters/{char['id']}/avatar", headers=headers, files={"file": ("avatar.png", image.getvalue(), "image/png")})
    data_dir = app.state.runtime.settings.data_dir
    created = snapshot(data_dir)
    manifest = verify(created)
    assert len(manifest["files"]) == 2
    try:
        restore(created, data_dir)
        assert False, "Live restoration should fail"
    except RuntimeError as error:
        assert "Stop Chatabae" in str(error)
    destination = tmp_path / "restored"
    restore(created, destination)
    settings = Settings(data_dir=destination, backups_enabled=False, metrics_enabled=False, limits=Limits(disk_reserve_bytes=0))
    with TestClient(create_app(settings, FakeProviders(destination))) as restored:
        assert restored.get("/api/v1/me", headers=headers).status_code == 401
        with restored.app.state.runtime.db.sessions() as db:
            assert db.get(Character, char["id"]) is not None
    media_entry = next(e for e in manifest["files"] if e["path"].startswith("media/"))
    (created / media_entry["path"]).write_bytes(b"tampered")
    try:
        verify(created)
        assert False, "Corrupt snapshot should fail verification"
    except ValueError as error:
        assert "checksum" in str(error)


def test_sse_connections_bound_and_unban(service):
    client, app, _ = service
    headers, token, _ = register(client)
    _, convo = character_conversation(client, headers)
    job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Hi"}).json()["job"]
    wait_job(client, headers, job["id"])
    app.state.runtime.sse_counts[token["user"]["id"]] = 3
    assert client.get(f"/api/v1/jobs/{job['id']}/events", headers=headers).status_code == 429
    with TestClient(create_admin_app(app.state.runtime.settings, app)) as admin:
        control = {"Authorization": "Bearer test-control-secret"}
        assert admin.post(f"/internal/users/{token['user']['id']}/ban", headers=control, json={"banned": True}).status_code == 200
        assert client.get("/api/v1/me", headers=headers).status_code == 401
        assert admin.post(f"/internal/users/{token['user']['id']}/ban", headers=control, json={"banned": False}).status_code == 200
        assert client.get("/api/v1/me", headers=headers).status_code == 200


def test_reported_snapshot_is_quarantined_when_local_moderation_fails(service):
    client, app, provider = service
    alice, _, _ = register(client)
    char, _ = character_conversation(client, alice, visibility="public")
    wait_job(client, alice, client.get("/api/v1/jobs", headers=alice).json()[0]["id"])
    bob, _, _ = register(client, "bob")
    provider.hold_moderation = True
    report = client.post("/api/v1/reports", headers=bob, json={"character_id": char["id"], "reason": "Please recheck this public profile"})
    assert report.status_code == 201
    job = client.get("/api/v1/jobs", headers=alice).json()[0]
    assert wait_job(client, alice, job["id"])["status"] == "failed"
    assert client.get(f"/api/v1/characters/{char['id']}").status_code == 404
    assert client.get(f"/api/v1/characters/{char['id']}", headers=alice).json()["moderation_status"] == "held"
    with TestClient(create_admin_app(app.state.runtime.settings, app)) as admin:
        assert admin.get("/internal/reports", headers={"Authorization": "Bearer test-control-secret"}).json()[0]["id"] == report.json()["id"]


def test_gpu_resource_error_is_actionable_and_arbitrary_errors_stay_private(service):
    from chatabae.providers import GPUResourceError
    client, _, provider = service
    headers, _, _ = register(client)
    _, convo = character_conversation(client, headers)
    async def no_vram(*args):
        raise GPUResourceError("chat", "GPU memory is insufficient. Close other GPU applications and retry.")
        yield "unreachable"
    provider.stream_chat = no_vram
    first = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Hello"}).json()["job"]
    assert "Close other GPU" in wait_job(client, headers, first["id"])["error"]
    async def private_failure(*args):
        raise RuntimeError("PRIVATESECRET in C:/Users/private/model.log")
        yield "unreachable"
    provider.stream_chat = private_failure
    second = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Retry"}).json()["job"]
    assert "PRIVATESECRET" not in json.dumps(wait_job(client, headers, second["id"]))


def test_argon_cpu_concurrency_and_random_username_ip_quota_are_bounded(service, monkeypatch):
    import chatabae.auth as auth
    client, app, _ = service
    query = {"client_id": "chatabae", "redirect_uri": "http://localhost:5173/", "code_challenge": pkce("a" * 64), "code_challenge_method": "S256", "state": "safe_state_1234567890"}
    page = client.get("/auth/authorize", params=query)
    flow = re.search(r'name="flow" value="([^"]+)"', page.text).group(1)
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    active = peak = 0
    lock = threading.Lock()
    def bounded_hash(_):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.05)
            return "dummy-test-hash"
        finally:
            with lock:
                active -= 1
    monkeypatch.setattr(auth, "hasher", SimpleNamespace(hash=bounded_hash))
    def attempt(index):
        return client.post("/auth/login", headers={"Cookie": "chatabae_csrf=" + csrf}, data={"username": f"unknown_{index}", "password": "correct-horse-password", "flow": flow, "csrf": csrf})
    with ThreadPoolExecutor(max_workers=9) as executor:
        assert all(result.status_code == 200 for result in executor.map(attempt, range(9)))
    assert peak == 2
    assert attempt(9).status_code == 200
    assert attempt(10).status_code == 429
