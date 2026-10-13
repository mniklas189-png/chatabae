"""Explicit one-time installation; normal launchers never install or update dependencies."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def run(arguments: list[str], cwd: Path = ROOT, env=None):
    print("Ausführen:", " ".join(arguments), flush=True)
    subprocess.run(arguments, cwd=cwd, env=env, check=True)


def default_data() -> Path:
    marker = ROOT / "config/local.json"
    if marker.is_file() and not os.environ.get("CHATABAE_DATA_DIR"):
        return Path(json.loads(marker.read_text(encoding="utf-8"))["data_dir"])
    base = Path.home() / "AppData/Local" if os.name == "nt" else Path.home() / ".local/share"
    return Path(os.environ.get("CHATABAE_DATA_DIR") or (base / "Chatabae")).resolve()


def detect_paths(directory: Path) -> dict:
    image_root = ROOT.parent / "LocalImageAI"
    ally = ROOT.parent / "!local-ally-code"
    kokoro_cache = Path.home() / ".cache/huggingface/hub/models--hexgrad--Kokoro-82M/snapshots"
    kokoro = next((path for path in kokoro_cache.glob("*") if (path / "kokoro-v1_0.pth").exists()), None)
    return {
        "model_paths": {
            "llama_cpp_executable": str(directory / "tools/llama/llama-server.exe"),
            "chat_model": str(directory / "models/Qwen3.5-9B-Q4_K_M.gguf"),
            "mmproj": str(directory / "models/mmproj-F16.gguf"),
            "kokoro_model": str(kokoro / "kokoro-v1_0.pth") if kokoro else "",
            "kokoro_voices": str(kokoro / "voices") if kokoro else "",
            "piper_executable": str(ally / "piper/piper.exe"),
            "piper_model": str(ally / "piper/de_DE-thorsten-medium.onnx"),
            "piper_female_model": str(directory / "assets/data/models/piper/de_DE-kerstin-low.onnx"),
            "xtts_model_dir": str(directory / "assets/data/models/xtts"),
        },
        "image": {
            "enabled": True,
            "python_executable": str(image_root / "backend/venv/Scripts/python.exe"),
            "comfy_root": str(image_root / "backend/ComfyUI"),
            "models_dir": str(image_root / "models"),
        },
    }


def configure(directory: Path, api_url: str | None = None, frontend_url: str | None = None):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.json"
    value = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else json.loads((ROOT / "config/config.example.json").read_text())
    detected = detect_paths(directory)
    for section, fields in detected.items():
        section_value = value.setdefault(section, {})
        for key, setting in fields.items():
            if not section_value.get(key):
                section_value[key] = setting
    value["data_dir"] = str(directory)
    value.setdefault("control_port", 7813)
    value.setdefault("runtime", {}).update(tts_python=str(ROOT / ".venv-tts/Scripts/python.exe"), xtts_python=str(ROOT / ".venv-xtts/Scripts/python.exe"))
    if api_url is not None:
        if not api_url.startswith("https://") or not api_url.rstrip("/").endswith(".ts.net"):
            raise ValueError("Public API must be the HTTPS .ts.net URL of this device")
        value["public_api_url"] = api_url.rstrip("/")
    if frontend_url:
        from urllib.parse import urlsplit
        parts = urlsplit(frontend_url)
        if parts.scheme != "https" or not parts.netloc.endswith(".github.io"):
            raise ValueError("Frontend must be the intended GitHub Pages HTTPS URL")
        value["frontend_url"] = frontend_url.rstrip("/") + "/"
        value["allowed_origins"] = [f"{parts.scheme}://{parts.netloc}"]
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    # Packaged desktop applications may redirect AppData. Retain the resolved
    # location so double-click launchers outside that package use the same data.
    (ROOT / "config/local.json").write_text(json.dumps({"data_dir": str(directory.resolve())}, indent=2), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    print("Lokale Konfiguration:", path, flush=True)
    return value


def tailscale_setup(directory: Path):
    executable = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tailscale/tailscale.exe"
    if not executable.exists():
        run(["winget", "install", "--id", "Tailscale.Tailscale", "--exact", "--silent", "--accept-package-agreements", "--accept-source-agreements"])
    # Browser sign-in belongs to the operator; no password/token is stored by this script.
    result = subprocess.run([str(executable), "status", "--json"], capture_output=True, text=True)
    status = json.loads(result.stdout) if result.returncode == 0 else {}
    if status.get("BackendState") != "Running":
        run([str(executable), "up"])
        status = json.loads(subprocess.check_output([str(executable), "status", "--json"], text=True))
    hostname = status.get("Self", {}).get("DNSName", "").rstrip(".")
    if not hostname:
        raise RuntimeError("MagicDNS/Anmeldung nicht vollständig; in Tailscale fertigstellen.")
    configure(directory, api_url="https://" + hostname)
    print("Feste Backend-Adresse:", "https://" + hostname)
    print("Einmalig MagicDNS, HTTPS, Funnel-Berechtigung und Geräteschlüsselablauf in Tailscale prüfen.")
    print("online.bat führt danach den Foreground-Funnel aus. Keine dauerhafte --bg-Freigabe anlegen.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=default_data())
    parser.add_argument("--configure-only", action="store_true")
    parser.add_argument("--api-url")
    parser.add_argument("--frontend-url")
    parser.add_argument("--models", action="store_true")
    parser.add_argument("--voices", action="store_true")
    parser.add_argument("--tailscale", action="store_true")
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()
    config = configure(args.data_dir, args.api_url, args.frontend_url)
    if args.tailscale:
        tailscale_setup(args.data_dir)
    if args.configure_only:
        return
    if not args.skip_install:
        app_python = ROOT / ".venv/Scripts/python.exe"
        if not app_python.exists():
            run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
        run([str(app_python), "-m", "pip", "install", "-r", str(ROOT / "backend/requirements.txt")])
        node = args.data_dir / "runtimes/node-v24.21.0-win-x64/node.exe"
        if not node.exists():
            run([sys.executable, str(ROOT / "scripts/bootstrap_runtime.py"), "--only", "node", "--data-dir", str(args.data_dir)])
        npm_cli = node.parent / "node_modules/npm/bin/npm-cli.js"
        node_env = dict(os.environ, PATH=str(node.parent) + os.pathsep + os.environ["PATH"])
        run([str(node), str(npm_cli), "ci"], cwd=ROOT / "frontend", env=node_env)
    if args.models:
        run([sys.executable, str(ROOT / "scripts/bootstrap_runtime.py"), "--only", "runtime", "--data-dir", str(args.data_dir)])
        run([sys.executable, str(ROOT / "scripts/bootstrap_runtime.py"), "--only", "models", "--data-dir", str(args.data_dir)])
    if args.voices:
        run([sys.executable, str(ROOT / "scripts/models/manage.py"), "prepare-kokoro", "--root", str(args.data_dir / "assets")])
        # Resolve the verified existing snapshot or the explicitly fetched local
        # assets; saving these paths makes a fresh install ready for inference.
        from models.manage import ensure_kokoro
        kokoro = ensure_kokoro(args.data_dir / "assets")
        config["model_paths"].update({key: kokoro[key] for key in ("kokoro_model", "kokoro_voices")})
        (args.data_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        run([sys.executable, str(ROOT / "scripts/models/manage.py"), "download", "piper_kerstin", "piper_kerstin_config", "piper_kerstin_card", "xtts", "xtts_speakers", "xtts_config", "xtts_vocab", "xtts_license", "--root", str(args.data_dir / "assets")])
        requirements = ROOT / "scripts/models/requirements-tts.txt"
        if not requirements.exists():
            raise RuntimeError("TTS requirements are missing")
        for name in ("tts", "xtts"):
            voice_env = ROOT / f".venv-{name}"
            if not (voice_env / "Scripts/python.exe").exists():
                run([sys.executable, "-m", "venv", str(voice_env)])
            voice_python = voice_env / "Scripts/python.exe"
            requirement = ROOT / f"scripts/models/requirements-{name}.txt"
            run([str(voice_python), "-m", "pip", "install", "-r", str(requirement)])
    print("Einrichtung abgeschlossen. Lokal: start.bat. Öffentlich nach Tailscale-Einrichtung: online.bat.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print("Einrichtung fehlgeschlagen:", error, file=sys.stderr)
        raise SystemExit(1)
