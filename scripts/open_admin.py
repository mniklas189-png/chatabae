"""Open local administration; the ephemeral credential stays in a URL fragment."""
import json
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launcher.supervisor import data_directory

directory = data_directory()
control_file = directory / "control.json"
if not control_file.is_file():
    raise SystemExit("Chatabae läuft nicht. Zuerst start.bat oder online.bat starten.")
control = json.loads(control_file.read_text(encoding="utf-8"))
config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
webbrowser.open(f"http://127.0.0.1:{config.get('admin_port', 7811)}/#{control['token']}")
print("Lokale Verwaltung geöffnet. Zugang ist nur für diese laufende Instanz gültig.")
