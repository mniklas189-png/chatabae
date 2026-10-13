import time

from conftest import register, wait_job


def make_character(client, headers, name, age=25):
    response = client.post("/api/v1/characters", headers=headers, json={"name": name, "description": f"{name} is invented", "profile": {"age": age, "fictional": True}})
    assert response.status_code == 201, response.text
    return response.json()


def turn(client, headers, convo, content):
    result = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": content}).json()
    job = wait_job(client, headers, result["job"]["id"])
    assert job["status"] == "completed", job
    return job


def test_group_chat_speakers_mentions_regeneration_and_member_removal(service):
    client, _, provider = service
    headers, _, _ = register(client)
    ada, ben = make_character(client, headers, "Ada"), make_character(client, headers, "Ben Stone")
    assert client.post("/api/v1/group-conversations", headers=headers, json={"character_ids": [ada["id"], ada["id"]]}).status_code == 422
    assert client.post("/api/v1/group-conversations", headers=headers, json={"character_ids": [ada["id"], "missing"]}).status_code == 404
    group = client.post("/api/v1/group-conversations", headers=headers, json={"character_ids": [ada["id"], ben["id"]]}).json()
    assert group["character_ids"] == [ada["id"], ben["id"]] and group["title"] == "Ada, Ben Stone"

    job = turn(client, headers, group, "Hi everyone")
    assert [m["character_id"] for m in job["output"]["messages"]] == [ada["id"], ben["id"]]
    ben_prompt = provider.received_chat[-1]
    assert "roleplaying Ben Stone" in ben_prompt[0]["content"] and "Ada: Hello fictional friend." in ben_prompt[-1]["content"]

    # Addressing a character by first name lets only that character reply.
    job = turn(client, headers, group, "Ben, what do you think?")
    assert [m["character_id"] for m in job["output"]["messages"]] == [ben["id"]]
    # Without a mention, the rotation continues after the last speaker.
    job = turn(client, headers, group, "And now?")
    assert [m["character_id"] for m in job["output"]["messages"]] == [ada["id"], ben["id"]]

    messages = client.get(f"/api/v1/conversations/{group['id']}/messages", headers=headers).json()
    first_ada = next(m for m in messages if m["character_id"] == ada["id"])
    regenerated = client.post(f"/api/v1/messages/{first_ada['id']}/regenerate", headers=headers, json={}).json()
    output = wait_job(client, headers, regenerated["id"])["output"]
    assert [m["id"] for m in output["messages"]] == [first_ada["id"]]
    assert "roleplaying Ada" in provider.received_chat[-1][0]["content"]

    branch = client.post(f"/api/v1/conversations/{group['id']}/branch", headers=headers, json={"message_id": messages[-1]["id"]}).json()
    assert branch["character_ids"] == [ada["id"], ben["id"]]
    assert {m["character_id"] for m in client.get(f"/api/v1/conversations/{branch['id']}/messages", headers=headers).json() if m["role"] == "assistant"} == {ada["id"], ben["id"]}

    # Deleting the first member keeps the chat with the remaining character.
    assert client.delete(f"/api/v1/characters/{ada['id']}", headers=headers).status_code == 200
    remaining = client.get(f"/api/v1/conversations/{group['id']}", headers=headers).json()
    assert remaining["character_id"] == ben["id"] and remaining["character_ids"] == [ben["id"]]


def test_group_with_a_minor_keeps_standard_rules(service):
    client, _, provider = service
    headers, _, _ = register(client)
    client.put("/api/v1/me/adult-content", headers=headers, json={"enabled": True, "confirm_adult": True})
    adult, young = make_character(client, headers, "Ada"), make_character(client, headers, "Kim", age=15)
    group = client.post("/api/v1/group-conversations", headers=headers, json={"character_ids": [adult["id"], young["id"]]}).json()
    turn(client, headers, group, "Ada, hi")
    assert "consenting adults" not in provider.received_chat[-1][0]["content"]


def test_avatar_jobs_use_their_own_quota_and_return_an_image(service):
    client, _, provider = service
    headers, _, _ = register(client)
    draft = {"name": "Mira", "description": "A painter", "age": 31, "appearance": "Short red hair, green coat", "prompt": "in her studio"}
    for _ in range(2):
        job = client.post("/api/v1/avatar-jobs", headers=headers, json=draft)
        assert job.status_code == 202, job.text
        result = wait_job(client, headers, job.json()["id"])
        assert result["status"] == "completed" and result["output"]["assets"][0]["kind"] == "image"
    assert provider.received_images[-1]["appearance"] == "Short red hair, green coat"
    assert client.post("/api/v1/avatar-jobs", headers=headers, json={**draft, "age": -1}).status_code == 422


def test_ai_character_skips_the_ai_portrait_when_the_creator_uploads_one(service):
    client, _, provider = service
    headers, _, _ = register(client)
    job = client.post("/api/v1/characters/generate", headers=headers, json={"idea": "A sailor", "mode": "assisted", "language": "en", "portrait": False}).json()
    result = wait_job(client, headers, job["id"])
    assert result["status"] == "completed" and result["output"]["character"]["avatar_asset_id"] is None
    assert provider.received_images == []


