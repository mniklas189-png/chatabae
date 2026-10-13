"""Own child processes, including their descendants, without a spawn race."""
from __future__ import annotations

import ctypes
import os
import subprocess
from pathlib import Path

if os.name == "nt":
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                    ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                    ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                    ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                    ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
                    ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
                    ("hStdError", wintypes.HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                    ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION)]
    kernel.CreateProcessW.restype = wintypes.BOOL
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]


class OwnedProcess:
    def __init__(self, pid: int, handle=None, popen=None):
        self.pid, self.handle, self.popen = pid, handle, popen

    def poll(self):
        if self.popen:
            return self.popen.poll()
        if not self.handle:
            return 0
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return None if code.value == 259 else code.value

    def terminate(self):
        if self.poll() is not None:
            return
        if self.popen:
            self.popen.terminate()
        else:
            kernel.TerminateProcess(self.handle, 1)

    def wait(self, timeout: float = 5):
        if self.popen:
            return self.popen.wait(timeout=timeout)
        if kernel.WaitForSingleObject(self.handle, int(timeout * 1000)) == 258:
            raise TimeoutError(f"Process {self.pid} did not exit")
        return self.poll()

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None


class ProcessJob:
    def __init__(self):
        self.children: list[OwnedProcess] = []
        self.handle = None
        if os.name == "nt":
            self.handle = kernel.CreateJobObjectW(None, None)
            if not self.handle:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = EXTENDED_LIMIT()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                self.close()
                raise ctypes.WinError(ctypes.get_last_error())

    def spawn(self, args: list[str], cwd: Path, env: dict[str, str], log: Path) -> OwnedProcess:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("ab", buffering=0) as output, open(os.devnull, "rb") as input_file:
            if os.name != "nt":
                process = subprocess.Popen(args, cwd=cwd, env=env, stdin=input_file,
                                           stdout=output, stderr=output, start_new_session=True)
                owned = OwnedProcess(process.pid, popen=process)
            else:
                out_handle = msvcrt.get_osfhandle(output.fileno())
                in_handle = msvcrt.get_osfhandle(input_file.fileno())
                os.set_handle_inheritable(out_handle, True)
                os.set_handle_inheritable(in_handle, True)
                startup = STARTUPINFO()
                startup.cb = ctypes.sizeof(startup)
                startup.dwFlags = 0x100 | 0x1  # USESTDHANDLES | USESHOWWINDOW
                startup.wShowWindow = 0
                startup.hStdInput = in_handle
                startup.hStdOutput = startup.hStdError = out_handle
                info = PROCESS_INFORMATION()
                command = ctypes.create_unicode_buffer(subprocess.list2cmdline(args))
                environment = ctypes.create_unicode_buffer("\0".join(
                    f"{k}={v}" for k, v in sorted(env.items(), key=lambda x: x[0].upper())) + "\0\0")
                # Suspend before assignment; descendants cannot escape during startup.
                flags = 0x4 | 0x400 | 0x08000000  # SUSPENDED | UNICODE_ENV | NO_WINDOW
                if not kernel.CreateProcessW(args[0], command, None, None, True, flags,
                                             environment, str(cwd), ctypes.byref(startup), ctypes.byref(info)):
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    if not kernel.AssignProcessToJobObject(self.handle, info.hProcess):
                        kernel.TerminateProcess(info.hProcess, 1)
                        kernel.CloseHandle(info.hProcess)
                        raise ctypes.WinError(ctypes.get_last_error())
                    if kernel.ResumeThread(info.hThread) == 0xFFFFFFFF:
                        kernel.TerminateProcess(info.hProcess, 1)
                        kernel.CloseHandle(info.hProcess)
                        raise ctypes.WinError(ctypes.get_last_error())
                finally:
                    kernel.CloseHandle(info.hThread)
                owned = OwnedProcess(info.dwProcessId, handle=info.hProcess)
        self.children.append(owned)
        return owned

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None
        if os.name != "nt":
            import signal
            for process in self.children:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        for process in self.children:
            process.close()


class InstanceLock:
    def __init__(self, directory: Path):
        import hashlib
        self.handle = None
        self.file = None
        name = hashlib.sha256(str(directory.resolve()).casefold().encode()).hexdigest()[:24]
        if os.name == "nt":
            self.handle = kernel.CreateMutexW(None, False, f"Local\\Chatabae-{name}")
            if not self.handle:
                raise ctypes.WinError(ctypes.get_last_error())
            if kernel.WaitForSingleObject(self.handle, 0) not in (0, 0x80):
                kernel.CloseHandle(self.handle)
                self.handle = None
                raise RuntimeError("Chatabae läuft bereits für dieses Datenverzeichnis.")
        else:
            import fcntl
            directory.mkdir(parents=True, exist_ok=True)
            self.file = (directory / "instance.lock").open("a")
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                self.file.close()
                raise RuntimeError("Chatabae is already running") from exc

    def close(self):
        if self.handle:
            kernel.ReleaseMutex(self.handle)
            kernel.CloseHandle(self.handle)
            self.handle = None
        if self.file:
            self.file.close()
