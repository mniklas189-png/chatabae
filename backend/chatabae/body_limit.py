import asyncio
import time

from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    """Bound actual received bytes, including requests without Content-Length."""
    def __init__(self, app, upload_bytes, voice_upload_bytes=None):
        self.app = app
        self.upload_bytes = upload_bytes
        self.voice_upload_bytes = voice_upload_bytes or upload_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        upload_limit = self.voice_upload_bytes if scope.get("path") == "/api/v1/voice-references" else self.upload_bytes
        limit = upload_limit + 1024 * 1024 if b"multipart/form-data" in headers.get(b"content-type", b"") else 128 * 1024
        messages, total, deadline = [], 0, time.monotonic() + 20
        try:
            while True:
                message = await asyncio.wait_for(receive(), max(0.01, deadline - time.monotonic()))
                if message["type"] == "http.disconnect":
                    return
                total += len(message.get("body", b""))
                if total > limit:
                    await JSONResponse({"detail": "Request body too large"}, 413)(scope, receive, send)
                    return
                messages.append(message)
                if not message.get("more_body", False):
                    break
        except TimeoutError:
            await JSONResponse({"detail": "Request body timed out"}, 408)(scope, receive, send)
            return
        iterator = iter(messages)
        async def replay():
            return next(iterator, None) or await receive()
        await self.app(scope, replay, send)
