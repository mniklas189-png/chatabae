import asyncio
import re
import time

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from chatabae.config import Limits, Settings
from chatabae.db import Character, Conversation, Job, Message, User
from chatabae.jobs import Runtime
from conftest import FakeProviders


@pytest.mark.parametrize("accounts", [2, 5, 10, 20])
@pytest.mark.asyncio
async def test_simulated_accounts_fairness_gpu_exclusion_and_persistent_quotas(tmp_path, accounts):
    settings = Settings(data_dir=tmp_path, backups_enabled=False, metrics_enabled=False, limits=Limits(disk_reserve_bytes=0, chat_per_minute=100, chat_per_day=2, queue_size=32))
    provider = FakeProviders(tmp_path)
    original = provider.stream_chat
    started, active, peak = [], 0, 0
    async def observed(messages, generation, cancel_event):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        match = re.search(r'"name": "Visitor_(\d+)"', messages[0]["content"])
        started.append(int(match.group(1)))
        try:
            async for token in original(messages, generation, cancel_event):
                yield token
        finally:
            active -= 1
    provider.stream_chat = observed
    rt = Runtime(settings, provider)
    visitors = []
    with rt.db.sessions() as db:
        for i in range(accounts):
            user = User(username=f"simulated_{i}", password_hash="not-a-login-fixture")
            db.add(user)
            db.flush()
            char = Character(user_id=user.id, name=f"Visitor_{i}", profile={"age": 25, "fictional": True})
            db.add(char)
            db.flush()
            convo = Conversation(user_id=user.id, character_id=char.id)
            db.add(convo)
            db.flush()
            db.add(Message(user_id=user.id, conversation_id=convo.id, role="user", content=f"Hello from visitor {i}"))
            visitors.append((user.id, convo.id))
        db.commit()
    await rt.start()
    try:
        # These are mocked functional load tests, not a hardware capacity benchmark.
        payloads = [(u, {"conversation_id": c, "generation": {"max_tokens": 64}}) for u, c in visitors]
        first = await asyncio.gather(*(rt.enqueue(u, "chat", p) for u, p in payloads))
        second = await asyncio.gather(*(rt.enqueue(u, "chat", p) for u, p in payloads), return_exceptions=True)
        accepted = first + [j for j in second if not isinstance(j, Exception)]
        rejected = [j for j in second if isinstance(j, Exception)]
        assert all(isinstance(error, HTTPException) and error.status_code == 429 for error in rejected)
        assert len(accepted) <= 32
        with rt.db.sessions() as db:
            assert db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running"]))) <= 32
            for user_id, _ in visitors:
                assert db.scalar(select(func.count()).select_from(Job).where(Job.user_id == user_id, Job.status.in_(["queued", "running"]))) <= 2
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with rt.db.sessions() as db:
                pending = db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running"])))
            if not pending:
                break
            await asyncio.sleep(0.025)
        assert pending == 0 and peak == 1
        assert len(set(started[:accounts])) == accounts
        with pytest.raises(HTTPException) as limited:
            await rt.enqueue(visitors[0][0], "chat", payloads[0][1])
        assert limited.value.status_code == 429
        with rt.db.sessions() as db:
            assert all(j.status == "completed" for j in db.scalars(select(Job)).all())
    finally:
        await rt.stop()
