"""Tests for PyMeasure Sequencer integration in the main window.

Verifies the SequencerWidget is present, correctly initialized,
and connected to the ExperimentQueueRunner.
"""

from __future__ import annotations

import os

os.environ["ANDOR_MOCK"] = "1"

import time

import numpy as np
import pytest

from PySide6.QtWidgets import QApplication, QTabWidget


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
def main_window(qt_app, hardware_manager, wait_for):
    """Create main window with hardware initialized."""
    completed = []
    hardware_manager.initialize(on_complete=lambda: completed.append(True))
    wait_for(lambda: len(completed) > 0)

    from andor_qt.windows.main_window import AndorSpectrometerWindow

    window = AndorSpectrometerWindow()
    yield window


class TestSequencerTab:
    """Verify the Sequencer tab exists in the main window."""

    def test_main_window_has_sequencer_tab(self, main_window):
        """Main window has a QTabWidget with Single and Sequence tabs."""
        assert hasattr(main_window, "_queue_tabs")
        tabs = main_window._queue_tabs
        assert isinstance(tabs, QTabWidget)
        assert tabs.count() == 2

    def test_single_tab_contains_queue_control(self, main_window):
        """The Single tab contains the QueueControlWidget."""
        from andor_qt.widgets.inputs import QueueControlWidget

        tabs = main_window._queue_tabs
        assert isinstance(tabs.widget(0), QueueControlWidget)

    def test_sequence_tab_contains_sequencer_widget(self, main_window):
        """The Sequence tab contains FeedbackSequencerWidget."""
        from andor_qt.widgets.inputs import FeedbackSequencerWidget

        tabs = main_window._queue_tabs
        assert isinstance(tabs.widget(1), FeedbackSequencerWidget)


class TestSequencerInitialization:
    """Verify sequencer components are properly initialized."""

    def test_sequencer_widget_initialized_with_correct_inputs(self, main_window):
        """SequencerWidget has inputs matching procedure parameters."""
        sw = main_window._sequencer_widget
        # Should have parameter attribute names from the procedure
        assert hasattr(sw, '_inputs')
        assert "exposure_time" in sw._inputs

    def test_queue_runner_exists(self, main_window):
        """Main window has an ExperimentQueueRunner."""
        from andor_qt.core.experiment_queue import ExperimentQueueRunner

        assert hasattr(main_window, "_queue_runner")
        assert isinstance(main_window._queue_runner, ExperimentQueueRunner)

    def test_sequencer_adapter_exists(self, main_window):
        """Main window has a SequencerAdapter."""
        from andor_qt.core.sequencer_adapter import SequencerAdapter

        assert hasattr(main_window, "_sequencer_adapter")
        assert isinstance(main_window._sequencer_adapter, SequencerAdapter)


class TestSequenceExecution:
    """Verify queued sequences produce data signals."""

    def test_queue_sequence_adds_to_experiment_queue(self, main_window):
        """Manually queueing through adapter executes the procedure."""
        runner = main_window._queue_runner

        completed = []
        runner.procedure_completed.connect(lambda idx: completed.append(idx))

        proc = main_window._sequencer_adapter.make_procedure()
        main_window._sequencer_adapter.queue(procedure=proc)

        # The adapter calls run() automatically, so wait for completion
        assert wait_for_qt(lambda: len(completed) > 0, timeout=15.0)

    def test_sequence_results_appear_as_traces(self, main_window):
        """Running a queued spectrum procedure produces a trace on the plot."""
        runner = main_window._queue_runner
        plot = main_window._spectrum_plot

        initial_traces = len(plot.get_traces())

        # Queue and run a procedure
        proc = main_window._sequencer_adapter.make_procedure()
        runner.add(proc)
        runner.run()

        assert wait_for_qt(lambda: not runner.is_running, timeout=15.0)
        # Process remaining events so spectrum_ready signal is delivered
        QApplication.instance().processEvents()

        assert len(plot.get_traces()) > initial_traces

    def test_abort_sequence_stops_execution(self, main_window):
        """Aborting the queue runner stops execution."""
        runner = main_window._queue_runner
        runner.abort_all()
        assert runner.pending_count == 0


def clear_sequence_tree(widget):
    """Remove all items from the sequence tree."""
    from PySide6.QtCore import QModelIndex

    model = widget.tree.model()
    root = QModelIndex()  # Invalid index = root
    # Remove all root items
    while model.rowCount(root) > 0:
        idx = model.index(0, 0, root)
        if idx.isValid():
            model.remove_node(idx)


class TestSequencerTreeWorkflow:
    """Test the full SequencerWidget tree workflow."""

    def test_add_root_item_creates_tree_node(self, main_window):
        """Adding a root item creates a node in the sequence tree."""
        from PySide6.QtCore import QModelIndex

        sw = main_window._sequencer_widget

        # Get initial row count
        model = sw.tree.model()
        root = QModelIndex()
        initial_rows = model.rowCount(root)

        # Add a root item programmatically
        sw._add_tree_item(level=0, parameter="Exposure Time")

        # Verify a row was added
        new_rows = model.rowCount(root)
        assert new_rows > initial_rows

    def test_sequence_with_valid_expression_queues_procedures(self, main_window):
        """Valid sequence expression queues multiple procedures."""
        from unittest.mock import patch
        from PySide6.QtCore import QModelIndex

        sw = main_window._sequencer_widget
        runner = main_window._queue_runner

        # Clear any existing sequence data
        clear_sequence_tree(sw)

        # Add a sequence item with valid expression
        sw._add_tree_item(level=0, parameter="Exposure Time")

        # Set a sequence expression in the tree model
        model = sw.tree.model()
        root = QModelIndex()
        # The sequence column is column 2
        idx = model.index(0, 2, root)
        model.setData(idx, "[0.1, 0.2, 0.3]")

        # Track queued procedures
        queued = []
        runner.procedure_started.connect(lambda i, p: queued.append(i))

        # Mock the info dialog to avoid blocking
        with patch.object(sw, "_show_info"):
            # Queue the sequence
            sw.queue_sequence()

        # Wait for procedures to be queued and run
        assert wait_for_qt(lambda: len(queued) >= 3, timeout=20.0), \
            f"Expected 3 procedures, got {len(queued)}"

    def test_names_choices_populated_from_procedure(self, main_window):
        """SequencerWidget has names_choices populated from procedure parameters."""
        sw = main_window._sequencer_widget

        # names_choices should have the display names from the procedure
        assert len(sw.names_choices) > 0
        assert "Exposure Time" in sw.names_choices
        assert "Center Wavelength" in sw.names_choices

    def test_empty_sequence_shows_warning(self, main_window):
        """Empty sequence tree shows warning dialog."""
        from unittest.mock import patch

        sw = main_window._sequencer_widget

        # Clear sequence data
        clear_sequence_tree(sw)

        # Queue the empty sequence with mocked warning dialog
        with patch.object(sw, "_show_warning") as mock_warning:
            sw.queue_sequence()
            mock_warning.assert_called_once()
            args = mock_warning.call_args[0]
            assert "Empty Sequence" in args[0]
