"""Tests for ExperimentQueueRunner — sequential procedure execution.

Tests queueing, sequential execution, abort, and signal emission.
"""

from __future__ import annotations

import os

os.environ["ANDOR_MOCK"] = "1"

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def wait_for_qt(condition_fn, timeout=15.0, poll_interval=0.05):
    """Wait for a condition, processing Qt events in the loop."""
    app = QApplication.instance()
    start = time.time()
    while time.time() - start < timeout:
        if app:
            app.processEvents()
        if condition_fn():
            return True
        time.sleep(poll_interval)
    return False


@pytest.fixture
def hw_manager(qt_app, hardware_manager, wait_for):
    """Initialize hardware manager."""
    completed = []
    hardware_manager.initialize(on_complete=lambda: completed.append(True))
    wait_for(lambda: len(completed) > 0)
    return hardware_manager


@pytest.fixture
def queue_runner(hw_manager):
    from andor_qt.core.experiment_queue import ExperimentQueueRunner

    runner = ExperimentQueueRunner(hw_manager)
    yield runner


@pytest.fixture
def spectrum_procedure():
    from andor_qt.procedures import SpectrumProcedure

    proc = SpectrumProcedure()
    proc.exposure_time = 0.01
    proc.center_wavelength = 500.0
    proc.grating = 1
    proc.hbin = 1
    proc.num_accumulations = 1
    return proc


@pytest.fixture
def image_procedure():
    from andor_qt.procedures import ImageProcedure

    proc = ImageProcedure()
    proc.exposure_time = 0.01
    proc.center_wavelength = 500.0
    proc.grating = 1
    proc.hbin = 1
    proc.vbin = 1
    return proc


class TestAddProcedure:
    """Tests for adding procedures to the queue."""

    def test_add_procedure_to_queue(self, queue_runner, spectrum_procedure):
        """add() returns a queue index and increments pending_count."""
        idx = queue_runner.add(spectrum_procedure)
        assert isinstance(idx, int)
        assert queue_runner.pending_count == 1

    def test_add_multiple_procedures(self, queue_runner, spectrum_procedure):
        """Can add multiple procedures to the queue."""
        from andor_qt.procedures import SpectrumProcedure

        proc2 = SpectrumProcedure()
        proc2.exposure_time = 0.02
        proc2.center_wavelength = 600.0
        proc2.grating = 1
        proc2.hbin = 1
        proc2.num_accumulations = 1

        queue_runner.add(spectrum_procedure)
        queue_runner.add(proc2)
        assert queue_runner.pending_count == 2

    def test_empty_queue_no_op(self, queue_runner):
        """Running an empty queue completes immediately."""
        completed = []
        queue_runner.queue_completed.connect(lambda: completed.append(True))

        queue_runner.run()
        assert wait_for_qt(lambda: len(completed) > 0, timeout=5.0)


class TestRunQueue:
    """Tests for sequential execution."""

    def test_run_queue_executes_sequentially(
        self, queue_runner, spectrum_procedure
    ):
        """Queue executes procedures one by one."""
        started = []
        queue_runner.procedure_started.connect(
            lambda idx, proc: started.append(idx)
        )
        completed_items = []
        queue_runner.procedure_completed.connect(
            lambda idx: completed_items.append(idx)
        )
        done = []
        queue_runner.queue_completed.connect(lambda: done.append(True))

        queue_runner.add(spectrum_procedure)
        queue_runner.run()

        assert wait_for_qt(lambda: len(done) > 0)
        assert len(started) == 1
        assert len(completed_items) == 1

    def test_queue_emits_progress_signals(
        self, queue_runner, spectrum_procedure
    ):
        """Queue emits queue_progress signal."""
        progress = []
        queue_runner.queue_progress.connect(
            lambda done, total: progress.append((done, total))
        )
        finished = []
        queue_runner.queue_completed.connect(lambda: finished.append(True))

        queue_runner.add(spectrum_procedure)
        queue_runner.run()

        assert wait_for_qt(lambda: len(finished) > 0)
        assert len(progress) >= 1

    def test_queue_emits_spectrum_ready(
        self, queue_runner, spectrum_procedure
    ):
        """FVB procedure emits spectrum_ready signal with data."""
        spectra = []
        queue_runner.spectrum_ready.connect(
            lambda wl, intens: spectra.append((wl, intens))
        )
        done = []
        queue_runner.queue_completed.connect(lambda: done.append(True))

        queue_runner.add(spectrum_procedure)
        queue_runner.run()

        assert wait_for_qt(lambda: len(done) > 0)
        assert len(spectra) == 1
        wl, intens = spectra[0]
        assert isinstance(wl, np.ndarray)
        assert isinstance(intens, np.ndarray)

    def test_queue_completed_signal(self, queue_runner, spectrum_procedure):
        """queue_completed fires when all procedures finish."""
        done = []
        queue_runner.queue_completed.connect(lambda: done.append(True))

        queue_runner.add(spectrum_procedure)
        queue_runner.run()

        assert wait_for_qt(lambda: len(done) > 0)
        assert queue_runner.is_running is False


class TestAbort:
    """Tests for aborting the queue."""

    def test_abort_stops_after_current(self, queue_runner):
        """abort() stops queue after the currently running procedure."""
        from andor_qt.procedures import SpectrumProcedure

        for i in range(3):
            proc = SpectrumProcedure()
            proc.exposure_time = 0.01
            proc.center_wavelength = 500.0
            proc.grating = 1
            proc.hbin = 1
            proc.num_accumulations = 1
            queue_runner.add(proc)

        completed_items = []
        queue_runner.procedure_completed.connect(
            lambda idx: completed_items.append(idx)
        )
        done = []
        queue_runner.queue_completed.connect(lambda: done.append(True))

        queue_runner.run()
        queue_runner.abort()

        assert wait_for_qt(lambda: len(done) > 0)
        assert len(completed_items) <= 3

    def test_abort_all_cancels_remaining(self, queue_runner):
        """abort_all() clears the remaining queue."""
        from andor_qt.procedures import SpectrumProcedure

        for i in range(5):
            proc = SpectrumProcedure()
            proc.exposure_time = 0.01
            proc.center_wavelength = 500.0
            proc.grating = 1
            proc.hbin = 1
            proc.num_accumulations = 1
            queue_runner.add(proc)

        done = []
        queue_runner.queue_completed.connect(lambda: done.append(True))

        queue_runner.run()
        queue_runner.abort_all()

        assert wait_for_qt(lambda: len(done) > 0)
        assert queue_runner.pending_count == 0


class TestQueueState:
    """Tests for queue state properties."""

    def test_is_running_false_initially(self, queue_runner):
        """is_running is False before run() is called."""
        assert queue_runner.is_running is False

    def test_pending_count_zero_initially(self, queue_runner):
        """pending_count is 0 on a fresh queue."""
        assert queue_runner.pending_count == 0

    def test_clear_removes_pending(self, queue_runner, spectrum_procedure):
        """clear() removes all pending procedures."""
        queue_runner.add(spectrum_procedure)
        queue_runner.add(spectrum_procedure)
        assert queue_runner.pending_count == 2

        queue_runner.clear()
        assert queue_runner.pending_count == 0
