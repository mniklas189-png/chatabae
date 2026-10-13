"""Export deterministic HTTP contracts without initializing a model provider."""
import argparse
import json
import tempfile
from pathlib import Path

from .app import create_app
from .config import Limits, Settings
from .jobs import UnavailableProviders


def export(destination: Path):
    with tempfile.TemporaryDirectory(prefix="chatabae-openapi-") as directory:
        data = Path(directory).resolve()
        if not data.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not data.name.startswith("chatabae-openapi-"):
            raise RuntimeError("Unexpected temporary schema location")
        app = create_app(Settings(data_dir=data, backups_enabled=False, metrics_enabled=False, limits=Limits(disk_reserve_bytes=0)), providers=UnavailableProviders())
        try:
            schema = app.openapi()
            schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            destination.write_text(json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        finally:
            app.state.runtime.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "openapi.json")
    export(parser.parse_args().output)