def test_adult_public_characters_are_only_listed_for_confirmed_adults(service):
    client, _, _ = service
    alice, _, _ = register(client, "alice")
    shared = client.post("/api/v1/characters", headers=alice, json={"name": "Vex", "description": "An explicit adult character", "profile": {"age": 30, "fictional": True}, "visibility": "public"}).json()
    wait_job(client, alice, client.get("/api/v1/jobs", headers=alice).json()[0]["id"])
    assert [c["id"] for c in client.get("/api/v1/library").json()] == []
    bob, _, _ = register(client, "bob")
    assert client.get(f"/api/v1/characters/{shared['id']}", headers=bob).status_code == 404
    assert client.post("/api/v1/conversations", headers=bob, json={"character_id": shared["id"], "title": "x"}).status_code == 404
    client.put("/api/v1/me/adult-content", headers=bob, json={"enabled": True, "confirm_adult": True})
    assert [c["id"] for c in client.get("/api/v1/library", headers=bob).json()] == [shared["id"]]
    assert client.get(f"/api/v1/characters/{shared['id']}", headers=bob).status_code == 200


def test_limit_errors_name_the_limit_and_when_it_resets(service):
    from chatabae.auth import quota_message
    assert quota_message("imageday:user", 3, 86400, 5400) == "Daily image limit reached (3 per day). Try again in 1 h 30 min."
    assert quota_message("chatmin:user", 4, 60, 12) == "Message limit reached (4 per minute). Try again in 1 min."
    client, _, _ = service
    headers, _, _ = register(client)
    character = make_character(client, headers, "Ada")
    convo = client.post("/api/v1/conversations", headers=headers, json={"character_id": character["id"], "title": "x"}).json()
    assert client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "Portrait"}).status_code == 202
    second = client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "Portrait"})
    assert second.status_code == 429 and second.json()["detail"].startswith("Image limit reached (1 per 5 minutes)")


def test_characters_send_photos_on_their_own_and_the_tag_is_not_saved(service):
    from chatabae.jobs import split_photo
    assert split_photo("Look!\n[photo: me at the beach]") == ("Look!", "me at the beach")
    assert split_photo("No photo here [photo: x]. More text") == ("No photo here [photo: x]. More text", None)
    client, _, provider = service
    headers, _, _ = register(client)
    character = make_character(client, headers, "Ada")
    convo = client.post("/api/v1/conversations", headers=headers, json={"character_id": character["id"], "title": "x"}).json()
    provider.reply_tokens = ["Here, just for you!", "\n[photo: a selfie on the beach at sunset]"]
    job = turn(client, headers, convo, "What are you doing?")
    assert job["output"]["message"]["content"] == "Here, just for you!" and "PHOTO" in provider.received_chat[-1][0]["content"].upper()
    photo = wait_job(client, headers, job["output"]["image_job"]["id"])
    assert photo["status"] == "completed" and provider.composed[-1]["request"] == "a selfie on the beach at sunset"


def test_messages_can_be_sent_while_an_image_is_generating(service):
    client, _, provider = service
    headers, _, _ = register(client)
    character = make_character(client, headers, "Ada")
    convo = client.post("/api/v1/conversations", headers=headers, json={"character_id": character["id"], "title": "x"}).json()
    provider.image_delay = 0.5
    image = client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "Portrait"}).json()
    message = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Hi while you paint"})
    assert message.status_code == 202
    assert wait_job(client, headers, message.json()["job"]["id"])["status"] == "completed"
    assert wait_job(client, headers, image["id"])["status"] == "completed"


def test_admin_accounts_have_no_limits_and_can_backfill_portraits(service):
    from fastapi.testclient import TestClient
    from chatabae.app import create_admin_app
    client, app, _ = service
    app.state.runtime.settings.admin_usernames = ["alice"]
    headers, _, _ = register(client, "alice")
    character = make_character(client, headers, "Ada")
    convo = client.post("/api/v1/conversations", headers=headers, json={"character_id": character["id"], "title": "x"}).json()
    for _ in range(4):
        job = client.post(f"/api/v1/conversations/{convo['id']}/images", headers=headers, json={"prompt": "Portrait"})
        assert job.status_code == 202, job.text
        wait_job(client, headers, job.json()["id"])
    with TestClient(create_admin_app(app.state.runtime.settings, app)) as admin:
        queued = admin.post("/internal/portraits", headers={"Authorization": "Bearer test-control-secret"}).json()["queued"]
    assert [entry["character_id"] for entry in queued] == [character["id"]]
    assert wait_job(client, headers, queued[0]["job_id"])["status"] == "completed"
    assert client.get(f"/api/v1/characters/{character['id']}", headers=headers).json()["avatar_asset_id"]


def test_template_markers_are_removed_and_history_never_ends_on_a_picture(service):
    from chatabae.db import Message
    from chatabae.jobs import clean_reply
    assert clean_reply("assistant\n<think>\n</think>\n\nOh, bold of you.") == "Oh, bold of you."
    assert clean_reply("Fine<|im_end|>") == "Fine"
    client, app, provider = service
    headers, _, _ = register(client)
    character = make_character(client, headers, "Elena")
    convo = client.post("/api/v1/conversations", headers=headers, json={"character_id": character["id"], "title": "x"}).json()
    first = turn(client, headers, convo, "Hi")
    # A picture that finishes after the newest user message is stored as an empty assistant message later in time.
    with app.state.runtime.db.sessions() as db:
        user_id = db.get(Message, first["output"]["message"]["id"]).user_id
        db.add(Message(user_id=user_id, conversation_id=convo["id"], role="assistant", content="", created_at=time.time() + 5))
        db.commit()
    message = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Still there?"}).json()
    wait_job(client, headers, message["job"]["id"])
    sent = provider.received_chat[-1]
    assert sent[-1] == {"role": "user", "content": "Still there?"} and all(entry["content"] for entry in sent)
    provider.reply_tokens = ["assistant\n<think>\n</think>\n\n", "Hey you."]
    assert turn(client, headers, convo, "Hello again")["output"]["message"]["content"] == "Hey you."
