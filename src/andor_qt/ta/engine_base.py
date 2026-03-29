"""Shared QThread lifecycle base class for TA engines.

Both ``TransientAbsorptionEngine`` and ``TAMonitorEngine`` follow the same
pattern for thread creation, worker setup, start-guard, abort, and user
confirmation. ``_EngineBase`` provides these common operations so that
subclasses only implement their own signals and control methods.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal

log = logging.getLogger(__name__)


class _EngineBase(QObject):
    """Base class providing shared QThread lifecycle management.

    Subclasses must:
    - Create a worker (``QObject`` with ``run()``, ``_abort``, ``_user_response``
      attributes) and pass it to ``__init__``.
    - Forward worker-specific signals to engine-level signals in their own
      ``__init__``.
    - Implement their public ``start_*()`` method, calling ``_start_worker()``
      after ``worker.setup()``.

    Args:
        worker: Worker QObject that will be moved to the managed QThread.
        completion_signals: List of worker signals that indicate the run is
            finished (e.g. ``[worker.finished, worker.error]``). Each is
            connected to ``QThread.quit`` so the thread stops cleanly.
        parent: Optional parent QObject.
    """

    def __init__(self, worker: QObject, completion_signals: list[Signal], parent=None):
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = worker
        self._worker.moveToThread(self._thread)

        for sig in completion_signals:
            sig.connect(self._thread.quit)

        self._thread.started.connect(self._worker.run)

    def _start_worker(self) -> None:
        """Start the thread if not already running."""
        if self._thread.isRunning():
            log.warning("Engine already running — ignoring start request")
            return
        self._thread.start()

    @property
    def is_running(self) -> bool:
        """Return True if the worker thread is currently running."""
        return self._thread.isRunning()

    def _abort_worker(self) -> None:
        """Set the worker's abort event and unblock any user-response wait.

        Checks for both ``_abort`` and ``_abort_event`` attribute names
        since the scan worker uses ``_abort_event`` while the monitor worker
        uses ``_abort``.
        """
        for attr in ("_abort", "_abort_event"):
            evt = getattr(self._worker, attr, None)
            if evt is not None:
                evt.set()
        if hasattr(self._worker, "_user_response"):
            self._worker._user_response.set()

    def user_confirmed(self) -> None:
        """Forward user confirmation to the worker (for interactive prompts)."""
        self._worker.user_confirmed()
