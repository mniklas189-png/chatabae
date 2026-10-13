from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from chatabae.providers import GPUResourceError, ProviderError, ProviderManager, ProviderUnavailable, _inside


@pytest.fixture
def manager(tmp_path):
    missing = tmp_path / "missing"
    settings = SimpleNamespace(data_dir=tmp_path, mode="local", public_image_allowed=False, xtts_enabled=False, model_paths={key: str(missing) for key in ("llama_cpp_executable", "chat_model", "mmproj", "kokoro_model", "piper_executable", "piper_model")}, runtime={"tts_python": str(missing), "xtts_python": str(missing)}, image={"enabled": False})
    return ProviderManager(settings)


async def ready():
    pass


@pytest.mark.asyncio
async def test_missing_chat_assets_never_fabricate_response(manager):
    with pytest.raises(ProviderUnavailable, match="executable is missing"):
        await anext(manager.stream_chat([{"role": "user", "content": "Hello"}]))
    assert manager.status()["chat"]["available"] is False
    await manager.stop()


@pytest.mark.asyncio
async def test_chat_stream_only_emits_model_content_and_filters_request_parameters(manager, monkeypatch):
    monkeypatch.setattr(manager, "ensure_chat_ready", ready)
    def handler(request):
        payload = json.loads(request.content)
        assert "tools" not in payload and "url" not in payload
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2]})
        assert payload["chat_template_kwargs"]["enable_thinking"] is False
        assert request.url.host == "127.0.0.1"
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": "Hi"})
        return httpx.Response(200, text='data: {"choices":[{"delta":{"reasoning_content":"hidden"}}]}\n\ndata: {"choices":[{"delta":{"content":"Hello "}}]}\n\ndata: {"choices":[{"delta":{"content":"friend"}}]}\n\ndata: [DONE]\n\n')
    manager._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    chunks = [text async for text in manager.stream_chat([{"role": "user", "content": "Hi"}], {"tools": [{}], "url": "https://example.com"})]
    assert chunks == ["Hello ", "friend"]
    await manager.stop()


@pytest.mark.asyncio
async def test_cancel_interrupts_a_stalled_chat_read(manager, monkeypatch):
    monkeypatch.setattr(manager, "ensure_chat_ready", ready)
    class Stalled(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            await asyncio.Event().wait()
            yield b""
        async def aclose(self):
            self.closed = True
    stream = Stalled()
    def handler(request):
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": "Hi"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2]})
        return httpx.Response(200, stream=stream)
    manager._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cancel = asyncio.Event()
    task = asyncio.create_task(anext(manager.stream_chat([], {}, cancel)))
    await asyncio.sleep(0.02)
    cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert stream.closed
    await manager.stop()


@pytest.mark.asyncio
async def test_cancel_during_model_warmup_cleans_up_before_request(manager, monkeypatch):
    cleaned = asyncio.Event()
    async def loading():
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
    monkeypatch.setattr(manager, "ensure_chat_ready", loading)
    cancel = asyncio.Event()
    task = asyncio.create_task(anext(manager.stream_chat([], {}, cancel)))
    await asyncio.sleep(0.01)
    cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_public_image_gate_precedes_process_start(manager, monkeypatch):
    manager.settings.mode = "online"
    async def forbidden():
        pytest.fail("Image process must not start before the license gate")
    monkeypatch.setattr(manager, "_ensure_image_ready", forbidden)
    with pytest.raises(ProviderUnavailable, match="private evaluation"):
        await manager.generate_image({"age": 30}, "A portrait")


@pytest.mark.asyncio
async def test_moderation_holds_missing_model_and_ambiguous_age(manager):
    assert (await manager.moderate_profile({"age": 30, "fictional": True}))["decision"] == "hold"
    assert (await manager.moderate_profile({"age": True, "fictional": True}))["decision"] == "hold"
    assert (await manager.moderate_profile({"age": 17, "fictional": True}))["decision"] == "hold"
    await manager.stop()


@pytest.mark.asyncio
async def test_image_history_fallback_and_owned_output_validation(manager, monkeypatch):
    monkeypatch.setattr(manager, "_ensure_image_ready", ready)
    monkeypatch.setattr(manager, "_running", lambda name: True)
    async def watcher(*args):
        await asyncio.Event().wait()
    monkeypatch.setattr(manager, "_watch_image", watcher)
    output = None
    prefix = None
    def handler(request):
        nonlocal output, prefix
        if request.url.path == "/prompt":
            graph = json.loads(request.content)["prompt"]
            save = next(node for node in graph.values() if node["class_type"] == "SaveImage")
            prefix = save["inputs"]["filename_prefix"]
            output = manager.output_dir / f"{prefix}_00001_.png"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"test-output")
            return httpx.Response(200, json={"prompt_id": "owned-job"})
        return httpx.Response(200, json={"owned-job": {"status": {"completed": True}, "outputs": {"9": {"images": [{"type": "output", "subfolder": "chatabae", "filename": output.name}]}}}})
    manager._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    events = []
    assert await manager.generate_image({"age": 30, "fictional": True}, "Portrait", progress_callback=events.append) == [output]
    assert events[-1]["stage"] == "done"
    await manager.stop()


