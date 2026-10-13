from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from .db import AuthCode, AuthSession, Job, Quota, RecoveryCode, SpentRefresh, User
from .schemas import CodeExchange, RefreshRequest, TokenResponse, UserResponse

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
USERNAME = re.compile(r"^[a-z0-9_]{3,40}$")
AUTH_STYLE = "body{background:#101116;color:#f5f2ef;font:16px system-ui;margin:0;display:grid;min-height:100vh;place-items:center}main{box-sizing:border-box;width:min(420px,calc(100vw - 32px));padding:clamp(20px,6vw,32px);border:1px solid #343640;border-radius:24px}input,button{box-sizing:border-box;width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #454653;background:#191b23;color:inherit}button{background:#ec956d;color:#18110e;font-weight:700}a{color:#ec956d}label{display:block}li{margin:10px 0}code{font-size:15px;word-break:break-all}"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def pkce(value: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).rstrip(b"=").decode()


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def runtime(request: Request):
    return request.app.state.runtime


def current_user(request: Request) -> User:
    rt = runtime(request)
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    try:
        claims = jwt.decode(header[7:], rt.secret, algorithms=["HS256"], audience="chatabae", options={"require": ["exp", "sub", "sid"]})
        if claims.get("typ") != "access":
            raise ValueError("Wrong token type")
        with rt.db.sessions() as db:
            session = db.get(AuthSession, claims["sid"])
            user = db.get(User, claims["sub"])
            if not session or session.revoked or session.expires_at < time.time() or session.user_id != claims["sub"] or not user or user.banned:
                raise ValueError("Session expired")
            rt.recent_visitors[user.id] = time.monotonic()
            return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Session expired; sign in again") from None


def user_json(user: User):
    return {"id": user.id, "username": user.username, "adult_content": user.adult_confirmed_at is not None}


def reserve_quota(db, key: str, limit: int, window: int):
    bucket = f"{key}:{int(time.time() // window)}"
    entry = db.get(Quota, bucket)
    if entry and entry.count >= limit:
        raise HTTPException(429, "Rate limit reached", headers={"Retry-After": str(window - int(time.time()) % window)})
    if entry:
        entry.count += 1
    else:
        db.add(Quota(key=bucket, count=1))


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    # Only Tailscale's loopback reverse-proxy is trusted; never trust an arbitrary chain.
    if peer in {"127.0.0.1", "::1"} and request.headers.get("tailscale-funnel-request"):
        forwarded = request.headers.get("x-forwarded-for", "")
        import ipaddress
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return peer


def cookie_name(rt):
    return "__Host-chatabae_refresh" if rt.settings.secure_cookies else "chatabae_refresh"


def set_refresh(response: Response, rt, token: str):
    settings = rt.settings
    attrs = f"{cookie_name(rt)}={token}; Path=/; Max-Age={settings.refresh_seconds}; HttpOnly"
    attrs += "; Secure; SameSite=None; Partitioned" if settings.secure_cookies else "; SameSite=Lax"
    response.headers.append("Set-Cookie", attrs)
    response.headers["Cache-Control"] = "no-store"


def token_pair(rt, db, user: User, session: AuthSession | None = None):
    token = secrets.token_urlsafe(48)
    if session is None:
        session = AuthSession(user_id=user.id, refresh_hash=digest(token), expires_at=time.time() + rt.settings.refresh_seconds)
        db.add(session)
        db.flush()
    else:
        db.add(SpentRefresh(token_hash=session.refresh_hash, session_id=session.id, expires_at=session.expires_at))
        session.previous_hash = session.refresh_hash
        session.refresh_hash = digest(token)
    access = jwt.encode({"typ": "access", "sub": user.id, "sid": session.id, "aud": "chatabae", "iat": int(time.time()), "exp": int(time.time()) + rt.settings.access_seconds}, rt.secret, algorithm="HS256")
    return {"access_token": access, "token_type": "bearer", "expires_in": rt.settings.access_seconds, "refresh_token": token, "user": user_json(user)}


