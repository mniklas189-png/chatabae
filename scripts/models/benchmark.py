"""Explicit private GPU switching test. This measures lifecycle, not image quality."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from chatabae.config import Settings
from chatabae.providers import ProviderManager
from scripts.models.manage import read_installed_config


def snapshot() -> dict:
    sample = {"at": time.monotonic()}
    result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("NVIDIA memory measurements are unavailable")
    name, total, used, free, utilization = [item.strip() for item in result.stdout.splitlines()[0].split(",")]
    sample.update({"gpu": name, "vram_total_mib": float(total), "vram_used_mib": float(used), "vram_free_mib": float(free), "gpu_utilization_percent": float(utilization)})
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ("total_physical", "available_physical", "total_pagefile", "available_pagefile", "total_virtual", "available_virtual", "available_extended")]
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise ctypes.WinError()
        sample.update({"ram_total_mib": memory.total_physical / 2**20, "ram_available_mib": memory.available_physical / 2**20, "ram_used_mib": (memory.total_physical - memory.available_physical) / 2**20})
    return sample


def monotonic_growth(samples: list[dict], key: str, threshold: float) -> bool:
    # Five post-exit snapshots and a material rise avoid treating allocator/desktop jitter as a leak.
    if len(samples) < 5:
        return False
    values = [sample[key] for sample in samples[-5:] if key in sample]
    return len(values) == 5 and values[-1] - values[0] > threshold and all(later > earlier + 8 for earlier, later in zip(values, values[1:]))


async def measured(operation) -> tuple[object, list[dict], float]:
    samples = []
    start = time.monotonic()
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            samples.append(await asyncio.to_thread(snapshot))
            await asyncio.sleep(0.5)
        return await task, samples, time.monotonic() - start
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def exercise(manager: ProviderManager, model: str):
    if model == "chat":
        result = "".join([token async for token in manager.stream_chat([{"role": "system", "content": "Reply briefly in English."}, {"role": "user", "content": "Say hello in one short sentence."}], {"temperature": 0, "max_tokens": 32})])
        if not result.strip():
            raise RuntimeError("Chat inference returned no content")
        return {"characters": len(result)}
    images = await manager.generate_image({"age": 30, "fictional": True, "appearance": "a fictional adult gardener with auburn hair"}, "A fully clothed portrait in a quiet garden", {"width": 512, "height": 512, "steps": 1})
    from PIL import Image
    try:
        with Image.open(images[0]) as image:
            image.load()
            if image.size != (512, 512):
                raise RuntimeError("Unexpected image dimensions")
            return {"width": image.width, "height": image.height}
    finally:
        for path in images:
            if path.resolve().is_relative_to(manager.output_dir.resolve()):
                path.unlink(missing_ok=True)


async def run(args) -> None:
    config = read_installed_config(args.data_dir)
    source = Settings.model_validate(config)
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    benchmark_dir = source.data_dir / "benchmarks" / identifier
    models = {**source.model_paths}
    models.setdefault("llama_cpp_executable", str(source.data_dir / "tools/llama/llama-server.exe"))
    models.setdefault("chat_model", str(source.data_dir / "models/Qwen3.5-9B-Q4_K_M.gguf"))
    models.setdefault("mmproj", str(source.data_dir / "models/mmproj-F16.gguf"))
    settings = source.model_copy(update={"data_dir": benchmark_dir / "private-runtime", "mode": "local", "model_paths": models, "runtime": {**source.runtime, "chat_port": args.chat_port, "image_port": args.image_port}})
    manager = ProviderManager(settings)
    if not args.execute:
        print(json.dumps({"will_execute": False, "transitions": args.transitions, "capabilities": manager.status(), "report_directory": str(benchmark_dir), "ports": [args.chat_port, args.image_port]}))
        return
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    report_path = benchmark_dir / "gpu-switches.json"
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "requested_model_switches": args.transitions, "completed_model_switches": 0, "loads": 0, "unloads": 0, "status": "running", "limitations": "One-step 512x512 private image and short chat inference exercise loading/unloading. This is not an image-quality or maximum-capacity benchmark. VRAM is global NVIDIA telemetry; RAM is system telemetry. Peaks are sampled.", "configuration": {"chat_context": int(settings.runtime.get("chat_context", 8192)), "chat_output_tokens": 32, "image_steps": 1, "image_size": [512, 512], "ports": [args.chat_port, args.image_port], "image_vram_reserve_gib": 0.8}, "measurements": []}
    baseline_samples = []
    def save():
        partial = report_path.with_suffix(".tmp")
        partial.write_text(json.dumps(report, indent=2), encoding="utf-8")
        os.replace(partial, report_path)
    start = time.monotonic()
    try:
        report["initial_baseline"] = await asyncio.to_thread(snapshot)
        # Establish chat first, so each of the following 20 iterations is an actual model-type switch.
        result, samples, seconds = await measured(exercise(manager, "chat"))
        report["initial_chat"] = {"seconds": seconds, "result": result, "samples": samples}
        report["loads"] += 1
        previous = "chat"
        for index in range(args.transitions):
            target = "image" if previous == "chat" else "chat"
            await manager.unload_gpu()
            report["unloads"] += 1
            await asyncio.sleep(2)
            before = await asyncio.to_thread(snapshot)
            baseline_samples.append(before)
            if monotonic_growth(baseline_samples, "vram_used_mib", args.gpu_growth_mib) or monotonic_growth(baseline_samples, "ram_used_mib", args.ram_growth_mib):
                raise RuntimeError("Material monotonic post-unload memory growth detected")
            if before.get("ram_available_mib", 8192) < 2048:
                raise RuntimeError("Insufficient available RAM for another model switch")
            result, samples, seconds = await measured(exercise(manager, target))
            report["loads"] += 1
            measurement = {"switch": index + 1, "from": previous, "to": target, "before_load": before, "loaded": await asyncio.to_thread(snapshot), "sampled_peak_vram_used_mib": max(sample["vram_used_mib"] for sample in samples), "sampled_peak_ram_used_mib": max(sample.get("ram_used_mib", 0) for sample in samples), "seconds": round(seconds, 3), "result": result, "samples": samples}
            report["measurements"].append(measurement)
            report["completed_model_switches"] = index + 1
            save()
            print(f"switch {index + 1}/{args.transitions}: {previous}->{target}, {seconds:.2f}s, sampled VRAM {measurement['sampled_peak_vram_used_mib']:.0f} MiB", flush=True)
            previous = target
        report["status"] = "passed"
    except BaseException as exc:
        report["status"] = "interrupted" if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)) else "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        await manager.stop()
        report["unloads"] += 1
        await asyncio.sleep(2)
        report["final_baseline"] = await asyncio.to_thread(snapshot)
        report["elapsed_seconds"] = round(time.monotonic() - start, 3)
        report["ended_utc"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps({"status": report["status"], "completed_model_switches": report["completed_model_switches"], "loads": report["loads"], "unloads": report["unloads"], "elapsed_seconds": report["elapsed_seconds"], "report": str(report_path)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Explicitly run only after coordinating exclusive GPU use")
    parser.add_argument("--transitions", type=int, default=20)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--chat-port", type=int, default=8842)
    parser.add_argument("--image-port", type=int, default=8843)
    parser.add_argument("--gpu-growth-mib", type=float, default=1024)
    parser.add_argument("--ram-growth-mib", type=float, default=2048)
    arguments = parser.parse_args()
    if arguments.transitions < 20:
        parser.error("Acceptance requires at least 20 actual model-type switches")
    asyncio.run(run(arguments))