def test_output_path_cannot_escape_owned_directory(manager):
    with pytest.raises(ProviderError, match="outside"):
        _inside(manager.output_dir / "../../outside.png", manager.output_dir)


@pytest.mark.asyncio
async def test_speech_cancellation_reaps_the_owned_process(manager):
    process = manager._spawn("piper", [sys.executable, "-c", "import time; time.sleep(60)"], input_pipe=True)
    cancel = asyncio.Event()
    task = asyncio.create_task(manager._wait_speech("piper", process, "test", cancel))
    await asyncio.sleep(0.02)
    cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    assert process.poll() is not None
    assert "piper" not in manager._children
    await manager.stop()


@pytest.mark.asyncio
async def test_persistent_cpu_worker_reuses_process_and_reaps_on_cancel(manager, monkeypatch):
    # An IPC test double verifies lifecycle independently of the real model smoke script.
    code = "import sys,json,time\nfor line in sys.stdin:\n r=json.loads(line)\n if r['text']=='stall': time.sleep(60)\n print(json.dumps({'id':r['id'],'ok':True,'output':r['output']}),flush=True)"
    original_spawn = manager._spawn
    def spawn(name, command, **options):
        return original_spawn(name, [sys.executable, "-u", "-c", code], **options)
    monkeypatch.setattr(manager, "_spawn", spawn)
    request = {"engine": "kokoro", "text": "hello", "output": str(manager.output_dir / "voice.wav")}
    await manager._synthesize_kokoro(request, None)
    process = manager._children["kokoro"]
    await manager._synthesize_kokoro({**request, "text": "another voice"}, None)
    assert manager._children["kokoro"] is process and process.poll() is None
    cancel = asyncio.Event()
    task = asyncio.create_task(manager._synthesize_kokoro({**request, "text": "stall"}, cancel))
    await asyncio.sleep(0.02)
    cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert process.poll() is not None and "kokoro" not in manager._children
    await manager._synthesize_kokoro(request, None)
    assert manager._children["kokoro"] is not process
    await manager.stop()


@pytest.mark.asyncio
async def test_cpu_speech_worker_rejects_unbounded_ipc_input(manager):
    with pytest.raises(ProviderError, match="worker limit"):
        await manager._synthesize_kokoro({"text": "x" * 12001, "output": "ignored"}, None)
    assert not manager._children


@pytest.mark.asyncio
async def test_gpu_release_does_not_interrupt_concurrent_cpu_speech(manager, monkeypatch):
    stopped = []
    async def stop_child(name):
        stopped.append(name)
    monkeypatch.setattr(manager, "_stop_child", stop_child)
    await manager.unload_gpu()
    assert stopped == ["chat", "image"]


