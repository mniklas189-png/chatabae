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
