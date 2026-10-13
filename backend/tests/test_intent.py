import pytest

from chatabae.intent import explicit_image_request
from conftest import character_conversation, register, wait_job


@pytest.mark.parametrize("text", ["Erstelle ein Bild von dir im Café.", "Bitte generiere ein Foto von dir.", "Create a picture of yourself in a café.", "Can you draw a portrait of yourself?", "Schick mir ein Selfie von dir.", "Zeig mir ein Foto, wo du gerade bist.", "Send me a pic of you right now", "Please show me a picture of your outfit"])
def test_explicit_image_commands(text):
    assert explicit_image_request(text)


@pytest.mark.parametrize("text", ["Erstelle kein Bild, erzähle eine Geschichte.", "Don't create an image.", "Tell me a story about creating an image.", "Was hältst du von diesem Bild?", "Zeig mir, was du meinst.", "Show me around the city."])
def test_other_chat_is_not_image_generation(text):
    assert not explicit_image_request(text)


def test_image_intent_persists_user_and_assistant_asset_and_checks_public_license(service):
    client, app, provider = service
    headers, _, _ = register(client)
    _, convo = character_conversation(client, headers)
    response = client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Erstelle ein Bild von dir im Café."})
    assert response.status_code == 202 and response.json()["job"]["kind"] == "image"
    completed = wait_job(client, headers, response.json()["job"]["id"])
    assert completed["status"] == "completed"
    assert completed["output"]["message"]["assets"][0]["kind"] == "image"
    messages = client.get(f"/api/v1/conversations/{convo['id']}/messages", headers=headers).json()
    assert len(messages) == 2 and messages[1]["assets"]
    app.state.runtime.settings.mode = "online"
    assert client.post(f"/api/v1/conversations/{convo['id']}/messages", headers=headers, json={"content": "Create a picture of yourself."}).status_code == 403
    assert len(client.get(f"/api/v1/conversations/{convo['id']}/messages", headers=headers).json()) == 2
