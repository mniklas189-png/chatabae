"""Explicit local text/vision moderation smoke check; never publishes a profile."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from PIL import Image, ImageDraw
from chatabae.config import Settings
from chatabae.providers import ProviderManager
from scripts.models.benchmark import read_installed_config


async def run(execute: bool):
    source = Settings.model_validate(read_installed_config(None))
    directory = source.data_dir / "benchmarks" / ("moderation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    settings = source.model_copy(update={"data_dir": directory / "private-runtime", "mode": "local", "runtime": {**source.runtime, "chat_port": 8862, "image_port": 8863}})
    if not execute:
        print(json.dumps({"execute": False, "requires_exclusive_gpu": True, "scope": "Two harmless fictional adult profiles, text then a generated abstract test avatar. No publication."}))
        return
    directory.mkdir(parents=True)
    settings.data_dir.mkdir()
    avatar = settings.data_dir / "abstract-test-avatar.png"
    canvas = Image.new("RGB", (256, 256), (33, 35, 42))
    ImageDraw.Draw(canvas).ellipse((48, 48, 208, 208), fill=(124, 147, 179))
    canvas.save(avatar, "PNG")
    manager = ProviderManager(settings)
    report = {"status": "running", "checks": [], "limitations": "Checks actual Qwen text and CPU vision-projector inference on harmless artificial fixtures. This is not a photo/anime content calibration or proof of moderation accuracy."}
    try:
        for language, path in (("de", None), ("en", str(avatar))):
            start = time.monotonic()
            result = await manager.moderate_profile({"name": "Lea", "age": 27, "fictional": True, "description": "A friendly fictional adult astronomer.", "appearance": "Fully clothed adult character", "personality": "Curious and kind", "instructions": "Talk about stars.", "language": language}, avatar_path=path)
            if result.get("decision") not in {"allow", "hold"}:
                raise RuntimeError("Moderation returned an invalid decision")
            if not manager.status()["chat"]["ready"]:
                raise RuntimeError("A real Qwen moderation worker was not ready")
            report["checks"].append({"language": language, "vision": bool(path), "seconds": round(time.monotonic() - start, 3), "decision": result["decision"], "reason": result.get("reason", "")})
            print(json.dumps(report["checks"][-1]), flush=True)
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        await manager.stop()
        (directory / "moderation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(directory / "moderation.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    asyncio.run(run(parser.parse_args().execute))
