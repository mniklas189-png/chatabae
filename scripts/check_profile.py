"""Explicit model-only structured-profile check, without registering an account."""
import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from chatabae.config import Settings
from chatabae.providers import ProviderManager
from scripts.models.benchmark import read_installed_config


async def check():
    settings = Settings.model_validate(read_installed_config(None))
    settings.runtime = {**settings.runtime, "chat_port": 8872, "image_port": 8873}
    manager = ProviderManager(settings)
    manager.runtime_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = await manager.create_profile("Requested profile language: Deutsch (de). Ein fiktiver freundlicher erwachsener Reisebegleiter namens Ben, der gerne wandert.", "assisted")
        assert isinstance(result["interests"], str)
        print({"real_profile_passed": True, "interests_type": type(result["interests"]).__name__, "field_count": len(result)})
    finally:
        await manager.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    if parser.parse_args().execute:
        asyncio.run(check())
    else:
        print("Requires --execute and an exclusively available GPU; stop Chatabae first.")