def check_browser_origin(request, rt, required=False):
    value = request.headers.get("origin")
    allowed = set(rt.settings.allowed_origins) | {origin(rt.settings.public_api_url)}
    if (required and not value) or (value and value not in allowed):
        raise HTTPException(403, "Origin not allowed")


def make_auth_router():
    router = APIRouter()

    def flow(request, client_id, redirect_uri, code_challenge, code_challenge_method, state):
        rt = runtime(request)
        if client_id != "chatabae" or redirect_uri != rt.settings.frontend_url or code_challenge_method != "S256" or not re.fullmatch(r"[A-Za-z0-9_-]{43}", code_challenge) or not re.fullmatch(r"[A-Za-z0-9._~-]{16,128}", state):
            raise HTTPException(400, "Invalid authorization request")
        return jwt.encode({"typ": "flow", "redirect_uri": redirect_uri, "challenge": code_challenge, "state": state, "exp": int(time.time()) + 600}, rt.secret, algorithm="HS256")

    def decode_flow(request, value):
        try:
            data = jwt.decode(value, runtime(request).secret, algorithms=["HS256"])
            if data.get("typ") != "flow":
                raise ValueError()
            return data
        except (jwt.PyJWTError, ValueError):
            raise HTTPException(400, "Authorization request expired") from None

    def finish(request, db, user, data):
        code = secrets.token_urlsafe(32)
        session = AuthSession(user_id=user.id, refresh_hash=digest(secrets.token_urlsafe(48)), expires_at=time.time() + runtime(request).settings.refresh_seconds)
        db.add(session)
        db.flush()
        db.add(AuthCode(code_hash=digest(code), user_id=user.id, session_id=session.id, challenge=data["challenge"], redirect_uri=data["redirect_uri"], expires_at=time.time() + 60))
        db.commit()
        sep = "&" if "?" in data["redirect_uri"] else "?"
        response = RedirectResponse(data["redirect_uri"] + sep + urlencode({"code": code, "state": data["state"]}), status_code=303)
        login = jwt.encode({"typ": "login", "sub": user.id, "sid": session.id, "exp": int(time.time()) + 86400}, runtime(request).secret, algorithm="HS256")
        response.set_cookie("chatabae_login", login, max_age=86400, httponly=True, secure=runtime(request).settings.secure_cookies, samesite="lax", path="/auth")
        response.headers["Cache-Control"] = "no-store"
        return response

    def form_page(request, flow_token, *, register=False, error=""):
        csrf = secrets.token_urlsafe(32)
        action = "register" if register else "login"
        safe_flow = html.escape(flow_token, quote=True)
        other = "login" if register else "register"
        other_url = f"/auth/{other}?flow={safe_flow}"
        body = f'''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chatabae · Anmeldung</title><style>body{{background:#101116;color:#f5f2ef;font:16px system-ui;margin:0;display:grid;min-height:100vh;place-items:center}}main{{box-sizing:border-box;width:min(380px,calc(100vw - 32px));padding:clamp(20px,6vw,32px);border:1px solid #343640;border-radius:24px}}input,button{{box-sizing:border-box;width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #454653;background:#191b23;color:inherit}}button{{background:#ec956d;color:#18110e;font-weight:700}}a{{color:#ec956d}}.error{{color:#ffaaa0}}</style><main><h1>Chatabae</h1><p>{"Kostenloses Konto erstellen" if register else "Willkommen zurück"}</p><p class="error">{html.escape(error)}</p><form action="/auth/{action}" method="post"><input type="hidden" name="flow" value="{safe_flow}"><input type="hidden" name="csrf" value="{csrf}"><label>Benutzername<input name="username" autocomplete="username" pattern="[a-zA-Z0-9_]{{3,40}}" minlength="3" maxlength="40" required></label><label>Passwort<input type="password" name="password" autocomplete="{"new-password" if register else "current-password"}" minlength="12" maxlength="128" required></label><button>{"Konto erstellen" if register else "Anmelden"}</button></form><p><a href="{other_url}">{"Schon registriert? Anmelden" if register else "Neues Konto erstellen"}</a></p><p><a href="/auth/recover?flow={safe_flow}">Passwort mit Recovery-Code zurücksetzen</a></p><small>Keine sexualisierten Minderjährigen, Täuschung oder Belästigung. Deine Daten liegen auf dem privaten Server des Betreibers.</small></main></html>'''
        response = HTMLResponse(body)
        response.set_cookie("chatabae_csrf", csrf, max_age=600, httponly=True, secure=runtime(request).settings.secure_cookies, samesite="strict", path="/auth")
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        # "no-referrer" would make browsers send `Origin: null` on the form POST, which the origin check rejects.
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    def recovery_saved_page(request, codes, data, login_response):
        url = "/auth/authorize?" + urlencode({"client_id": "chatabae", "redirect_uri": data["redirect_uri"], "code_challenge": data["challenge"], "code_challenge_method": "S256", "state": data["state"]})
        entries = "".join(f"<li><code>{html.escape(code)}</code></li>" for code in codes)
        response = HTMLResponse(f'<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Recovery-Codes sichern</title><style>{AUTH_STYLE}</style><body><main><h1>Recovery-Codes sichern</h1><p>Diese Codes werden nur einmal angezeigt. Bewahre sie sicher auf. Jeder Code kann dein Passwort einmal zurücksetzen.</p><ul>{entries}</ul><a id="continue" href="{html.escape(url, quote=True)}">Gesichert — weiter zu Chatabae</a></main></body></html>')
        for key, value in login_response.raw_headers:
            if key.lower() == b"set-cookie":
                response.raw_headers.append((key, value))
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @router.get("/auth/recover")
    async def recovery_page(request: Request, flow: str):
        decode_flow(request, flow)
        csrf = secrets.token_urlsafe(32)
        response = HTMLResponse(f'<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Passwort zurücksetzen</title><style>{AUTH_STYLE}</style><body><main><h1>Passwort zurücksetzen</h1><p>Nutze einen deiner gesicherten Codes. Alte Sitzungen werden geschlossen.</p><form method="post" action="/auth/recover"><input type="hidden" name="flow" value="{html.escape(flow, quote=True)}"><input type="hidden" name="csrf" value="{csrf}"><label>Benutzername<input name="username" required maxlength="40"></label><label>Recovery-Code<input name="recovery_code" required maxlength="100" autocomplete="off"></label><label>Neues Passwort<input name="password" type="password" minlength="12" maxlength="128" required autocomplete="new-password"></label><button>Passwort zurücksetzen</button></form></main></body></html>')
        response.set_cookie("chatabae_csrf", csrf, max_age=600, httponly=True, secure=runtime(request).settings.secure_cookies, samesite="strict", path="/auth")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        # "no-referrer" would make browsers send `Origin: null` on the form POST, which the origin check rejects.
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @router.post("/auth/recover")
    async def recover(request: Request, username: str = Form(...), recovery_code: str = Form(...), password: str = Form(...), flow: str = Form(...), csrf: str = Form(...)):
        rt = runtime(request)
        check_browser_origin(request, rt)
        if not secrets.compare_digest(csrf, request.cookies.get("chatabae_csrf", "")) or not 12 <= len(password) <= 128:
            raise HTTPException(403, "Invalid recovery form")
        data = decode_flow(request, flow)
        async with rt.admission_lock:
            with rt.db.sessions() as db:
                reserve_quota(db, f"recovery:{client_ip(request)}", 5, 900)
                db.commit()
        async with rt.hash_slots:
            password_hash = await asyncio.to_thread(hasher.hash, password)
        async with rt.admission_lock:
            with rt.db.sessions() as db:
                user = db.scalar(select(User).where(User.username == username.strip().lower()))
                code = db.get(RecoveryCode, digest(recovery_code.strip()))
                if not user or user.banned or not code or code.used or code.user_id != user.id:
                    raise HTTPException(400, "Recovery failed")
                code.used = True
                user.password_hash = password_hash
                for family in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all():
                    family.revoked = True
                rt.cancel_user_jobs(db, user.id)
                db.commit()
                rt.recent_visitors.pop(user.id, None)
                return finish(request, db, user, data)

    @router.get("/auth/authorize")
    async def authorize(request: Request, client_id: str, redirect_uri: str, code_challenge: str, code_challenge_method: str, state: str, mode: str = "login"):
        token = flow(request, client_id, redirect_uri, code_challenge, code_challenge_method, state)
        if mode == "register":
            return form_page(request, token, register=True)
        login = request.cookies.get("chatabae_login")
        if login:
            try:
                claims = jwt.decode(login, runtime(request).secret, algorithms=["HS256"])
                if claims.get("typ") == "login":
                    with runtime(request).db.sessions() as db:
                        user = db.get(User, claims.get("sub"))
                        login_session = db.get(AuthSession, claims.get("sid"))
                        if user and not user.banned and login_session and not login_session.revoked and login_session.user_id == user.id and login_session.expires_at > time.time():
                            return finish(request, db, user, decode_flow(request, token))
            except jwt.PyJWTError:
                pass
        return form_page(request, token)

    @router.get("/auth/login")
    async def login_page(request: Request, flow: str):
        decode_flow(request, flow)
        return form_page(request, flow)

    @router.get("/auth/register")
    async def register_page(request: Request, flow: str):
        decode_flow(request, flow)
        return form_page(request, flow, register=True)

    async def credentials(request, username, password, flow_token, csrf, register):
        rt = runtime(request)
        check_browser_origin(request, rt)
        if not secrets.compare_digest(csrf, request.cookies.get("chatabae_csrf", "")):
            raise HTTPException(403, "Invalid form token")
        data = decode_flow(request, flow_token)
        username = username.strip().lower()
        if not USERNAME.fullmatch(username) or not 12 <= len(password) <= 128:
            return form_page(request, flow_token, register=register, error="Benutzername: 3–40 Zeichen. Passwort: mindestens 12 Zeichen.")
        async with rt.admission_lock:
            with rt.db.sessions() as db:
                reserve_quota(db, f"login:{client_ip(request)}:{username}", 5, 900)
                reserve_quota(db, f"loginip:{client_ip(request)}", 10, 900)
                if register:
                    if not rt.settings.registration_enabled:
                        raise HTTPException(403, "Registration is closed")
                    reserve_quota(db, f"register:{client_ip(request)}", 3, 3600)
                    reserve_quota(db, f"registerday:{client_ip(request)}", 10, 86400)
                db.commit()
        with rt.db.sessions() as db:
            user = db.scalar(select(User).where(User.username == username))
            if register:
                if user:
                    return form_page(request, flow_token, register=True, error="Dieser Benutzername ist nicht verfügbar.")
                async with rt.hash_slots:
                    password_hash = await asyncio.to_thread(hasher.hash, password)
                user = User(username=username, password_hash=password_hash)
                db.add(user)
                try:
                    db.flush()
                except IntegrityError:
                    db.rollback()
                    return form_page(request, flow_token, register=True, error="Dieser Benutzername ist nicht verfügbar.")
                recovery_codes = [secrets.token_hex(16) for _ in range(8)]
                for recovery_code in recovery_codes:
                    db.add(RecoveryCode(user_id=user.id, code_hash=digest(recovery_code)))
            else:
                # A dummy Argon2 operation avoids a cheap username-existence timing oracle.
                if user is None:
                    async with rt.hash_slots:
                        await asyncio.to_thread(hasher.hash, password)
                    return form_page(request, flow_token, error="Anmeldung fehlgeschlagen.")
                try:
                    async with rt.hash_slots:
                        await asyncio.to_thread(hasher.verify, user.password_hash, password)
                except VerificationError:
                    return form_page(request, flow_token, error="Anmeldung fehlgeschlagen.")
                if user.banned:
                    return form_page(request, flow_token, error="Anmeldung fehlgeschlagen.")
            response = finish(request, db, user, data)
            return recovery_saved_page(request, recovery_codes, data, response) if register else response

    @router.post("/auth/login")
    async def login(request: Request, username: str = Form(...), password: str = Form(...), flow: str = Form(...), csrf: str = Form(...)):
        return await credentials(request, username, password, flow, csrf, False)

    @router.post("/auth/register")
    async def register(request: Request, username: str = Form(...), password: str = Form(...), flow: str = Form(...), csrf: str = Form(...)):
        return await credentials(request, username, password, flow, csrf, True)

    @router.post("/api/v1/auth/exchange", response_model=TokenResponse)
    async def exchange(body: CodeExchange, request: Request, response: Response):
        rt = runtime(request)
        check_browser_origin(request, rt)
        async with rt.admission_lock:
            with rt.db.sessions() as db:
                code = db.get(AuthCode, digest(body.code))
                if not code or code.used or code.expires_at < time.time() or code.redirect_uri != body.redirect_uri or not secrets.compare_digest(code.challenge, pkce(body.code_verifier)):
                    raise HTTPException(400, "Authorization code invalid or expired")
                code.used = True
                user = db.get(User, code.user_id)
                if not user or user.banned:
                    raise HTTPException(401, "Account unavailable")
                session = db.get(AuthSession, code.session_id) if code.session_id else None
                if session and session.revoked:
                    raise HTTPException(401, "Session revoked")
                result = token_pair(rt, db, user, session)
                db.commit()
        set_refresh(response, rt, result["refresh_token"])
        result.pop("refresh_token", None)
        return result

    @router.post("/api/v1/auth/refresh", response_model=TokenResponse)
    async def refresh(body: RefreshRequest, request: Request, response: Response):
        rt = runtime(request)
        cookie = request.cookies.get(cookie_name(rt))
        check_browser_origin(request, rt, required=True)
        token = cookie
        if not token:
            raise HTTPException(401, "Reauthorization required")
        async with rt.admission_lock:
            with rt.db.sessions() as db:
                hashed = digest(token)
                spent = db.get(SpentRefresh, hashed)
                if spent:
                    family = db.get(AuthSession, spent.session_id)
                    if family:
                        family.revoked = True
                        rt.cancel_user_jobs(db, family.user_id)
                        db.commit()
                    raise HTTPException(401, "Refresh token reuse detected; reauthorize")
                session = db.scalar(select(AuthSession).where(or_(AuthSession.refresh_hash == hashed, AuthSession.previous_hash == hashed)))
                if not session:
                    raise HTTPException(401, "Session expired")
                if session.previous_hash == hashed:
                    session.revoked = True
                    db.commit()
                    raise HTTPException(401, "Refresh token reuse detected; reauthorize")
                user = db.get(User, session.user_id)
                if session.revoked or session.expires_at < time.time() or not user or user.banned:
                    raise HTTPException(401, "Session expired")
                result = token_pair(rt, db, user, session)
                db.commit()
        set_refresh(response, rt, result["refresh_token"])
        result.pop("refresh_token", None)
        return result

    @router.post("/api/v1/auth/logout")
    async def logout(request: Request, response: Response, user: User = Depends(current_user)):
        rt = runtime(request)
        claims = jwt.decode(request.headers["authorization"][7:], rt.secret, algorithms=["HS256"], audience="chatabae")
        with rt.db.sessions() as db:
            session = db.get(AuthSession, claims["sid"])
            if session:
                session.revoked = True
                rt.cancel_user_jobs(db, user.id)
                db.commit()
        rt.recent_visitors.pop(user.id, None)
        response.delete_cookie(cookie_name(rt), path="/", secure=rt.settings.secure_cookies, httponly=True, samesite="none" if rt.settings.secure_cookies else "lax")
        response.delete_cookie("chatabae_login", path="/auth")
        return {"ok": True}

    @router.get("/api/v1/auth/me", response_model=UserResponse)
    async def me(user: User = Depends(current_user)):
        return user_json(user)

    return router
