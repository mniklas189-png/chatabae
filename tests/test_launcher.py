from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from launcher.supervisor import port_free, tailscale_preflight
from launcher.windows import InstanceLock, ProcessJob


def test_instance_mutex_prevents_double_start(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    first = InstanceLock(tmp_path)
    try:
        # Windows mutexes are reentrant on the owning thread. A second launcher
        # has a different thread/process, which is the behavior under test.
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(RuntimeError, match="bereits|already"):
                pool.submit(InstanceLock, tmp_path).result()
    finally:
        first.close()
    again = InstanceLock(tmp_path)
    again.close()


def test_port_conflict_fails_instead_of_selecting_another_port():
    import socket
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        with pytest.raises(RuntimeError, match="belegt"):
            port_free(occupied.getsockname()[1])


def test_existing_funnel_configuration_is_not_overwritten(monkeypatch):
    results = iter([
        {"BackendState": "Running", "Self": {"DNSName": "chatabae.example.ts.net."}},
        {"TCP": {"443": {"HTTPS": True}}},
    ])
    def execute(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, json.dumps(next(results)), "")
    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises(RuntimeError, match="bereits konfiguriert"):
        tailscale_preflight("tailscale.exe", "https://chatabae.example.ts.net")


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object native lifecycle")
def test_job_close_kills_children_and_grandchildren(tmp_path):
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    def alive(pid):
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    marker = tmp_path / "grandchild.pid"
    code = "import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(60)"
    job = ProcessJob()
    process = job.spawn([sys.executable, "-c", code, str(marker)], tmp_path, dict(os.environ), tmp_path / "child.log")
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), (tmp_path / "child.log").read_text()
        grandchild = int(marker.read_text())
        assert alive(process.pid)
        assert alive(grandchild)
        job.close()
        deadline = time.monotonic() + 3
        while (alive(process.pid) or alive(grandchild)) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not alive(process.pid)
        assert not alive(grandchild)
    finally:
        job.close()
