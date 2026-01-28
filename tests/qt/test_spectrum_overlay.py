"""Tests for multi-trace overlay support in SpectrumPlotWidget.

Tests the ability to add, remove, toggle, and manage multiple
spectrum traces on a single plot.
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
def spectrum_plot(qt_app):
    from andor_qt.widgets.display.spectrum_plot import SpectrumPlotWidget

    widget = SpectrumPlotWidget()
    yield widget


@pytest.fixture
def sample_data():
    """Generate sample wavelength/intensity arrays."""
    wavelengths = np.linspace(400, 700, 100)
    intensities = np.random.default_rng(42).uniform(0, 1000, 100)
    return wavelengths, intensities


class TestAddTrace:
    """Tests for adding traces to the plot."""

    def test_add_trace_creates_plot_curve(self, spectrum_plot, sample_data):
        """add_trace creates a PlotCurveItem and returns a trace ID."""
        wl, intens = sample_data
        trace_id = spectrum_plot.add_trace(wl, intens, label="Test")
        assert isinstance(trace_id, int)
        traces = spectrum_plot.get_traces()
        assert len(traces) == 1
        assert traces[0].id == trace_id

    def test_add_multiple_traces(self, spectrum_plot, sample_data):
        """Adding multiple traces gives distinct IDs and stores all."""
        wl, intens = sample_data
        id1 = spectrum_plot.add_trace(wl, intens, label="Trace 1")
        id2 = spectrum_plot.add_trace(wl, intens * 2, label="Trace 2")
        id3 = spectrum_plot.add_trace(wl, intens * 3, label="Trace 3")

        assert id1 != id2 != id3
        assert len(spectrum_plot.get_traces()) == 3

    def test_add_trace_without_wavelengths(self, spectrum_plot):
        """add_trace works when wavelengths is None (pixel axis)."""
        intens = np.ones(50)
        trace_id = spectrum_plot.add_trace(None, intens, label="No WL")
        traces = spectrum_plot.get_traces()
        assert len(traces) == 1
        assert traces[0].wavelengths is None

    def test_add_trace_auto_label(self, spectrum_plot, sample_data):
        """Traces get auto-generated labels when none provided."""
        wl, intens = sample_data
        spectrum_plot.add_trace(wl, intens)
        traces = spectrum_plot.get_traces()
        assert traces[0].label is not None
        assert len(traces[0].label) > 0


class TestRemoveTrace:
    """Tests for removing traces from the plot."""

    def test_remove_trace(self, spectrum_plot, sample_data):
        """remove_trace removes the trace from the plot."""
        wl, intens = sample_data
        id1 = spectrum_plot.add_trace(wl, intens, label="A")
        id2 = spectrum_plot.add_trace(wl, intens, label="B")

        spectrum_plot.remove_trace(id1)
        traces = spectrum_plot.get_traces()
        assert len(traces) == 1
        assert traces[0].id == id2

    def test_remove_nonexistent_trace_is_noop(self, spectrum_plot, sample_data):
        """Removing a non-existent trace ID does not raise."""
        wl, intens = sample_data
        spectrum_plot.add_trace(wl, intens)
        spectrum_plot.remove_trace(9999)  # Should not raise
        assert len(spectrum_plot.get_traces()) == 1


class TestToggleVisibility:
    """Tests for showing/hiding individual traces."""

    def test_toggle_trace_visibility(self, spectrum_plot, sample_data):
        """set_trace_visible toggles visibility flag and plot item."""
        wl, intens = sample_data
        tid = spectrum_plot.add_trace(wl, intens, label="Toggle")

        spectrum_plot.set_trace_visible(tid, False)
        trace = [t for t in spectrum_plot.get_traces() if t.id == tid][0]
        assert trace.visible is False

        spectrum_plot.set_trace_visible(tid, True)
        trace = [t for t in spectrum_plot.get_traces() if t.id == tid][0]
        assert trace.visible is True

    def test_toggle_nonexistent_trace_is_noop(self, spectrum_plot):
        """Toggling visibility of non-existent trace does not raise."""
        spectrum_plot.set_trace_visible(9999, False)  # Should not raise


class TestClearTraces:
    """Tests for clearing all traces."""

    def test_clear_traces(self, spectrum_plot, sample_data):
        """clear_traces removes all traces from the plot."""
        wl, intens = sample_data
        spectrum_plot.add_trace(wl, intens, label="A")
        spectrum_plot.add_trace(wl, intens, label="B")
        assert len(spectrum_plot.get_traces()) == 2

        spectrum_plot.clear_traces()
        assert len(spectrum_plot.get_traces()) == 0

    def test_clear_traces_when_empty_is_noop(self, spectrum_plot):
        """clear_traces on empty plot does not raise."""
        spectrum_plot.clear_traces()  # Should not raise
        assert len(spectrum_plot.get_traces()) == 0


class TestDistinctColors:
    """Tests for color assignment."""

    def test_traces_get_distinct_colors(self, spectrum_plot, sample_data):
        """Each trace gets a distinct color from the cycle."""
        wl, intens = sample_data
        ids = []
        for i in range(5):
            ids.append(spectrum_plot.add_trace(wl, intens * (i + 1), label=f"T{i}"))

        traces = spectrum_plot.get_traces()
        colors = [t.color for t in traces]
        # First 5 should all be different
        assert len(set(colors)) == 5


class TestBackwardCompatibility:
    """Tests for backward-compatible set_data method."""

    def test_set_data_still_works_as_add_trace(self, spectrum_plot, sample_data):
        """set_data() should delegate to add_trace for backward compat."""
        wl, intens = sample_data
        spectrum_plot.set_data(wl, intens)
        traces = spectrum_plot.get_traces()
        assert len(traces) == 1

    def test_set_data_replaces_live_trace(self, spectrum_plot, sample_data):
        """Calling set_data twice replaces the 'live' trace, not adds."""
        wl, intens = sample_data
        spectrum_plot.set_data(wl, intens)
        spectrum_plot.set_data(wl, intens * 2)
        # Should still be 1 trace (live trace replaced)
        traces = spectrum_plot.get_traces()
        assert len(traces) == 1


class TestMaxTraces:
    """Tests for maximum trace limit."""

    def test_max_traces_limit(self, spectrum_plot, sample_data):
        """Adding more than MAX_TRACES removes the oldest."""
        from andor_qt.widgets.display.spectrum_plot import SpectrumPlotWidget

        wl, intens = sample_data
        max_traces = SpectrumPlotWidget.MAX_TRACES

        ids = []
        for i in range(max_traces + 5):
            ids.append(spectrum_plot.add_trace(wl, intens, label=f"T{i}"))

        traces = spectrum_plot.get_traces()
        assert len(traces) == max_traces
        # Oldest traces should have been removed
        trace_ids = {t.id for t in traces}
        for old_id in ids[:5]:
            assert old_id not in trace_ids


class TestSignals:
    """Tests for trace signals."""

    def test_trace_added_signal(self, spectrum_plot, sample_data):
        """trace_added signal fires with (id, label, color)."""
        received = []
        spectrum_plot.trace_added.connect(
            lambda tid, label, color: received.append((tid, label, color))
        )

        wl, intens = sample_data
        tid = spectrum_plot.add_trace(wl, intens, label="Sig")

        assert len(received) == 1
        assert received[0][0] == tid
        assert received[0][1] == "Sig"
        assert isinstance(received[0][2], str)

    def test_trace_removed_signal(self, spectrum_plot, sample_data):
        """trace_removed signal fires with (id,)."""
        removed = []
        spectrum_plot.trace_removed.connect(lambda tid: removed.append(tid))

        wl, intens = sample_data
        tid = spectrum_plot.add_trace(wl, intens, label="Rm")
        spectrum_plot.remove_trace(tid)

        assert len(removed) == 1
        assert removed[0] == tid

    def test_traces_cleared_signal(self, spectrum_plot, sample_data):
        """traces_cleared signal fires on clear_traces."""
        cleared = []
        spectrum_plot.traces_cleared.connect(lambda: cleared.append(True))

        wl, intens = sample_data
        spectrum_plot.add_trace(wl, intens)
        spectrum_plot.clear_traces()

        assert len(cleared) == 1


class TestCrosshairStillWorks:
    """Ensure crosshair and cursor readout still work with traces."""

    def test_cursor_label_exists(self, spectrum_plot):
        """Cursor label should still exist after adding traces."""
        assert spectrum_plot._cursor_label is not None

    def test_crosshair_lines_exist(self, spectrum_plot):
        """Crosshair lines should still exist."""
        assert spectrum_plot._vline is not None
        assert spectrum_plot._hline is not None
