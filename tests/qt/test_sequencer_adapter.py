"""Tests for SequencerAdapter — adapts our app for SequencerWidget.

Tests that the adapter provides the ManagedWindow-like interface
(procedure_class, make_procedure, queue) that SequencerWidget expects.
"""

from __future__ import annotations

import os

os.environ["ANDOR_MOCK"] = "1"

import pytest

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def hw_manager(qt_app, hardware_manager, wait_for):
    """Initialize hardware manager."""
    completed = []
    hardware_manager.initialize(on_complete=lambda: completed.append(True))
    wait_for(lambda: len(completed) > 0)
    return hardware_manager


@pytest.fixture
def inputs_widget(qt_app):
    from andor_qt.widgets.inputs import DynamicInputsWidget

    widget = DynamicInputsWidget()
    return widget


@pytest.fixture
def queue_runner(hw_manager):
    from andor_qt.core.experiment_queue import ExperimentQueueRunner

    return ExperimentQueueRunner(hw_manager)


@pytest.fixture
def adapter(inputs_widget, hw_manager, queue_runner):
    from andor_qt.core.sequencer_adapter import SequencerAdapter

    return SequencerAdapter(inputs_widget, hw_manager, queue_runner)


class TestProcedureClass:
    """Tests for the procedure_class property."""

    def test_adapter_has_procedure_class(self, adapter):
        """procedure_class returns a class, not an instance."""
        cls = adapter.procedure_class
        assert isinstance(cls, type)

    def test_adapter_procedure_class_fvb(self, adapter, inputs_widget):
        """In FVB mode, procedure_class is SpectrumProcedure."""
        from andor_qt.procedures import SpectrumProcedure

        # Ensure FVB mode (default)
        inputs_widget._read_mode_combo.setCurrentIndex(0)
        assert adapter.procedure_class is SpectrumProcedure

    def test_adapter_procedure_class_image(self, adapter, inputs_widget):
        """In Image mode, procedure_class is ImageProcedure."""
        from andor_qt.procedures import ImageProcedure

        inputs_widget._read_mode_combo.setCurrentIndex(1)  # Image mode
        assert adapter.procedure_class is ImageProcedure


class TestMakeProcedure:
    """Tests for the make_procedure method."""

    def test_adapter_make_procedure_returns_configured_procedure(self, adapter):
        """make_procedure returns a Procedure with current form values."""
        from pymeasure.experiment import Procedure

        proc = adapter.make_procedure()
        assert isinstance(proc, Procedure)
        # Should have exposure_time set from the inputs widget
        assert hasattr(proc, "exposure_time")
        assert proc.exposure_time > 0


class TestQueue:
    """Tests for the queue method."""

    def test_adapter_queue_adds_to_runner(self, adapter, queue_runner):
        """queue() adds a procedure to the runner and starts execution."""
        import time

        from PySide6.QtWidgets import QApplication

        completed = []
        queue_runner.procedure_completed.connect(lambda idx: completed.append(idx))

        proc = adapter.make_procedure()
        adapter.queue(procedure=proc)

        # Wait for completion (queue() auto-starts the runner)
        start = time.time()
        while time.time() - start < 15.0:
            app = QApplication.instance()
            if app:
                app.processEvents()
            if len(completed) > 0:
                break
            time.sleep(0.05)

        assert len(completed) == 1

    def test_adapter_queue_without_procedure_creates_one(self, adapter, queue_runner):
        """queue() without a procedure argument creates one from make_procedure."""
        import time

        from PySide6.QtWidgets import QApplication

        completed = []
        queue_runner.procedure_completed.connect(lambda idx: completed.append(idx))

        adapter.queue()

        start = time.time()
        while time.time() - start < 15.0:
            app = QApplication.instance()
            if app:
                app.processEvents()
            if len(completed) > 0:
                break
            time.sleep(0.05)

        assert len(completed) >= 1


class TestSequenceableInputs:
    """Tests for the inputs list matching procedure parameters."""

    def test_sequenceable_inputs_fvb(self, adapter, inputs_widget):
        """FVB sequenceable inputs match SpectrumProcedure parameters."""
        inputs_widget._read_mode_combo.setCurrentIndex(0)
        inputs = adapter.sequenceable_inputs
        assert "exposure_time" in inputs
        assert "center_wavelength" in inputs
        assert "grating" in inputs

    def test_sequenceable_inputs_image(self, adapter, inputs_widget):
        """Image sequenceable inputs match ImageProcedure parameters."""
        inputs_widget._read_mode_combo.setCurrentIndex(1)
        inputs = adapter.sequenceable_inputs
        assert "exposure_time" in inputs
        assert "center_wavelength" in inputs
        assert "vbin" in inputs