def test_reference_graph_uses_qwen_matching_latent_and_single_batch(manager):
    graph = manager._image_graph("adult character", {}, ["owned-reference.png"], "chatabae/owned")
    encoder_id = next(key for key, node in graph.items() if node["class_type"] == "TextEncodeQwenImage21")
    sampler = next(node for node in graph.values() if node["class_type"] == "KSampler")
    assert sampler["inputs"]["latent_image"] == [encoder_id, 2]
    assert sampler["inputs"]["cfg"] == 1.0
    assert graph[encoder_id]["inputs"]["resolution"] == 0
    assert "images.image_1" in graph[encoder_id]["inputs"]


@pytest.mark.asyncio
async def test_nonsexual_minor_and_real_inspiration_are_reviewed_by_model(manager, monkeypatch):
    calls = []
    async def moderation_ready(**options):
        calls.append(options)
    async def review(messages, **options):
        assert "Nonsexual characters of any age" in messages[0]["content"]
        return {"decision": "allow", "reason": "Nonsexual fictional child character."}
    monkeypatch.setattr(manager, "ensure_chat_ready", moderation_ready)
    monkeypatch.setattr(manager, "_completion_json", review)
    decision = await manager.moderate_profile({"age": 12, "fictional": True, "description": "A friendly child explorer."})
    assert decision["decision"] == "allow" and calls == [{"cpu": True, "vision": False}]
    assert (await manager.moderate_profile({"age": 25, "fictional": False, "description": "Harmless inspiration."}))["decision"] == "allow"


def tokenizer_transport():
    def handler(request):
        payload = json.loads(request.content)
        if request.url.path == "/apply-template":
            assert payload["chat_template_kwargs"] == {"enable_thinking": False}
            assert all(isinstance(message["content"], str) for message in payload["messages"])
            return httpx.Response(200, json={"prompt": "\n".join(message["content"] for message in payload["messages"])})
        assert request.url.path == "/tokenize"
        assert payload["add_special"] is True and payload["parse_special"] is True
        # A character-per-token tokenizer deliberately models text denser than English.
        return httpx.Response(200, json={"tokens": list(range(len(payload["content"])))})
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_unicode_context_prunes_complete_old_turn_and_preserves_core(manager):
    manager._runtime["chat_context"] = 256
    manager._client = httpx.AsyncClient(transport=tokenizer_transport())
    messages = [{"role": "system", "content": "Keep server policies."}, {"role": "user", "content": "旧" * 80}, {"role": "assistant", "content": "答" * 80}, {"role": "user", "content": "最新の入力"}]
    fitted = await manager._fit_chat_context(manager._chat_payload(messages, {"max_tokens": 32}, stream=True))
    assert fitted["messages"] == [messages[0], messages[-1]]
    assert messages[1]["content"] == "旧" * 80
    await manager.stop()


@pytest.mark.asyncio
async def test_core_context_excess_never_truncates_profile_or_latest_input(manager):
    manager._runtime["chat_context"] = 256
    manager._client = httpx.AsyncClient(transport=tokenizer_transport())
    messages = [{"role": "system", "content": "Profile and policy " + "人" * 200}, {"role": "user", "content": "latest question"}]
    with pytest.raises(ProviderError, match="Shorten them"):
        await manager._fit_chat_context(manager._chat_payload(messages, {"max_tokens": 32}, stream=True))
    assert len(messages[0]["content"]) > 200
    await manager.stop()


@pytest.mark.asyncio
async def test_vision_moderation_reserves_image_tokens_without_tokenizing_base64(manager):
    manager._runtime["chat_context"] = 1536
    manager._client = httpx.AsyncClient(transport=tokenizer_transport())
    messages = [{"role": "system", "content": "review"}, {"role": "user", "content": [{"type": "text", "text": "x" * 200}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,not-text-tokens"}}]}]
    payload = manager._chat_payload(messages, {"max_tokens": 256}, stream=False)
    with pytest.raises(ProviderError, match="configured model context"):
        await manager._fit_chat_context(payload)
    messages[-1]["content"][0]["text"] = "safe profile"
    fitted = await manager._fit_chat_context(payload)
    assert fitted["messages"][-1]["content"][1] == messages[-1]["content"][1]
    await manager.stop()


def test_model_requests_cannot_fetch_remote_images_or_run_tools(manager):
    with pytest.raises(ProviderError, match="external URLs"):
        manager._chat_payload([{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}}]}], {}, stream=True)
    with pytest.raises(ProviderError, match="tool execution"):
        manager._chat_payload([{"role": "assistant", "content": "", "tool_calls": [{"name": "read_file"}]}], {}, stream=True)


