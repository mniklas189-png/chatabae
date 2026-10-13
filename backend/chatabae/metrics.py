"""Read-only hardware sampling, never on the request/event-loop path."""
import asyncio
import ctypes
import os
import shutil
import subprocess


def ram_metrics():
    if os.name != "nt":
        return {"available": False}
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong), ("total_page", ctypes.c_ulonglong), ("available_page", ctypes.c_ulonglong), ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong), ("extended_virtual", ctypes.c_ulonglong)]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return {"available": False}
    return {"available": True, "total_bytes": status.total_physical, "available_bytes": status.available_physical, "used_bytes": status.total_physical - status.available_physical, "used_percent": status.load}


def sample():
    result = {"ram": ram_metrics(), "gpu": {"available": False}}
    executable = shutil.which("nvidia-smi")
    if not executable:
        return result
    try:
        completed = subprocess.run([executable, "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=2, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if completed.returncode == 0:
            values = [part.strip() for part in completed.stdout.splitlines()[0].split(",")]
            result["gpu"] = {"available": True, "name": values[0], "total_mib": int(values[1]), "used_mib": int(values[2]), "free_mib": int(values[3]), "utilization_percent": int(values[4])}
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    return result
