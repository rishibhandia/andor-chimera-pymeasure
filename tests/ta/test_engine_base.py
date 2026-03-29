"""Tests for _EngineBase shared QThread lifecycle."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from andor_qt.ta.engine_base import _EngineBase


class _DummyWorker(QObject):
    """Minimal worker for testing _EngineBase."""
    finished = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._abort = threading.Event()
        self._user_response = threading.Event()

    def setup(self, **kwargs):
        self._abort.clear()
        self._user_response.clear()

    def run(self):
        self.finished.emit()

    def stop(self):
        self._abort.set()

    def user_confirmed(self):
        self._user_response.set()


class _DummyEngine(_EngineBase):
    finished = Signal()

    def __init__(self, parent=None):
        worker = _DummyWorker()
        super().__init__(worker, [worker.finished, worker.error], parent)
        self._worker.finished.connect(self.finished)

    def start(self):
        self._worker.setup()
        self._start_worker()


class TestEngineBase:
    def test_creates_successfully(self, qt_app):
        engine = _DummyEngine()
        assert engine is not None
        engine.deleteLater()

    def test_is_running_false_initially(self, qt_app):
        engine = _DummyEngine()
        assert not engine.is_running
        engine.deleteLater()

    def test_abort_worker_sets_event(self, qt_app):
        engine = _DummyEngine()
        engine._abort_worker()
        assert engine._worker._abort.is_set()
        engine.deleteLater()

    def test_user_confirmed_sets_event(self, qt_app):
        engine = _DummyEngine()
        engine.user_confirmed()
        assert engine._worker._user_response.is_set()
        engine.deleteLater()

    def test_start_and_finish(self, qt_app):
        import time
        engine = _DummyEngine()
        done = []
        engine.finished.connect(lambda: done.append(True))
        engine.start()
        app = QApplication.instance()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            app.processEvents()
            if done:
                break
            time.sleep(0.05)
        engine.deleteLater()
        assert done, "Engine should have finished"

    def test_double_start_ignored(self, qt_app):
        """Starting while already running should be a no-op."""
        import time
        engine = _DummyEngine()
        # Monkey-patch worker.run to block briefly
        original_run = engine._worker.run

        def _slow_run():
            time.sleep(0.3)
            original_run()

        engine._worker.run = _slow_run
        engine.start()
        engine.start()  # should not crash
        app = QApplication.instance()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            app.processEvents()
            if not engine.is_running:
                break
            time.sleep(0.05)
        engine.deleteLater()
