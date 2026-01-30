"""Tests for FeedbackSequencerWidget.

Verifies that the widget provides user feedback on validation errors
instead of failing silently.
"""

from __future__ import annotations

import os

os.environ["ANDOR_MOCK"] = "1"

import pytest
from unittest.mock import patch, MagicMock

from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication, QMessageBox


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
    return DynamicInputsWidget()


@pytest.fixture
def queue_runner(hw_manager):
    from andor_qt.core.experiment_queue import ExperimentQueueRunner
    return ExperimentQueueRunner(hw_manager)


@pytest.fixture
def adapter(inputs_widget, hw_manager, queue_runner):
    from andor_qt.core.sequencer_adapter import SequencerAdapter
    return SequencerAdapter(inputs_widget, hw_manager, queue_runner)


@pytest.fixture
def feedback_widget(adapter):
    """Create a fresh FeedbackSequencerWidget for each test."""
    from andor_qt.widgets.inputs import FeedbackSequencerWidget

    sequencer_inputs = [
        "exposure_time", "center_wavelength", "grating",
        "hbin", "num_accumulations", "delay_position",
    ]
    widget = FeedbackSequencerWidget(
        inputs=sequencer_inputs,
        parent=adapter,
    )
    return widget


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


class TestFeedbackSequencerWidgetInitialization:
    """Test widget initialization."""

    def test_widget_created_successfully(self, feedback_widget):
        """Widget is created without errors."""
        assert feedback_widget is not None

    def test_widget_has_names_choices(self, feedback_widget):
        """Widget has parameter choices populated."""
        assert len(feedback_widget.names_choices) > 0
        assert "Exposure Time" in feedback_widget.names_choices

    def test_widget_has_last_queue_count(self, feedback_widget):
        """Widget tracks last queue count."""
        assert hasattr(feedback_widget, "last_queue_count")
        assert feedback_widget.last_queue_count == 0


class TestFeedbackOnEmptySequence:
    """Test feedback when sequence is empty."""

    def test_empty_sequence_shows_warning(self, feedback_widget):
        """Empty sequence shows warning dialog."""
        # Clear any existing data
        clear_sequence_tree(feedback_widget)

        with patch.object(feedback_widget, "_show_warning") as mock_warning:
            feedback_widget.queue_sequence()
            mock_warning.assert_called_once()
            args = mock_warning.call_args[0]
            assert "Empty Sequence" in args[0]

    def test_empty_sequence_queues_zero(self, feedback_widget):
        """Empty sequence queues zero procedures."""
        clear_sequence_tree(feedback_widget)

        with patch.object(feedback_widget, "_show_warning"):
            feedback_widget.queue_sequence()

        assert feedback_widget.last_queue_count == 0


class TestFeedbackOnValidSequence:
    """Test feedback when sequence is valid."""

    def test_valid_sequence_shows_info(self, feedback_widget, queue_runner):
        """Valid sequence shows info dialog with count."""
        # Add a sequence item
        feedback_widget._add_tree_item(level=0, parameter="Exposure Time")

        # Set sequence value
        model = feedback_widget.tree.model()
        idx = model.index(0, 2, QModelIndex())
        model.setData(idx, "[0.1, 0.2]")

        with patch.object(feedback_widget, "_show_info") as mock_info:
            feedback_widget.queue_sequence()
            mock_info.assert_called_once()
            args = mock_info.call_args[0]
            assert "Sequence Queued" in args[0]
            assert "2" in args[1]  # 2 measurements

    def test_valid_sequence_updates_last_queue_count(self, feedback_widget, queue_runner):
        """Valid sequence updates last_queue_count."""
        clear_sequence_tree(feedback_widget)
        feedback_widget._add_tree_item(level=0, parameter="Exposure Time")

        model = feedback_widget.tree.model()
        idx = model.index(0, 2, QModelIndex())
        model.setData(idx, "[0.1, 0.2, 0.3]")

        with patch.object(feedback_widget, "_show_info"):
            feedback_widget.queue_sequence()

        assert feedback_widget.last_queue_count == 3


class TestFeedbackOnInvalidSyntax:
    """Test feedback when sequence syntax is invalid."""

    def test_invalid_syntax_shows_error(self, feedback_widget):
        """Invalid sequence syntax shows error dialog."""
        # Add a sequence item with invalid syntax
        clear_sequence_tree(feedback_widget)
        feedback_widget._add_tree_item(level=0, parameter="Exposure Time")

        model = feedback_widget.tree.model()
        idx = model.index(0, 2, QModelIndex())
        model.setData(idx, "invalid_python_syntax[[[")

        with patch.object(feedback_widget, "_show_error") as mock_error:
            feedback_widget.queue_sequence()
            mock_error.assert_called_once()
            args = mock_error.call_args[0]
            assert "Invalid Sequence" in args[0]


class TestFeedbackOnMissingSequence:
    """Test feedback when sequence parameter has no value."""

    def test_missing_value_shows_error(self, feedback_widget):
        """Missing sequence value shows error dialog."""
        # Add item but don't set sequence value
        clear_sequence_tree(feedback_widget)
        feedback_widget._add_tree_item(level=0, parameter="Exposure Time")

        # Leave the sequence column empty (it defaults to empty string)

        with patch.object(feedback_widget, "_show_error") as mock_error:
            feedback_widget.queue_sequence()
            # Should show either "Invalid Sequence" or "Missing Sequence" error
            mock_error.assert_called_once()