def test_benchmark_config_uses_real_installed_paths_and_explicit_root_override(tmp_path, monkeypatch):
    from scripts.models import manage
    repository = tmp_path / "repository"
    installation = tmp_path / "installed"
    override = tmp_path / "override"
    (repository / "config").mkdir(parents=True)
    installation.mkdir()
    override.mkdir()
    (repository / "config/local.json").write_text(json.dumps({"data_dir": str(installation)}))
    (installation / "config.json").write_text(json.dumps({"model_paths": {"chat_model": "installed-custom.gguf"}, "image": {"models_dir": "shared-read-only-models"}, "runtime": {"chat_context": 4096}}))
    (override / "config.json").write_text(json.dumps({"model_paths": {"chat_model": "other-custom.gguf"}}))
    monkeypatch.setattr(manage, "ROOT", repository)
    loaded = manage.read_installed_config()
    assert loaded["model_paths"]["chat_model"] == "installed-custom.gguf"
    assert loaded["runtime"]["chat_context"] == 4096
    assert loaded["image"]["models_dir"] == "shared-read-only-models"
    explicit = manage.read_installed_config(override)
    assert explicit["model_paths"]["chat_model"] == "other-custom.gguf"
    assert Path(explicit["data_dir"]) == override.resolve()


@pytest.mark.asyncio
async def test_unsupported_speech_provider_is_descriptive(manager):
    with pytest.raises(ProviderUnavailable, match="Unsupported"):
        await manager.synthesize("Hello", "remote:voice", "en")


@pytest.mark.asyncio
async def test_gpu_guard_waits_for_release_and_reports_foreign_processes(manager, monkeypatch):
    snapshots = iter([{"available": True, "free_mib": 100, "foreign_gpu_processes": [{"pid": 42, "name": "foreign.exe"}]}, {"available": True, "free_mib": 10000, "used_mib": 1100, "foreign_gpu_processes": [{"pid": 42, "name": "foreign.exe"}]}])
    monkeypatch.setattr(manager, "_measure_gpu", lambda: next(snapshots))
    snapshot = await manager._require_gpu_room("image")
    assert snapshot["required_free_mib"] == 8192
    assert snapshot["foreign_gpu_processes"][0]["pid"] == 42
    assert not manager._children


@pytest.mark.asyncio
async def test_gpu_guard_holds_missing_telemetry_and_insufficient_memory(manager, monkeypatch):
    monkeypatch.setattr(manager, "_measure_gpu", lambda: {"available": False, "reason": "GPU memory telemetry is unavailable", "foreign_gpu_processes": []})
    with pytest.raises(GPUResourceError, match="telemetry is unavailable"):
        await manager._require_gpu_room("chat")
    manager._runtime["gpu_release_timeout"] = 0
    monkeypatch.setattr(manager, "_measure_gpu", lambda: {"available": True, "free_mib": 100, "foreign_gpu_processes": [{"pid": 42, "name": "foreign.exe"}]})
    with pytest.raises(GPUResourceError, match="never terminates them"):
        await manager._require_gpu_room("image")
    assert manager.status()["gpu"]["foreign_gpu_process_count"] == 1
    assert "foreign_gpu_processes" not in manager.status()["gpu"]


def test_gpu_oom_error_has_safe_actionable_text(manager):
    with pytest.raises(GPUResourceError, match="reduce image resolution") as failure:
        manager._raise_if_gpu_oom("image", "Private path and prompt: torch.OutOfMemoryError: CUDA out of memory")
    assert "Private path" not in str(failure.value)


