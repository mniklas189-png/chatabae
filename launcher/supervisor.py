"""One owner for the API, model descendants, development UI, and foreground Funnel."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from .windows import InstanceLock, ProcessJob

ROOT = Path(__file__).resolve().parents[1]


def data_directory() -> Path:
    marker = ROOT / "config/local.json"
    if marker.is_file() and not os.environ.get("CHATABAE_DATA_DIR"):
        return Path(json.loads(marker.read_text(encoding="utf-8"))["data_dir"])
    base = Path.home() / "AppData/Local" if os.name == "nt" else Path.home() / ".local/share"
    return Path(os.environ.get("CHATABAE_DATA_DIR") or (base / "Chatabae")).resolve()


def read_json(url: str, timeout: float = 3, token: str = "", method: str = "GET"):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers, method=method, data=b"{}" if method == "POST" else None)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def port_free(port: int):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"Port {port} ist belegt. Kein automatischer Portwechsel.") from exc


def tail(path: Path, lines: int = 12) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as source:
        source.seek(max(0, path.stat().st_size - 8000))
        return "\n".join(source.read().decode("utf-8", "replace").splitlines()[-lines:])


def find_tailscale() -> str:
    result = shutil.which("tailscale")
    for candidate in (Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tailscale/tailscale.exe",):
        if candidate.is_file():
            result = str(candidate)
    if not result:
        raise RuntimeError("Tailscale fehlt. setup.bat --tailscale installieren, dann einmal anmelden.")
    return result


def tailscale_preflight(executable: str, public_url: str):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    def query(args):
        result = subprocess.run([executable, *args], capture_output=True, text=True, timeout=15, creationflags=flags)
        if result.returncode:
            raise RuntimeError("Tailscale ist nicht bereit: " + result.stderr.strip())
        return json.loads(result.stdout)
    state = query(["status", "--json"])
    if state.get("BackendState") != "Running":
        raise RuntimeError("Tailscale benötigt deine einmalige Anmeldung. setup.bat --tailscale ausführen.")
    expected = "https://" + state.get("Self", {}).get("DNSName", "").rstrip(".")
    if not expected.startswith("https://") or expected == "https://":
        raise RuntimeError("MagicDNS ist nicht bereit.")
    if public_url.rstrip("/") != expected:
        raise RuntimeError(f"Konfigurierte API-Adresse stimmt nicht mit dem Tailscale-Gerät überein. Erwartet: {expected}")
    configuration = query(["serve", "status", "--json"])
    # Never hide a persistent route behind a temporary foreground route.
    for key in ("TCP", "AllowFunnel", "Web"):
        value = configuration.get(key) or {}
        if any(str(item) == "443" or str(item).endswith(":443") for item in value):
            raise RuntimeError("Tailscale-Port 443 ist bereits konfiguriert. Bestehende Freigabe wird nicht verändert.")
    if configuration.get("Foreground"):
        raise RuntimeError("Eine andere Foreground-Serve/Funnel-Sitzung läuft bereits.")


def terminal_status(status: dict, online: bool) -> str:
    queue = status.get("queue", {})
    metrics = status.get("metrics", {})
    gpu, ram = metrics.get("gpu", {}), metrics.get("ram", {})
    gpu_text = f"{gpu['used_mib'] / 1024:.1f}/{gpu['total_mib'] / 1024:.1f} GiB" if gpu.get("available") else "unbekannt"
    ram_text = f"{ram['used_bytes'] / 1024**3:.1f}/{ram['total_bytes'] / 1024**3:.1f} GiB" if ram.get("available") else "unbekannt"
    models = status.get("models", {})
    loaded = [name for name, value in models.items() if isinstance(value, dict) and value.get("ready")]
    return (f"API {status.get('state', '?')} | Funnel {'online' if online else 'aus'} | "
            f"Besucher {status.get('active_visitors', 0)} | Sitzungen {status.get('active_sessions', 0)} | "
            f"Queue {queue.get('queued', 0)} wartend / {queue.get('running', 0)} laufend\n"
            f"VRAM {gpu_text} | RAM {ram_text} | Geladen: {', '.join(loaded) or 'keine'}")


class Supervisor:
    def __init__(self, mode: str, no_frontend: bool = False):
        self.mode, self.no_frontend = mode, no_frontend
        self.directory = data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config_path = Path(os.environ.get("CHATABAE_CONFIG", self.directory / "config.json"))
        if not self.config_path.is_file():
            raise RuntimeError("Konfiguration fehlt. Bitte setup.bat ausführen.")
        self.config = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        self.token = secrets.token_urlsafe(32)
        self.instance_id = secrets.token_hex(12)
        self.stop_event = threading.Event()
        self.job = ProcessJob()
        self.lock = None
        self.control_server = None
        self.api = None
        self.funnel = None
        self.frontend = None
        self.closed = False
        self.control_port = int(self.config.get("control_port", 7813))
        self.api_port = int(self.config.get("port", 7810))
        self.admin_port = int(self.config.get("admin_port", 7811))
        self.runtime_config = self.directory / "runtime-config.json"
        self.console_handler = None

    def start_control(self):
        supervisor = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/stop" or self.headers.get("Origin"):
                    self.send_error(404)
                    return
                supplied = self.headers.get("Authorization", "")
                if not secrets.compare_digest(supplied, "Bearer " + supervisor.token):
                    self.send_error(401)
                    return
                supervisor.stop_event.set()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "11")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            def log_message(self, *_):
                pass
        self.control_server = http.server.ThreadingHTTPServer(("127.0.0.1", self.control_port), Handler)
        threading.Thread(target=self.control_server.serve_forever, daemon=True).start()
        control = self.directory / "control.json"
        control.write_text(json.dumps({"pid": os.getpid(), "port": self.control_port, "token": self.token, "instance_id": self.instance_id}), encoding="utf-8")
        if os.name != "nt":
            control.chmod(0o600)

    def install_handlers(self):
        for name in ("SIGINT", "SIGTERM"):
            signal.signal(getattr(signal, name), lambda *_: self.stop_event.set())
        if os.name == "nt":
            handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
            def handler(event):
                if event in (2, 5, 6):  # window close/logoff/shutdown: no long drain
                    self.stop_event.set()
                    self.job.close()
                    return True
                return False
            self.console_handler = handler_type(handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(self.console_handler, True)

    def wait_ready(self, url: str, process, timeout: float, public: bool = False):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self.stop_event.is_set():
            if process.poll() is not None:
                raise RuntimeError("Ein gestarteter Dienst ist beendet.\n" + tail(self.directory / "logs/api.log"))
            try:
                status = read_json(url, timeout=3)
                if status.get("instance_id") == self.instance_id:
                    chat = status.get("capabilities", {}).get("chat", False)
                    chat_available = bool(chat.get("available")) if isinstance(chat, dict) else bool(chat)
                    if status.get("state") == "ready" and (public or self.mode == "local" or chat_available):
                        return status
            except (OSError, ValueError, urllib.error.URLError):
                pass
            self.stop_event.wait(0.5)
        raise RuntimeError("Start abgebrochen oder Readiness-Zeitlimit überschritten.\n" + tail(self.directory / "logs/api.log"))

    def run(self):
        try:
            self.lock = InstanceLock(self.directory)
            self.install_handlers()
            port_free(self.api_port)
            port_free(self.admin_port)
            port_free(self.control_port)
            if shutil.disk_usage(self.directory).free < 10 * 1024**3:
                raise RuntimeError("Weniger als 10 GiB freier Speicher; Start wird abgebrochen.")
            if self.mode == "online":
                tailscale = find_tailscale()
                tailscale_preflight(tailscale, self.config.get("public_api_url", ""))
                result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                if result.returncode:
                    raise RuntimeError("NVIDIA-GPU ist nicht verfügbar.")
                print("GPU:", result.stdout.strip(), flush=True)
            settings = dict(self.config)
            if self.mode == "local":
                settings.update(frontend_url="http://127.0.0.1:5173/", public_api_url=f"http://127.0.0.1:{self.api_port}",
                                allowed_origins=["http://localhost:5173", "http://127.0.0.1:5173"])
            self.runtime_config.write_text(json.dumps(settings, indent=2), encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=str(ROOT / "backend"), PYTHONUNBUFFERED="1",
                       CHATABAE_CONFIG=str(self.runtime_config), CHATABAE_DATA_DIR=str(self.directory),
                       CHATABAE_MODE=self.mode, CHATABAE_INSTANCE_ID=self.instance_id, CHATABAE_CONTROL_TOKEN=self.token)
            self.start_control()
            print("Chatabae startet. Logs:", self.directory / "logs", flush=True)
            self.api = self.job.spawn([sys.executable, "-m", "chatabae", "--host", "127.0.0.1", "--port", str(self.api_port), "--admin-port", str(self.admin_port)], ROOT, env, self.directory / "logs/api.log")
            local_url = f"http://127.0.0.1:{self.api_port}/api/v1/status"
            self.wait_ready(local_url, self.api, timeout=300)
            if self.mode == "online":
                self.funnel = self.job.spawn([tailscale, "funnel", "--https=443", f"http://127.0.0.1:{self.api_port}"], ROOT, env, self.directory / "logs/funnel.log")
                public_url = self.config["public_api_url"].rstrip("/") + "/api/v1/status"
                self.wait_ready(public_url, self.funnel, timeout=120, public=True)
                print("ONLINE:", self.config["public_api_url"], flush=True)
                print("Website:", self.config["frontend_url"], flush=True)
            elif not self.no_frontend:
                port_free(5173)
                node = self.directory / "runtimes/node-v24.21.0-win-x64/node.exe"
                if not node.is_file():
                    raise RuntimeError("Node24 fehlt; setup.bat erneut ausführen.")
                vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
                if not vite.is_file():
                    raise RuntimeError("Frontend-Abhängigkeiten fehlen; setup.bat ausführen.")
                env.update(VITE_API_BASE_URL=f"http://127.0.0.1:{self.api_port}")
                self.frontend = self.job.spawn([str(node), str(vite), "--host", "127.0.0.1", "--port", "5173", "--strictPort"], ROOT / "frontend", env, self.directory / "logs/frontend.log")
                print("LOKAL: http://127.0.0.1:5173/", flush=True)
            print("Ctrl+C oder offline.bat beendet alle eigenen Dienste.", flush=True)
            last_status = ""
            last_display = 0.0
            while not self.stop_event.wait(2):
                for child in (self.api, self.funnel, self.frontend):
                    if child and child.poll() is not None:
                        raise RuntimeError(f"Dienst {child.pid} ist unerwartet beendet.")
                try:
                    status = read_json(f"http://127.0.0.1:{self.admin_port}/internal/status", token=self.token)
                    compact = terminal_status(status, self.mode == "online")
                    if compact != last_status and time.monotonic() - last_display >= 5:
                        print(compact, flush=True)
                        last_status = compact
                        last_display = time.monotonic()
                except (OSError, ValueError):
                    pass
            return 0
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"\nStart-/Betriebsfehler: {exc}", file=sys.stderr, flush=True)
            return 1
        finally:
            self.shutdown()

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        self.stop_event.set()
        print("\nChatabae wird beendet...", flush=True)
        try:
            if self.api and self.api.poll() is None:
                try:
                    read_json(f"http://127.0.0.1:{self.admin_port}/internal/drain", timeout=1, token=self.token, method="POST")
                except Exception:
                    pass
            if self.funnel:
                self.funnel.terminate()
                try:
                    self.funnel.wait(2)
                except TimeoutError:
                    pass
            # Job close covers API, every model descendant, Funnel and Vite.
            self.job.close()
        finally:
            if self.control_server:
                self.control_server.shutdown()
                self.control_server.server_close()
            control = self.directory / "control.json"
            if control.exists():
                try:
                    if json.loads(control.read_text()).get("instance_id") == self.instance_id:
                        control.unlink()
                except (OSError, ValueError):
                    pass
            if self.lock:
                self.lock.close()
            print("OFFLINE. Öffentliche KI-Verbindung und eigene Prozesse beendet.", flush=True)


def stop_existing() -> int:
    control = data_directory() / "control.json"
    if not control.is_file():
        print("Chatabae läuft nicht.")
        return 0
    payload = json.loads(control.read_text(encoding="utf-8"))
    try:
        read_json(f"http://127.0.0.1:{int(payload['port'])}/stop", token=payload["token"], method="POST")
        deadline = time.monotonic() + 12
        while control.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if control.exists():
            raise RuntimeError("Supervisor hat Stop noch nicht bestätigt.")
        print("Chatabae ist offline.")
        return 0
    except (OSError, RuntimeError) as exc:
        print("Stop fehlgeschlagen:", exc, file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("local", "online", "stop"))
    parser.add_argument("--no-frontend", action="store_true")
    args = parser.parse_args()
    if args.mode == "stop":
        return stop_existing()
    try:
        return Supervisor(args.mode, args.no_frontend).run()
    except (RuntimeError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
