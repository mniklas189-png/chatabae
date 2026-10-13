"""One process owns the public gateway and a separate loopback admin listener."""
import argparse
import asyncio
import contextlib
import logging
import signal

import uvicorn

from .app import create_admin_app, create_app
from .config import load_settings


async def serve(args):
    settings = load_settings()
    settings.port, settings.admin_port = args.port or settings.port, args.admin_port or settings.admin_port
    public = create_app(settings)
    admin = create_admin_app(settings, public)
    servers = [uvicorn.Server(uvicorn.Config(public, host=args.host, port=settings.port, access_log=False, proxy_headers=False, limit_concurrency=64)), uvicorn.Server(uvicorn.Config(admin, host="127.0.0.1", port=settings.admin_port, access_log=False, proxy_headers=False, limit_concurrency=8))]
    for server in servers:
        # A single outer handler controls both listeners and the common lifespan.
        server.capture_signals = contextlib.nullcontext
    def stop(*_):
        for server in servers:
            server.should_exit = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, stop)
    await asyncio.gather(*(server.serve() for server in servers))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1"])
    parser.add_argument("--port", type=int)
    parser.add_argument("--admin-port", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve(args))


if __name__ == "__main__":
    main()
