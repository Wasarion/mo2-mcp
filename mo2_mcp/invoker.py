"""Run callables on MO2's GUI thread and wait for the result from a worker thread.

MO2's plugin API is not thread-safe, so every mobase call goes through here.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot


class _Job:
    def __init__(self, fn: Callable[[], Any]):
        self.fn = fn
        self.done = threading.Event()
        self.cancelled = False
        self.result: Any = None
        self.error: BaseException | None = None

    def run(self) -> None:
        if self.cancelled:
            return
        try:
            self.result = self.fn()
        except BaseException as e:  # noqa: BLE001 - re-raised in the caller's thread
            self.error = e
        finally:
            self.done.set()


class MainThreadInvoker(QObject):
    """Create this on the GUI thread (MO2 calls IPlugin.init there)."""

    _submit = pyqtSignal(object)  # pyright: ignore[reportCallIssue]

    def __init__(self) -> None:
        super().__init__()
        self._gui_thread = threading.current_thread()
        self._submit.connect(self._run, Qt.ConnectionType.QueuedConnection)

    @pyqtSlot(object)
    def _run(self, job: _Job) -> None:
        job.run()

    def invoke(self, fn: Callable[[], Any], timeout: float = 60.0) -> Any:
        if threading.current_thread() is self._gui_thread:
            return fn()
        job = _Job(fn)
        self._submit.emit(job)
        if not job.done.wait(timeout):
            job.cancelled = True
            raise TimeoutError(
                f"MO2 did not respond within {timeout:.0f} s (busy, or a dialog is open)."
            )
        if job.error is not None:
            raise job.error
        return job.result
