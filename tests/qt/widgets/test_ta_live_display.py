"""Tests for TALiveDisplayWidget (real-time ΔI/I₀ display)."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QDoubleSpinBox

from andor_qt.widgets.ta.live_display import TALiveDisplayWidget


@pytest.fixture
def widget(qt_app):
    w = TALiveDisplayWidget()
    yield w
    w.deleteLater()
    qt_app.processEvents()  # force cleanup


class TestTALiveDisplayWidgetCreation:
    def test_creates_successfully(self, qt_app):
        w = TALiveDisplayWidget()
        assert w is not None
        w.deleteLater()

    def test_has_signal_plot(self, widget):
        assert widget.signal_plot is not None

    def test_has_kinetic_plot(self, widget):
        assert widget.kinetic_plot is not None

    def test_has_heatmap_plot(self, widget):
        assert widget.heatmap_plot is not None

    def test_has_wavelength_selector(self, widget):
        assert widget._probe_wl_spin is not None
        assert isinstance(widget._probe_wl_spin, QDoubleSpinBox)


class TestTALiveDisplaySlots:
    def test_on_signal_updated_no_crash(self, widget):
        wavelengths = np.linspace(400.0, 800.0, 64)
        delta_signal = np.random.rand(64) * 0.01 - 0.005
        widget.on_signal_updated(1.0, wavelengths, delta_signal)
        QApplication.instance().processEvents()

    def test_on_map_updated_no_crash(self, widget):
        delays = np.linspace(0.0, 10.0, 5)
        wavelengths = np.linspace(400.0, 800.0, 32)
        signal_matrix = np.random.rand(5, 32) * 0.01
        widget.on_map_updated(delays, wavelengths, signal_matrix)
        QApplication.instance().processEvents()

    def test_clear_resets_display(self, widget):
        wavelengths = np.linspace(400.0, 800.0, 32)
        delta_signal = np.ones(32) * 0.01
        widget.on_signal_updated(1.0, wavelengths, delta_signal)
        widget.clear()
        QApplication.instance().processEvents()
        assert len(widget._kinetic_delays) == 0
        assert len(widget._kinetic_signals) == 0

    def test_multiple_updates_no_crash(self, widget):
        wavelengths = np.linspace(400.0, 800.0, 32)
        for i in range(5):
            widget.on_signal_updated(float(i), wavelengths, np.ones(32) * i * 0.001)
        QApplication.instance().processEvents()


class TestDualAxisRawSpectra:
    """Raw spectra plot should have a secondary top axis showing pixel indices."""

    def test_raw_plot_has_top_axis(self, widget):
        """The raw spectra plot should have a visible top axis."""
        top_axis = widget._raw_plot.getPlotItem().getAxis("top")
        assert top_axis is not None
        assert top_axis.isVisible()

    def test_top_axis_label_is_pixel(self, widget):
        """Top axis should be labelled 'Pixel'."""
        top_axis = widget._raw_plot.getPlotItem().getAxis("top")
        assert "Pixel" in top_axis.labelText or "pixel" in top_axis.labelText.lower()

    def test_tick_strings_convert_wavelength_to_pixel(self, widget):
        """Given wavelengths, tick values should map back to pixel indices."""
        wavelengths = np.linspace(500.0, 700.0, 100)
        widget._wavelengths = wavelengths

        top_axis = widget._raw_plot.getPlotItem().getAxis("top")
        # Ask for tick labels at specific wavelength values
        test_values = [500.0, 600.0, 700.0]
        labels = top_axis.tickStrings(test_values, scale=1, spacing=1)
        # pixel 0 ↔ 500 nm, pixel 50 ↔ 600 nm, pixel 99 ↔ 700 nm
        assert len(labels) == 3
        assert "0" in labels[0]
        assert "50" in labels[1] or "49" in labels[1]
        assert "99" in labels[2]

    def test_tick_strings_passthrough_without_wavelengths(self, widget):
        """Without wavelengths set, tick strings should pass values through."""
        top_axis = widget._raw_plot.getPlotItem().getAxis("top")
        labels = top_axis.tickStrings([10.0, 20.0], scale=1, spacing=1)
        assert len(labels) == 2


class TestMonitorModeKinetic:
    """In monitor mode, kinetic trace should show signal vs cycle number."""

    def test_set_monitor_mode_exists(self, widget):
        assert hasattr(widget, "set_monitor_mode")

    def test_monitor_mode_changes_axis_label(self, widget):
        """Kinetic plot x-axis should say 'Cycle #' in monitor mode."""
        widget.set_monitor_mode(True)
        QApplication.instance().processEvents()
        bottom = widget._kinetic_plot.getPlotItem().getAxis("bottom")
        assert "Cycle" in bottom.labelText

    def test_monitor_mode_hides_ps_top_axis(self, widget):
        """ps top axis should be hidden in monitor mode (cycle # has no ps)."""
        widget.set_monitor_mode(True)
        QApplication.instance().processEvents()
        top = widget._kinetic_plot.getPlotItem().getAxis("top")
        assert not top.isVisible()

    def test_exit_monitor_mode_restores_axis(self, widget):
        """Exiting monitor mode should restore µm axis label and show ps axis."""
        widget.set_monitor_mode(True)
        widget.set_monitor_mode(False)
        QApplication.instance().processEvents()
        bottom = widget._kinetic_plot.getPlotItem().getAxis("bottom")
        assert "m" in bottom.labelText.lower()  # µm
        top = widget._kinetic_plot.getPlotItem().getAxis("top")
        assert top.isVisible()

    def test_monitor_kinetic_accumulates_by_cycle(self, widget):
        """In monitor mode, kinetic trace x-values should be cycle numbers."""
        widget.set_monitor_mode(True)
        wavelengths = np.linspace(500.0, 700.0, 32)
        for i in range(5):
            # delay_ps is ignored in monitor mode; cycle count is used instead
            widget.on_signal_updated(0.0, wavelengths, np.ones(32) * i * 0.001)
        QApplication.instance().processEvents()

        x, y = widget._kinetic_curve.getData()
        assert len(x) == 5
        # x should be [1, 2, 3, 4, 5] (cycle numbers)
        np.testing.assert_array_equal(x, [1, 2, 3, 4, 5])

    def test_monitor_mode_skips_fft(self, widget):
        """FFT is not meaningful for cycle data; curve should remain empty."""
        widget.set_monitor_mode(True)
        wavelengths = np.linspace(500.0, 700.0, 32)
        for i in range(10):
            widget.on_signal_updated(0.0, wavelengths, np.ones(32) * i * 0.001)
        QApplication.instance().processEvents()
        x, _ = widget._fft_curve.getData()
        assert x is None or len(x) == 0

    def test_clear_resets_monitor_cycle_count(self, widget):
        """Clearing in monitor mode should reset cycle counter."""
        widget.set_monitor_mode(True)
        wavelengths = np.linspace(500.0, 700.0, 32)
        widget.on_signal_updated(0.0, wavelengths, np.ones(32) * 0.001)
        widget.on_signal_updated(0.0, wavelengths, np.ones(32) * 0.002)
        widget.clear()
        widget.on_signal_updated(0.0, wavelengths, np.ones(32) * 0.003)
        QApplication.instance().processEvents()
        x, _ = widget._kinetic_curve.getData()
        assert len(x) == 1
        assert x[0] == 1  # reset to 1


class TestKineticFFTHorizontalLayout:
    """Kinetic trace and FFT plots should be arranged side-by-side horizontally."""

    def test_kinetic_and_fft_in_horizontal_splitter(self, widget):
        """Kinetic plot and FFT plot should be children of a horizontal QSplitter."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QSplitter

        kinetic_plot = widget._kinetic_plot
        fft_plot = widget._fft_plot

        # Walk up from kinetic_plot to find the QSplitter parent
        kinetic_splitter = kinetic_plot.parent()
        while kinetic_splitter is not None and not isinstance(kinetic_splitter, QSplitter):
            kinetic_splitter = kinetic_splitter.parent()

        fft_splitter = fft_plot.parent()
        while fft_splitter is not None and not isinstance(fft_splitter, QSplitter):
            fft_splitter = fft_splitter.parent()

        # Both should share the same horizontal splitter
        assert kinetic_splitter is not None, "Kinetic plot must be inside a QSplitter"
        assert fft_splitter is not None, "FFT plot must be inside a QSplitter"
        assert kinetic_splitter is fft_splitter, (
            "Kinetic and FFT plots must share the same QSplitter"
        )
        assert kinetic_splitter.orientation() == Qt.Orientation.Horizontal

    def test_probe_selector_above_both_plots(self, widget):
        """Probe wavelength selector row should be above (not beside) the plots."""
        from PySide6.QtWidgets import QSplitter

        # The probe spin box should NOT be inside the horizontal splitter
        spin_parent = widget._probe_wl_spin.parent()
        while spin_parent is not None:
            if isinstance(spin_parent, QSplitter):
                if spin_parent.orientation() == 1:  # Qt.Horizontal
                    pytest.fail(
                        "Probe wavelength selector should be above the "
                        "horizontal splitter, not inside it"
                    )
            spin_parent = spin_parent.parent()


class TestWavelengthSelector:
    def test_selector_range_set_from_first_signal(self, widget):
        wavelengths = np.linspace(500.0, 750.0, 64)
        widget.on_signal_updated(0.0, wavelengths, np.zeros(64))
        QApplication.instance().processEvents()
        assert widget._probe_wl_spin.minimum() == pytest.approx(500.0, abs=1.0)
        assert widget._probe_wl_spin.maximum() == pytest.approx(750.0, abs=1.0)

    def test_default_probe_wl_near_centre(self, widget):
        wavelengths = np.linspace(500.0, 700.0, 64)
        widget.on_signal_updated(0.0, wavelengths, np.zeros(64))
        QApplication.instance().processEvents()
        centre = (500.0 + 700.0) / 2
        assert abs(widget.probe_wavelength - centre) < 20.0

    def test_kinetic_updates_on_signal(self, widget):
        """Kinetic buffer accumulates one entry per signal_updated call."""
        wavelengths = np.linspace(500.0, 700.0, 32)
        for i in range(4):
            widget.on_signal_updated(float(i * 100), wavelengths, np.ones(32) * i * 0.01)
        QApplication.instance().processEvents()
        assert len(widget._kinetic_delays) == 4

    def test_changing_selector_rerenders_kinetic(self, widget):
        """Changing probe wavelength calls _update_kinetic_curve without crash."""
        wavelengths = np.linspace(500.0, 700.0, 32)
        for i in range(3):
            widget.on_signal_updated(float(i * 50), wavelengths, np.ones(32) * i * 0.005)
        widget.probe_wavelength = 550.0
        QApplication.instance().processEvents()
        x, y = widget._kinetic_curve.getData()
        assert x is not None and len(x) == 3

    def test_probe_wavelength_property(self, widget):
        widget.probe_wavelength = 632.8
        assert widget.probe_wavelength == pytest.approx(632.8, abs=0.1)
