"""Use the same private data directory as the Windows launchers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from launcher.supervisor import data_directory


def main():
    directory = data_directory()
    config = directory / "config.json"
    if not config.is_file():
        raise SystemExit("Private configuration is missing; run setup.bat first.")
    os.environ["CHATABAE_CONFIG"] = str(config)
    os.environ["CHATABAE_DATA_DIR"] = str(directory)
    from chatabae.backup import main as backup_main
    backup_main()


if __name__ == "__main__":
    main()
