"""Explicit real-inference scheduler measurements in an isolated private database."""
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
from sqlalchemy import select
from chatabae.config import Settings
from chatabae.db import Character, Conversation, Job, JobEvent, Message, User
from chatabae.jobs import Runtime, TERMINAL
from chatabae.providers import ProviderManager
from scripts.models.benchmark import read_installed_config, snapshot


async def run(execute: bool):
    source = Settings.model_validate(read_installed_config(None))
    directory = source.data_dir / "benchmarks" / ("load-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    settings = source.model_copy(update={"data_dir": directory / "private-runtime", "mode": "local", "instance_id": "isolated-load-test", "backups_enabled": False, "runtime": {**source.runtime, "chat_port": 8852, "image_port": 8853}})
    if not execute:
        print(json.dumps({"execute": False, "accounts_per_wave": [2, 5, 10, 20], "report_directory": str(directory), "requires_exclusive_gpu": True}))
        return
    manager = ProviderManager(settings)
    runtime = Runtime(settings, manager)
    report = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(), "limitations": "Real Qwen chat through the application scheduler with isolated test-account fixtures, distinct personas and 64 maximum output tokens. Measures queuing and model inference, not public HTTP concurrency, image quality or Funnel bandwidth. System RAM and GPU peaks are sampled.", "waves": []}
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "scheduler-load.json"
    def save():
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    try:
        await runtime.start()
        if runtime.state != "ready" or not manager.status()["chat"]["ready"]:
            raise RuntimeError("Real Qwen worker was not ready")
        for count in (2, 5, 10, 20):
            inputs = []
            with runtime.db.sessions() as db:
                for index in range(count):
                    user = User(username=f"qa_wave_{count}_{index}", password_hash="isolated-fixture-no-login")
                    db.add(user)
                    db.flush()
                    character = Character(user_id=user.id, name=f"Guide{count}-{index}", description="A fictional adult hiking companion.", profile={"age": 30, "fictional": True, "instructions": "Start your reply with your character name. Reply in three concise English sentences."}, language="en", visibility="private")
                    db.add(character)
                    db.flush()
                    conversation = Conversation(user_id=user.id, character_id=character.id, title="Isolated scheduler measurement")
                    db.add(conversation)
                    db.flush()
                    db.add(Message(user_id=user.id, conversation_id=conversation.id, role="user", content="Describe a peaceful forest trail in three short sentences."))
                    inputs.append((user.id, conversation.id))
                db.commit()
            started = time.monotonic()
            jobs = [await runtime.enqueue(user_id, "chat", {"conversation_id": conversation_id, "generation": {"max_tokens": 64, "temperature": 0, "top_p": 0.8}}) for user_id, conversation_id in inputs]
            identifiers = [job.id for job in jobs]
            samples = []
            while True:
                with runtime.db.sessions() as db:
                    live = db.scalars(select(Job).where(Job.id.in_(identifiers))).all()
                    active = sum(job.status == "running" for job in live)
                    if active > 1:
                        raise RuntimeError("Single GPU lease invariant failed")
                    if any(job.status in {"failed", "cancelled"} for job in live):
                        raise RuntimeError("Real generation failed during the load wave")
                    if len(live) == count and all(job.status in TERMINAL for job in live):
                        break
                if time.monotonic() - started > count * settings.limits.chat_timeout + 60:
                    raise RuntimeError("Load wave exceeded its bounded timeout")
                samples.append(await asyncio.to_thread(snapshot))
                await asyncio.sleep(0.25)
            results = []
            for identifier in identifiers:
                with runtime.db.sessions() as db:
                    job = db.get(Job, identifier)
                    token_events = db.scalars(select(JobEvent).where(JobEvent.job_id == identifier, JobEvent.kind == "token").order_by(JobEvent.id)).all()
                    if not token_events or not job.output.get("message", {}).get("content"):
                        raise RuntimeError("Job completed without a real streamed model answer")
                    text = job.output["message"]["content"]
                    stored = db.get(Message, job.output["message"]["id"])
                    if stored.user_id != job.user_id or stored.conversation_id != job.payload["conversation_id"]:
                        raise RuntimeError("Private result ownership invariant failed")
                    first_at = token_events[0].created_at
                    last_at = token_events[-1].created_at
                    response = await manager._client_instance().post(manager._chat_url + "/tokenize", headers={"Authorization": "Bearer " + manager._chat_key}, json={"content": text, "add_special": False})
                    response.raise_for_status()
                    tokens = len(response.json()["tokens"])
                    seconds = max(0.001, last_at - first_at)
                    results.append({"queue_seconds": round(job.started_at - job.created_at, 3), "first_token_seconds": round(first_at - job.created_at, 3), "generation_seconds": round(job.finished_at - job.started_at, 3), "output_tokens": tokens, "streaming_tokens_per_second": round(tokens / seconds, 2) if len(token_events) > 1 else None})
            wave = {"accounts": count, "jobs_completed": count, "seconds": round(time.monotonic() - started, 3), "results": results, "peak_vram_mib": max((sample["vram_used_mib"] for sample in samples), default=None), "peak_system_ram_mib": max((sample.get("ram_used_mib", 0) for sample in samples), default=None), "single_gpu_lease": True}
            report["waves"].append(wave)
            save()
            print(json.dumps({key: value for key, value in wave.items() if key != "results"}), flush=True)
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        await runtime.stop()
        report["ended_utc"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps({"status": report["status"], "report": str(report_path)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    asyncio.run(run(parser.parse_args().execute))
