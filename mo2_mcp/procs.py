"""Track applications Claude started through MO2 (xEdit, LOOT, DynDOLOD, ...)."""

from __future__ import annotations

import itertools
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol


class Backend(Protocol):
    def pid_from_handle(self, handle: int) -> int: ...
    def open(self, pid: int) -> int: ...
    def exit_code(self, handle: int) -> int | None: ...  # None = still running
    def close(self, handle: int) -> None: ...


class WinBackend:
    SYNCHRONIZE = 0x00100000
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    WAIT_OBJECT_0 = 0

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        k32.GetProcessId.argtypes = [wintypes.HANDLE]
        k32.GetProcessId.restype = wintypes.DWORD
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.GetExitCodeProcess.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        self._k32 = k32
        self._dword = wintypes.DWORD

    def pid_from_handle(self, handle: int) -> int:
        return int(self._k32.GetProcessId(handle))

    def open(self, pid: int) -> int:
        h = self._k32.OpenProcess(self.SYNCHRONIZE | self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return int(h or 0)

    def exit_code(self, handle: int) -> int | None:
        if self._k32.WaitForSingleObject(handle, 0) != self.WAIT_OBJECT_0:
            return None
        code = self._dword(0)
        if not self._k32.GetExitCodeProcess(handle, self._ct.byref(code)):
            return -1
        return int(code.value)

    def close(self, handle: int) -> None:
        self._k32.CloseHandle(handle)


@dataclass
class Run:
    id: int
    title: str
    args: list[str]
    pid: int
    started: float
    handle: int = 0
    exit_code: int | None = None
    finished: float | None = None
    tracked: bool = True

    @property
    def running(self) -> bool:
        return self.finished is None

    def describe(self) -> dict[str, Any]:
        end = self.finished or time.time()
        status = "running" if self.running else "finished"
        if not self.tracked:
            status = "started (cannot be tracked)"
        d: dict[str, Any] = {
            "run_id": self.id,
            "executable": self.title,
            "args": self.args,
            "pid": self.pid,
            "status": status,
            "seconds": round(end - self.started, 1),
        }
        if not self.running:
            d["exit_code"] = self.exit_code
        return d


class RunTracker:
    def __init__(self, backend: Backend | None = None):
        if backend is None and sys.platform == "win32":
            backend = WinBackend()
        self._backend = backend
        self._runs: dict[int, Run] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, title: str, args: list[str], mo_handle: int) -> Run:
        pid = self._backend.pid_from_handle(mo_handle) if self._backend else 0
        # Hold our own handle so the PID cannot be reused while we watch it.
        own = self._backend.open(pid) if (self._backend and pid) else 0
        run = Run(next(self._ids), title, args, pid, time.time(), own)
        if not own:
            run.finished, run.tracked = time.time(), False
        with self._lock:
            self._runs[run.id] = run
        return run

    def poll(self, run: Run) -> Run:
        with self._lock:
            if run.running and self._backend and run.handle:
                code = self._backend.exit_code(run.handle)
                if code is not None:
                    run.exit_code, run.finished = code, time.time()
                    self._backend.close(run.handle)
                    run.handle = 0
        return run

    def get(self, run_id: int) -> Run | None:
        run = self._runs.get(run_id)
        return self.poll(run) if run else None

    def all(self) -> list[Run]:
        return [self.poll(r) for r in list(self._runs.values())]

    def active(self) -> list[Run]:
        return [r for r in self.all() if r.running]

    def wait(self, run: Run, timeout: float) -> Run:
        deadline = time.time() + timeout
        while self.poll(run).running and time.time() < deadline:
            time.sleep(0.5)
        return run
