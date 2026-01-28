"""Tests for trace overlay integration in the main window.

Verifies TraceListWidget is present, signal connections work,
and acquisitions produce new traces.
"""

from __future__ import annotations

import os

os.environ["ANDOR_MOCK"] = "1"

import numpy as np
import pytest

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def main_window(qt_app, hardware_manager, wait_for):
    """Create main window with hardware initialized."""
    completed = []
    hardware_manager.initialize(on_complete=lambda: completed.append(True))
    wait_for(lambda: len(completed) > 0)

    from andor_qt.windows.main_window import AndorSpectrometerWindow

    window = AndorSpectrometerWindow()
    yield window


class TestTraceListPresent:
    """Verify TraceListWidget exists in the right panel."""

    def test_trace_list_in_right_panel(self, main_window):
        """Main window has a TraceListWidget attribute."""
        from andor_qt.widgets.display.trace_list import TraceListWidget

        assert hasattr(main_window, "_trace_list")
        assert isinstance(main_window._trace_list, TraceListWidget)


class TestAcquisitionAddsTrace:
    """Verify that incoming spectrum data adds a trace."""

    def test_acquisition_adds_trace_to_plot(self, main_window):
        """_on_spectrum_ready adds a trace to the plot."""
        wl = np.linspace(400, 700, 100)
        intens = np.ones(100) * 500.0

        main_window._on_spectrum_ready(wl, intens)

        traces = main_window._spectrum_plot.get_traces()
        assert len(traces) >= 1

    def test_trace_list_syncs_with_plot(self, main_window):
        """Adding a trace to the plot adds a row to the trace list."""
        wl = np.linspace(400, 700, 100)
        intens = np.ones(100) * 500.0

        initial_count = main_window._trace_list.row_count()
        main_window._on_spectrum_ready(wl, intens)

        assert main_window._trace_list.row_count() == initial_count + 1


class TestVisibilityToggle:
    """Verify visibility toggle syncs list → plot."""

    def test_visibility_toggle_hides_trace_on_plot(self, main_window):
        """Toggling visibility in the list hides the trace on the plot."""
        wl = np.linspace(400, 700, 100)
        intens = np.ones(100) * 500.0

        main_window._on_spectrum_ready(wl, intens)
        traces = main_window._spectrum_plot.get_traces()
        tid = traces[-1].id

        # Toggle off
        main_window._trace_list.visibility_toggled.emit(tid, False)
        trace = [t for t in main_window._spectrum_plot.get_traces() if t.id == tid][0]
        assert trace.visible is False


class TestRemoveTrace:
    """Verify remove trace syncs list → plot."""

    def test_remove_trace_from_list_removes_from_plot(self, main_window):
        """Requesting remove in the list removes from the plot."""
        wl = np.linspace(400, 700, 100)
        intens = np.ones(100) * 500.0

        main_window._on_spectrum_ready(wl, intens)
        traces = main_window._spectrum_plot.get_traces()
        tid = traces[-1].id
        count_before = len(traces)

        main_window._trace_list.trace_remove_requested.emit(tid)
        assert len(main_window._spectrum_plot.get_traces()) == count_before - 1


class TestClearAll:
    """Verify clear all syncs list ↔ plot."""

    def test_clear_all_clears_both_list_and_plot(self, main_window):
        """Clear All clears both the plot and the list."""
        wl = np.linspace(400, 700, 100)
        intens = np.ones(100) * 500.0

        main_window._on_spectrum_ready(wl, intens)
        main_window._on_spectrum_ready(wl, intens * 2)

        main_window._trace_list.clear_all_requested.emit()

        assert len(main_window._spectrum_plot.get_traces()) == 0
        assert main_window._trace_list.row_count() == 0
