"""One owned, offline speech inference request per process; no API or downloads."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import contextlib

_KOKORO_MODELS: dict = {}
_KOKORO_PIPELINES: dict = {}


def kokoro(request: dict) -> None:
    import importlib.util
    if importlib.util.find_spec("en_core_web_sm") is None:
        raise RuntimeError("Install the pinned en_core_web_sm package explicitly before offline Kokoro inference")
    import numpy as np
    import soundfile as sf
    import torch
    torch.set_num_threads(max(1, min(4, int(request.get("threads", 2)))))
    from kokoro import KModel, KPipeline
    model_dir = Path(request["model_dir"])
    voice = str(request["voice"])
    if not voice.replace("_", "").isalnum() or voice[:1] not in ("a", "b"):
        raise ValueError("Choose an installed English Kokoro voice")
    voice_path = Path(request["voices_dir"]) / f"{voice}.pt"
    if not voice_path.is_file():
        raise RuntimeError("Selected Kokoro voice weights are missing")
    key = str(model_dir.resolve())
    if key not in _KOKORO_MODELS:
        # A single configured model lives in this owned CPU service.
        _KOKORO_MODELS.clear()
        _KOKORO_PIPELINES.clear()
        _KOKORO_MODELS[key] = KModel(repo_id="hexgrad/Kokoro-82M", config=str(model_dir / "config.json"), model=str(model_dir / "kokoro-v1_0.pth")).to("cpu").eval()
    pipeline_key = (key, voice[0])
    if pipeline_key not in _KOKORO_PIPELINES:
        _KOKORO_PIPELINES[pipeline_key] = KPipeline(lang_code=voice[0], repo_id="hexgrad/Kokoro-82M", model=_KOKORO_MODELS[key], device="cpu")
    pipeline = _KOKORO_PIPELINES[pipeline_key]
    if request.get("operation") == "warmup":
        pipeline.load_voice(str(voice_path))
        return
    chunks = [result.audio.numpy() for result in pipeline(request["text"], voice=str(voice_path), speed=request["speed"]) if result.audio is not None]
    if not chunks:
        raise RuntimeError("Kokoro did not produce audio")
    sf.write(request["output"], np.concatenate(chunks), 24000, subtype="PCM_16")


def xtts(request: dict) -> None:
    import torch
    torch.set_num_threads(max(1, min(8, int(request.get("threads", 4)))))
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    import soundfile as sf
    model_dir = Path(request["model_dir"])
    config = XttsConfig()
    config.load_json(str(model_dir / "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=str(model_dir), eval=True, use_deepspeed=False)
    # CPU HQ is slower, but it cannot overlap the scheduled GPU model's allocations.
    model.cpu()
    speaker_wav = request.get("speaker_wav")
    if speaker_wav:
        if not Path(speaker_wav).is_file():
            raise ValueError("The verified speaker reference is missing")
        result = model.synthesize(request["text"], config, speaker_wav=speaker_wav, language=request["language"].split("-")[0], speed=request["speed"])
    else:
        voice = request.get("voice", "")
        if voice not in model.speaker_manager.speakers:
            raise ValueError("Choose a built-in XTTS speaker or a verified speaker reference")
        result = model.synthesize(request["text"], config, speaker_id=voice, language=request["language"].split("-")[0], speed=request["speed"])
    sf.write(request["output"], result["wav"], 24000, subtype="PCM_16")


def main() -> None:
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1", "CUDA_VISIBLE_DEVICES": ""})
    if sys.argv[1] == "--serve-kokoro":
        while True:
            line = sys.stdin.buffer.readline(65537)
            if not line:
                return
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise ValueError("Speech service input exceeds its request limit")
            request = json.loads(line)
            try:
                if request.get("engine") != "kokoro" or len(request.get("text", "")) > 12000:
                    raise ValueError("Invalid bounded Kokoro request")
                with contextlib.redirect_stdout(sys.stderr):
                    kokoro(request)
                response = {"id": request["id"], "ok": True, "output": request["output"]}
            except Exception as exc:
                print(f"Speech inference failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                response = {"id": request.get("id"), "ok": False, "error": type(exc).__name__}
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if request["engine"] == "kokoro":
        kokoro(request)
    elif request["engine"] == "xtts":
        xtts(request)
    else:
        raise ValueError("Unsupported speech worker")


if __name__ == "__main__":
    main()
