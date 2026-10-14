import pytest

from chatabae.jobs import ADULT_CHAT_RULES, MINOR_RULES
from chatabae.persona import chat_persona, read_statements
from conftest import character_conversation, register, wait_job


@pytest.mark.parametrize("text, expected", [
    ("*hi my name is tom and im 16*", {"name": "Tom", "age": 16, "minor": True}),
    ("ich heiße Lena und bin 25.", {"name": "Lena", "age": 25}),
    ("im tom im 16 your 17 and your my nanny", {"age": 16, "minor": True}),
    ("du bist 17", {"minor": True}),
    ("i'm sixteen", {"age": 16, "minor": True}),
    ("ur 2 hot", {}),
    ("I'm 5 minutes away", {}),
    ("*I put my hand on your thigh*", {}),
    ("my name is not important", {}),
])
def test_statements_about_name_and_age_are_read(text, expected):
    assert read_statements(text) == expected


def test_a_stated_minor_stays_for_the_whole_chat():
    persona = chat_persona({"name": "Max", "age": 30}, {"minor": True}, ["im 25"])
    assert persona == {"name": "Max", "age": 25, "minor": True}
    assert chat_persona({"name": "Max", "age": 30}, None, ["my name is tom"]) == {"name": "Tom", "age": 30}


def test_profile_persona_is_saved_and_survives_display_preferences(service):
    client, _, _ = service
    headers, _, _ = register(client)
    assert client.get("/api/v1/me/persona", headers=headers).json() == {"name": "", "age": None, "about": ""}
    saved = client.put("/api/v1/me/persona", headers=headers, json={"name": "Sam", "age": 27, "about": "Tall, works nights as a barkeeper."})
    assert saved.status_code == 200 and saved.json()["name"] == "Sam"
    assert client.put("/api/v1/preferences", headers=headers, json={"theme": "dark"}).status_code == 200
    assert client.get("/api/v1/me/persona", headers=headers).json()["age"] == 27
    assert client.put("/api/v1/me/persona", headers=headers, json={"age": 200}).status_code == 422


def test_chat_uses_the_profile_persona_and_a_name_given_in_chat(service):
    client, _, provider = service
    headers, _, _ = register(client)
    client.put("/api/v1/me/persona", headers=headers, json={"name": "Sam", "age": 27, "about": "Barkeeper"})
    _, convo = character_conversation(client, headers)
    job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Hey"}).json()["job"]
    assert wait_job(client, headers, job["id"])["status"] == "completed"
    assert "name Sam; age 27; about them: Barkeeper" in provider.received_chat[-1][0]["content"]
    job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "*waves* my name is Jonas"}).json()["job"]
    assert wait_job(client, headers, job["id"])["status"] == "completed"
    assert "name Jonas; age 27" in provider.received_chat[-1][0]["content"]
    assert client.get(f"/api/v1/conversations/{convo['id']}", headers=headers).json()["persona"] == {"name": "Jonas"}


def test_a_user_who_says_they_are_under_18_never_gets_adult_rules(service):
    client, _, provider = service
    headers, _, _ = register(client)
    client.put("/api/v1/me/adult-content", headers=headers, json={"enabled": True, "confirm_adult": True})
    _, convo = character_conversation(client, headers)
    job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Hi"}).json()["job"]
    assert wait_job(client, headers, job["id"])["status"] == "completed"
    assert ADULT_CHAT_RULES in provider.received_chat[-1][0]["content"]
    job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "*hi my name is tom and im 16*"}).json()["job"]
    assert wait_job(client, headers, job["id"])["status"] == "completed"
    system = provider.received_chat[-1][0]["content"]
    assert ADULT_CHAT_RULES not in system and system.endswith(MINOR_RULES)
    # Saying a different age later does not lift the rule for this chat.
    job = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "jk im 25"}).json()["job"]
    assert wait_job(client, headers, job["id"])["status"] == "completed"
    assert provider.received_chat[-1][0]["content"].endswith(MINOR_RULES)
    assert client.get(f"/api/v1/conversations/{convo['id']}", headers=headers).json()["persona"]["minor"] is True