@pytest.mark.asyncio
async def test_created_profile_fills_editor_fields_and_preserves_requested_minor_age(manager, monkeypatch):
    monkeypatch.setattr(manager, "ensure_chat_ready", ready)
    result = {"name": "Mila", "age": 12, "fictional": True, "description": "Forscherin", "personality": "Neugierig", "backstory": "Ein erfundenes Dorf", "appearance": "Roter Mantel", "greeting": "Hallo", "scenario": "Eine Entdeckung", "language": "de", "voice": "piper:de_DE-kerstin-low"}
    async def completion(messages, **options):
        assert "communication_style" in messages[0]["content"]
        assert options["json_schema"]["properties"]["interests"] == {"type": "string"}
        assert "instructions" in options["json_schema"]["required"]
        return dict(result)
    monkeypatch.setattr(manager, "_completion_json", completion)
    profile = await manager.create_profile("Eine zwölfjährige Forscherin", "assisted")
    assert profile["age"] == 12
    assert profile["gender"] == "Nicht angegeben"
    assert profile["communication_style"] == "Freundlich und natürlich"
    assert all(isinstance(profile[field], str) for field in ("interests", "relationship", "instructions"))
    result["interests"] = ["Sterne", "Wandern"]
    assert (await manager.create_profile("Eine Forscherin", "assisted"))["interests"] == "Sterne; Wandern"


def test_speech_cache_fingerprint_changes_for_voice_and_model_replacement_without_exposing_paths(manager, tmp_path):
    model = tmp_path / "kokoro"
    (model / "voices").mkdir(parents=True)
    for relative in ("config.json", "kokoro-v1_0.pth", "voices/af_heart.pt", "voices/am_michael.pt"):
        (model / relative).write_bytes(b"first")
    manager._models["kokoro_model"] = str(model)
    initial = manager.speech_fingerprint("kokoro:af_heart", "en")
    assert len(initial) == 64 and str(model) not in initial
    assert initial == manager.speech_fingerprint("kokoro:af_heart", "en")
    assert initial != manager.speech_fingerprint("kokoro:am_michael", "en")
    (model / "kokoro-v1_0.pth").write_bytes(b"different-model")
    assert initial != manager.speech_fingerprint("kokoro:af_heart", "en")


def test_image_graph_rejects_over_one_megapixel_without_reference(manager):
    with pytest.raises(ProviderError, match="pixel budget"):
        manager._image_graph("portrait", {"width": 1536, "height": 1024}, [], "owned")


@pytest.mark.asyncio
async def test_image_moderation_decides_from_fixed_categories(manager, monkeypatch):
    answers = {}
    async def ready(**options):
        pass
    async def review(messages, **options):
        assert "Gender, style or other differences" in messages[0]["content"] and options["json_schema"]["required"][-1] == "reason"
        return dict(answers)
    monkeypatch.setattr(manager, "ensure_chat_ready", ready)
    monkeypatch.setattr(manager, "_completion_json", review)
    clean = {"minor_sexualized": False, "named_real_person": False, "hate_or_extremism": False, "nudity_or_sexual": False, "graphic_violence": False, "reason": "A portrait"}
    answers.update(clean)
    assert (await manager.moderate_image({"age": 30}, "Portrait"))["decision"] == "allow"
    answers.update(nudity_or_sexual=True)
    assert (await manager.moderate_image({"age": 30}, "Portrait"))["decision"] == "hold"
    assert (await manager.moderate_image({"age": 30, "content_mode": "adult"}, "Portrait"))["decision"] == "allow"
    answers.update(minor_sexualized=True)
    held = await manager.moderate_image({"age": 30, "content_mode": "adult"}, "Portrait")
    assert held["decision"] == "hold" and held["reason"].startswith("minor_sexualized")
    answers.clear()
    answers.update(clean, named_real_person="maybe")
    assert (await manager.moderate_image({"age": 30, "content_mode": "adult"}, "Portrait"))["decision"] == "hold"
