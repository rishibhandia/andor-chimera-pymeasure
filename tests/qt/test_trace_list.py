"""Tests for TraceListWidget — compact list of spectrum traces.

Tests visibility checkbox, remove button, clear all, and signal emission.
"""

from __future__ import annotations

import os

os.environ["ANDOR_MOCK"] = "1"

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def trace_list(qt_app):
    from andor_qt.widgets.display.trace_list import TraceListWidget

    widget = TraceListWidget()
    yield widget


class TestAddTraceRow:
    """Tests for adding trace rows to the list."""

    def test_add_trace_row(self, trace_list):
        """add_trace adds a row with the given label."""
        trace_list.add_trace(1, "Trace 1", "#1f77b4")
        assert trace_list.row_count() == 1

    def test_add_multiple_trace_rows(self, trace_list):
        """Adding multiple traces creates multiple rows."""
        trace_list.add_trace(1, "A", "#1f77b4")
        trace_list.add_trace(2, "B", "#ff7f0e")
        trace_list.add_trace(3, "C", "#2ca02c")
        assert trace_list.row_count() == 3


class TestCheckboxToggle:
    """Tests for visibility checkbox behavior."""

    def test_checkbox_toggles_visibility(self, trace_list):
        """Checking/unchecking the checkbox emits visibility_toggled."""
        received = []
        trace_list.visibility_toggled.connect(
            lambda tid, vis: received.append((tid, vis))
        )

        trace_list.add_trace(1, "Toggle", "#1f77b4")
        # The checkbox starts checked; uncheck it
        trace_list._toggle_visibility(1, False)

        assert len(received) == 1
        assert received[0] == (1, False)

    def test_signal_on_visibility_toggle(self, trace_list):
        """visibility_toggled signal includes trace_id and state."""
        received = []
        trace_list.visibility_toggled.connect(
            lambda tid, vis: received.append((tid, vis))
        )

        trace_list.add_trace(5, "Vis", "#2ca02c")
        trace_list._toggle_visibility(5, True)

        assert len(received) == 1
        assert received[0] == (5, True)


class TestRemoveTraceRow:
    """Tests for removing a trace row."""

    def test_remove_trace_row(self, trace_list):
        """remove_trace removes the row from the list."""
        trace_list.add_trace(1, "X", "#1f77b4")
        trace_list.add_trace(2, "Y", "#ff7f0e")

        trace_list.remove_trace(1)
        assert trace_list.row_count() == 1

    def test_signal_on_remove(self, trace_list):
        """trace_remove_requested signal fires when remove button clicked."""
        removed = []
        trace_list.trace_remove_requested.connect(lambda tid: removed.append(tid))

        trace_list.add_trace(10, "Rm", "#d62728")
        trace_list._request_remove(10)

        assert len(removed) == 1
        assert removed[0] == 10


class TestClearAll:
    """Tests for clearing all trace rows."""

    def test_clear_all_traces(self, trace_list):
        """clear() removes all rows."""
        trace_list.add_trace(1, "A", "#1f77b4")
        trace_list.add_trace(2, "B", "#ff7f0e")
        trace_list.clear()
        assert trace_list.row_count() == 0

    def test_signal_on_clear_all(self, trace_list):
        """clear_all_requested signal fires when Clear All button clicked."""
        cleared = []
        trace_list.clear_all_requested.connect(lambda: cleared.append(True))

        trace_list.add_trace(1, "A", "#1f77b4")
        trace_list._request_clear_all()

        assert len(cleared) == 1


class TestColorSwatch:
    """Tests for the color swatch display."""

    def test_color_swatch_displayed(self, trace_list):
        """Each trace row shows a colored swatch matching the trace color."""
        trace_list.add_trace(1, "Colored", "#ff7f0e")
        # The swatch should exist in the row widgets
        row_widget = trace_list._rows.get(1)
        assert row_widget is not None
        swatch = row_widget["swatch"]
        # Check that the swatch has the color set via stylesheet
        style = swatch.styleSheet()
        assert "#ff7f0e" in style.lower()
