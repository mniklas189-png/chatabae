"""Real local API/inference acceptance check; creates and removes its own QA account."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit

import httpx


def field(page: str, name: str):
    match = re.search(r'name="' + re.escape(name) + r'" value="([^"]+)"', page)
    if not match:
        raise RuntimeError("Expected backend form field is missing: " + name)
    return html.unescape(match.group(1))


def require(response, code=200):
    if response.status_code != code:
        # Do not print HTML, cookies, authorization codes or bearer credentials.
        detail = ""
        if "application/json" in response.headers.get("content-type", ""):
            detail = str(response.json().get("detail", ""))[:200]
        raise RuntimeError(f"Unexpected HTTP {response.status_code}, expected {code}: {detail}")
    return response


def wait_job(client, identifier, timeout=150):
    start = time.monotonic()
    with client.stream("GET", f"/api/v1/jobs/{identifier}/events", timeout=timeout) as response:
        require(response)
        tokens = 0
        event = ""
        result = {}
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
                if event in {"token", "delta"}:
                    tokens += 1
                elif event == "completed":
                    result = data.get("output", {})
                    break
                elif event in {"failed", "cancelled", "auth_expired"}:
                    raise RuntimeError("Real generation failed: " + str(data.get("error", event))[:200])
        if not result:
            raise RuntimeError("Generation ended without a persisted result")
    return result, {"seconds": round(time.monotonic() - start, 2), "stream_chunks": tokens}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:7810")
    parser.add_argument("--frontend", default="http://127.0.0.1:5173/")
    parser.add_argument("--allow-online", action="store_true", help="Explicitly test your configured HTTPS Funnel API with a disposable QA account")
    parser.add_argument("--image", action="store_true", help="Also generate one real fast image (several minutes of GPU time)")
    args = parser.parse_args()
    if urlsplit(args.api).hostname not in {"127.0.0.1", "localhost"}:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        private_dir = Path(json.loads((root / "config/local.json").read_text())["data_dir"])
        configured = json.loads((private_dir / "config.json").read_text())["public_api_url"]
        if not args.allow_online or args.api.rstrip("/") != configured.rstrip("/") or urlsplit(args.api).scheme != "https":
            raise SystemExit("Online QA requires --allow-online and this installation's configured HTTPS Funnel API.")
    frontend_parts = urlsplit(args.frontend)
    origin = f"{frontend_parts.scheme}://{frontend_parts.netloc}"
    reports = {}
    with httpx.Client(base_url=args.api, timeout=30, follow_redirects=False) as client:
        status = require(client.get("/api/v1/status")).json()
        if status.get("mode") != "local" and not args.allow_online:
            raise RuntimeError("QA account creation is allowed only in local mode")
        verifier = secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        state = secrets.token_urlsafe(24)
        query = {"client_id": "chatabae", "redirect_uri": args.frontend, "code_challenge": challenge, "code_challenge_method": "S256", "state": state, "mode": "register"}
        form_response = require(client.get("/auth/authorize", params=query))
        form = form_response.text
        # Browsers send `Origin: null` when posting a form from a no-referrer page; mimic that instead of a forged origin.
        form_origin = "null" if form_response.headers.get("referrer-policy", "").strip() == "no-referrer" else args.api.rstrip("/")
        account = "qa_" + secrets.token_hex(4)
        response = require(client.post("/auth/register", data={"username": account, "password": secrets.token_urlsafe(32), "flow": field(form, "flow"), "csrf": field(form, "csrf")}, headers={"Origin": form_origin}))
        saved = re.search(r'id="continue" href="([^"]+)"', response.text)
        if not saved:
            raise RuntimeError("Registration did not display recovery codes")
        redirect = require(client.get(html.unescape(saved.group(1))), 303)
        returned = parse_qs(urlsplit(redirect.headers["location"]).query)
        if returned.get("state", [None])[0] != state:
            raise RuntimeError("PKCE state was not preserved")
        auth = require(client.post("/api/v1/auth/exchange", json={"code": returned["code"][0], "code_verifier": verifier, "redirect_uri": args.frontend}, headers={"Origin": origin})).json()
        if "refresh_token" in auth:
            raise RuntimeError("Refresh credential must not be exposed to JavaScript")
        client.headers.update({"Authorization": "Bearer " + auth["access_token"], "Origin": origin})
        try:
            require(client.get("/api/v1/me"))
            character = require(client.post("/api/v1/characters", json={"name": "Lea", "description": "Eine freundliche fiktive Astronomin.", "profile": {"age": 27, "fictional": True, "personality": "Freundlich und neugierig", "background": "Forscht über Sterne", "instructions": "Antworte kurz und natürlich."}, "language": "de", "voice": "piper:de_DE-thorsten-medium", "visibility": "private"}), 201).json()
            conversation = require(client.post("/api/v1/conversations", json={"character_id": character["id"], "title": "Disposable local integration check"}), 201).json()
            turn = require(client.post(f"/api/v1/conversations/{conversation['id']}/messages", json={"content": "Begrüße mich mit einem kurzen Satz auf Deutsch.", "generation": {"temperature": 0.5, "max_tokens": 64, "top_p": 0.8}}), 202).json()
            output, timing = wait_job(client, turn["job"]["id"])
            if not output.get("message", {}).get("content") or timing["stream_chunks"] == 0:
                raise RuntimeError("Real chat did not produce streamed text")
            reports["chat"] = timing
            messages = require(client.get(f"/api/v1/conversations/{conversation['id']}/messages")).json()
            if len(messages) < 2:
                raise RuntimeError("Chat history was not persisted")
            require(client.post(f"/api/v1/conversations/{conversation['id']}/memories", json={"content": "Ich interessiere mich für Sterne.", "enabled": True}), 201)
            profile_job = require(client.post("/api/v1/characters/generate", json={"idea": "Ein fiktiver freundlicher erwachsener Reisebegleiter namens Ben, der gerne wandert.", "mode": "assisted", "language": "de", "visibility": "private"}), 202).json()
            profile_result, timing = wait_job(client, profile_job["id"])
            if not profile_result.get("character", {}).get("name"):
                raise RuntimeError("AI-assisted character creation returned no profile")
            profile_fields = profile_result["character"]["profile"]
            if not all(isinstance(profile_fields.get(key), str) for key in ("gender", "appearance", "personality", "background", "interests", "communication_style", "relationship", "instructions")):
                raise RuntimeError("AI profile did not preserve the editor field contract")
            reports["profile"] = timing
            speech_request = {"text": "Hallo, ich freue mich auf unser Gespräch.", "voice": "piper:de_DE-thorsten-medium", "language": "de", "speed": 1.0}
            speech_job = require(client.post(f"/api/v1/conversations/{conversation['id']}/speech", json=speech_request), 202).json()
            speech_result, timing = wait_job(client, speech_job["id"])
            media = require(client.get("/api/v1/assets")).json()
            audio = next((asset for asset in media if asset["kind"] == "audio"), None)
            if not audio:
                raise RuntimeError("Speech job did not store an audio asset")
            wav = require(client.get(f"/api/v1/assets/{audio['id']}/content"))
            if not wav.content.startswith(b"RIFF"):
                raise RuntimeError("Stored audio is not a valid WAV container")
            reports["speech"] = {**timing, "audio_bytes": len(wav.content)}
            repeated = require(client.post(f"/api/v1/conversations/{conversation['id']}/speech", json=speech_request), 202).json()
            repeated_result, _ = wait_job(client, repeated["id"])
            if not repeated_result.get("cached") or repeated_result["assets"][0]["id"] != speech_result["assets"][0]["id"]:
                raise RuntimeError("Identical speech did not reuse the private audio cache")
            reports["speech_cache"] = True
            if args.image:
                image_job = require(client.post(f"/api/v1/conversations/{conversation['id']}/images", json={"prompt": "Eine freundliche Astronomin mit Teleskop unter dem Sternenhimmel", "options": {"preset": "fast", "width": 512, "height": 512}}), 202).json()
                image_result, timing = wait_job(client, image_job["id"], timeout=900)
                stored = image_result.get("assets") or []
                if not stored or stored[0].get("kind") != "image":
                    raise RuntimeError("Image job did not store an image asset")
                picture = require(client.get(stored[0]["url"]))
                if not picture.content.startswith((b"\x89PNG", b"\xff\xd8", b"RIFF")):
                    raise RuntimeError("Stored image has an unexpected format")
                reports["image"] = {**timing, "image_bytes": len(picture.content)}
            require(client.get("/api/v1/me/export"))
            reports["persistence"] = True
            reports["pkce_cookie_only"] = True
        finally:
            require(client.delete("/api/v1/me"))
            if client.get("/api/v1/me").status_code != 401:
                raise RuntimeError("Deleted account retained access")
    print(json.dumps({"real_api_check": "passed", "transport": "public_https" if args.allow_online else "loopback", "checks": reports, "qa_account_removed": True}, indent=2))


if __name__ == "__main__":
    main()
