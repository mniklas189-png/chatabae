"""Explicit real-inference smoke checks; generated files remain private runtime artifacts."""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from chatabae.config import Settings
from chatabae.providers import ProviderManager
from scripts.models.manage import read_installed_config


async def run(args) -> None:
    payload = read_installed_config(args.data_dir)
    payload["mode"] = "local"
    settings = Settings.model_validate(payload)
    # The explicit optional downloads use their own assets destination.
    for key, relative in (("piper_female_model", "assets/data/models/piper/de_DE-kerstin-low.onnx"), ("xtts_model_dir", "assets/data/models/xtts")):
        candidate = settings.data_dir / relative
        if candidate.exists() and key not in settings.model_paths:
            settings.model_paths[key] = str(candidate)
    if "xtts" in args.capabilities:
        settings.xtts_enabled = True
    manager = ProviderManager(settings)
    try:
        for name in args.capabilities:
            start = time.monotonic()
            if name == "chat":
                reply = "".join([chunk async for chunk in manager.stream_chat([{"role": "system", "content": "Answer briefly in English."}, {"role": "user", "content": "Say hello in one short sentence."}], {"max_tokens": 64, "temperature": 0})])
                if not reply.strip():
                    raise RuntimeError("Real model returned no content")
                print(json.dumps({"capability": name, "success": True, "reply": reply, "seconds": round(time.monotonic() - start, 2)}, ensure_ascii=False), flush=True)
                await manager.unload_gpu()
            elif name == "moderation":
                result = await manager.moderate_profile({"name": "Mira", "age": 30, "fictional": True, "description": "A friendly fictional gardener who talks about plants."})
                print(json.dumps({"capability": name, "result": result, "seconds": round(time.monotonic() - start, 2)}), flush=True)
                await manager.unload_gpu()
            elif name == "image":
                outputs = await manager.generate_image({"age": 30, "fictional": True, "appearance": "a fictional adult woman with auburn hair"}, "A fully clothed portrait in a garden", {"width": 512, "height": 512, "steps": 1})
                from PIL import Image
                with Image.open(outputs[0]) as image:
                    print(json.dumps({"capability": name, "success": True, "path": str(outputs[0]), "size": image.size, "seconds": round(time.monotonic() - start, 2)}), flush=True)
                await manager.unload_gpu()
            else:
                voices = {"kokoro": [("kokoro:af_heart", "en"), ("kokoro:am_michael", "en")], "piper": [("piper:de_DE-thorsten-medium", "de"), ("piper:de_DE-kerstin-low", "de")], "xtts": [("xtts:Ana Florence", "de")]}
                for voice, language in voices[name]:
                    voice_start = time.monotonic()
                    text = "Hello. This is a local speech test." if language == "en" else "Hallo. Dies ist ein lokaler Sprachtest."
                    output = await manager.synthesize(text, voice, language)
                    with wave.open(str(output)) as audio:
                        if audio.getnframes() <= 0:
                            raise RuntimeError("Real speech worker returned no audio")
                        print(json.dumps({"capability": name, "success": True, "voice": voice, "path": str(output), "rate": audio.getframerate(), "audio_seconds": round(audio.getnframes() / audio.getframerate(), 3), "seconds": round(time.monotonic() - voice_start, 2)}, ensure_ascii=False), flush=True)
    finally:
        await manager.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capabilities", nargs="+", choices=("chat", "kokoro", "piper", "xtts", "image", "moderation"))
    parser.add_argument("--data-dir", type=Path)
    asyncio.run(run(parser.parse_args()))
