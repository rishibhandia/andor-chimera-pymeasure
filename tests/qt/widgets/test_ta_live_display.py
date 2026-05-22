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


class TestSpectrumPlotHoverAndClick:
    """Mouse hover display and click-to-select on the ΔI/I₀ spectrum plot."""

    def test_hover_label_exists(self, widget):
        """A coordinate label should be overlaid on the signal plot."""
        assert hasattr(widget, "_hover_label")
        assert widget._hover_label is not None

    def test_hover_label_initially_hidden(self, widget):
        """Hover label should be hidden until the mouse enters the plot."""
        assert not widget._hover_label.isVisible()

    def test_crosshair_vline_exists(self, widget):
        """A vertical crosshair line should exist on the signal plot."""
        assert hasattr(widget, "_crosshair_v")
        assert widget._crosshair_v is not None

    def test_crosshair_hline_exists(self, widget):
        """A horizontal crosshair line should exist on the signal plot."""
        assert hasattr(widget, "_crosshair_h")
        assert widget._crosshair_h is not None

    def test_crosshairs_initially_hidden(self, widget):
        """Crosshair lines should be hidden until mouse enters."""
        assert not widget._crosshair_v.isVisible()
        assert not widget._crosshair_h.isVisible()

    def test_probe_indicator_line_exists(self, widget):
        """A vertical dashed line indicating the selected probe wavelength."""
        assert hasattr(widget, "_probe_indicator")
        assert widget._probe_indicator is not None

    def test_probe_indicator_at_initial_wavelength(self, widget):
        """The probe indicator should be at the current probe wavelength."""
        widget.probe_wavelength = 600.0
        QApplication.instance().processEvents()
        assert widget._probe_indicator.value() == pytest.approx(600.0, abs=0.1)

    def test_probe_indicator_updates_on_spin_change(self, widget):
        """Changing the spinbox should move the probe indicator line."""
        wavelengths = np.linspace(400.0, 800.0, 64)
        widget.on_signal_updated(0.0, wavelengths, np.zeros(64))
        widget.probe_wavelength = 550.0
        QApplication.instance().processEvents()
        assert widget._probe_indicator.value() == pytest.approx(550.0, abs=0.1)

    def test_click_on_signal_plot_updates_spinbox(self, widget):
        """Clicking on the ΔI/I₀ plot should update the probe wavelength."""
        wavelengths = np.linspace(400.0, 800.0, 64)
        widget.on_signal_updated(0.0, wavelengths, np.zeros(64))
        QApplication.instance().processEvents()

        # Simulate click by calling the handler directly with a known wavelength
        widget._on_signal_plot_clicked(650.0)
        QApplication.instance().processEvents()
        assert widget.probe_wavelength == pytest.approx(650.0, abs=0.2)

    def test_click_clamps_to_wavelength_range(self, widget):
        """Click outside the wavelength range should clamp to min/max."""
        wavelengths = np.linspace(400.0, 800.0, 64)
        widget.on_signal_updated(0.0, wavelengths, np.zeros(64))
        QApplication.instance().processEvents()

        # Click below the range - spinbox range is [400, 800]
        widget._on_signal_plot_clicked(300.0)
        QApplication.instance().processEvents()
        assert widget.probe_wavelength >= 400.0

    def test_click_updates_kinetic_trace(self, widget):
        """Clicking a new wavelength should update the kinetic curve data."""
        wavelengths = np.linspace(400.0, 800.0, 32)
        # Feed a few delay points with different spectra
        for i in range(3):
            sig = np.zeros(32)
            sig[16] = 0.01 * (i + 1)  # peak at pixel 16 = 600 nm
            widget.on_signal_updated(float(i), wavelengths, sig)
        QApplication.instance().processEvents()

        # Click on 600 nm (pixel 16)
        widget._on_signal_plot_clicked(600.0)
        QApplication.instance().processEvents()

        x, y = widget._kinetic_curve.getData()
        assert x is not None and len(x) == 3

    def test_hover_update_method_exists(self, widget):
        """The widget should have the mouse-move handler method."""
        assert hasattr(widget, "_on_signal_mouse_moved")
        assert callable(widget._on_signal_mouse_moved)

    def test_clear_hides_crosshairs(self, widget):
        """Clearing the display should hide crosshair lines."""
        # Make crosshairs visible first
        widget._crosshair_v.setVisible(True)
        widget._crosshair_h.setVisible(True)
        widget._hover_label.setVisible(True)
        widget.clear()
        QApplication.instance().processEvents()
        assert not widget._crosshair_v.isVisible()
        assert not widget._crosshair_h.isVisible()
        assert not widget._hover_label.isVisible()

    def test_probe_indicator_visible_after_data(self, widget):
        """Probe indicator should be visible once data has been loaded."""
        wavelengths = np.linspace(400.0, 800.0, 64)
        widget.on_signal_updated(0.0, wavelengths, np.zeros(64))
        QApplication.instance().processEvents()
        assert widget._probe_indicator.isVisible()


class TestDeltaReadoutLabel:
    """Live numerical readout of DI/I0 at the selected probe wavelength."""

    def test_has_delta_readout_label(self, widget):
        """Widget should have a _delta_readout_label QLabel attribute."""
        from PySide6.QtWidgets import QLabel

        assert hasattr(widget, "_delta_readout_label")
        assert isinstance(widget._delta_readout_label, QLabel)

    def test_readout_initially_empty(self, widget):
        """Before any data, the readout label should show placeholder text."""
        text = widget._delta_readout_label.text()
        # Should be empty or a placeholder — NOT a numeric value
        assert text == "" or "---" in text or "N/A" in text

    def test_readout_shows_value_after_signal_updated(self, widget):
        """After on_signal_updated, label should display DI/I0 at probe wavelength."""
        wavelengths = np.linspace(500.0, 700.0, 101)
        # Create signal with a known value at 600 nm (index 50)
        delta_signal = np.zeros(101)
        delta_signal[50] = 1.23e-3
        widget.on_signal_updated(0.0, wavelengths, delta_signal)
        QApplication.instance().processEvents()

        text = widget._delta_readout_label.text()
        # Probe should auto-center at 600 nm; value should be 1.23e-3
        assert "1.23" in text
        assert "e-0" in text.lower() or "e-" in text.lower()

    def test_readout_scientific_notation_format(self, widget):
        """Readout should use scientific notation with DI/I0 prefix."""
        wavelengths = np.linspace(500.0, 700.0, 101)
        delta_signal = np.ones(101) * 5.67e-4
        widget.on_signal_updated(0.0, wavelengths, delta_signal)
        QApplication.instance().processEvents()

        text = widget._delta_readout_label.text()
        assert "\u0394I/I\u2080" in text or "DI/I" in text

    def test_readout_updates_with_new_data(self, widget):
        """Successive signal updates should change the readout value."""
        wavelengths = np.linspace(500.0, 700.0, 101)

        # First update
        delta_signal_1 = np.ones(101) * 1.0e-3
        widget.on_signal_updated(0.0, wavelengths, delta_signal_1)
        QApplication.instance().processEvents()
        text_1 = widget._delta_readout_label.text()

        # Second update with different value
        delta_signal_2 = np.ones(101) * 9.87e-4
        widget.on_signal_updated(1.0, wavelengths, delta_signal_2)
        QApplication.instance().processEvents()
        text_2 = widget._delta_readout_label.text()

        assert text_1 != text_2

    def test_readout_tracks_probe_wavelength(self, widget):
        """Changing probe wavelength should update readout from stored data."""
        wavelengths = np.linspace(500.0, 700.0, 101)
        # Create a signal where different wavelengths have different values
        delta_signal = np.zeros(101)
        delta_signal[25] = 2.00e-3  # at 550 nm
        delta_signal[75] = 4.00e-3  # at 650 nm
        widget.on_signal_updated(0.0, wavelengths, delta_signal)
        QApplication.instance().processEvents()

        # Select 550 nm
        widget.probe_wavelength = 550.0
        QApplication.instance().processEvents()
        text_550 = widget._delta_readout_label.text()

        # Select 650 nm
        widget.probe_wavelength = 650.0
        QApplication.instance().processEvents()
        text_650 = widget._delta_readout_label.text()

        # Values should be different since the signal differs at 550 vs 650
        assert text_550 != text_650

    def test_clear_resets_readout_label(self, widget):
        """Calling clear() should reset the readout label to empty/placeholder."""
        wavelengths = np.linspace(500.0, 700.0, 101)
        delta_signal = np.ones(101) * 3.45e-3
        widget.on_signal_updated(0.0, wavelengths, delta_signal)
        QApplication.instance().processEvents()

        # Verify it has a value
        assert widget._delta_readout_label.text() != ""

        widget.clear()
        QApplication.instance().processEvents()

        text = widget._delta_readout_label.text()
        assert text == "" or "---" in text or "N/A" in text

    def test_readout_correct_value_at_specific_wavelength(self, widget):
        """Readout should display the value at the nearest wavelength to the selector."""
        wavelengths = np.linspace(500.0, 700.0, 201)
        delta_signal = np.zeros(201)
        # Set a known value at index 100 = 600 nm
        delta_signal[100] = -7.89e-3
        widget.on_signal_updated(0.0, wavelengths, delta_signal)
        QApplication.instance().processEvents()

        # Probe auto-centers near 600 nm
        widget.probe_wavelength = 600.0
        QApplication.instance().processEvents()

        text = widget._delta_readout_label.text()
        assert "7.89" in text
        assert "-" in text  # negative sign


def _feed_known_oscillation(widget, freq_thz=2.0, n_points=64, dt_ps=0.05):
    """Push a known sinusoidal kinetic trace into the widget so the FFT computes.

    Returns the (frequency, amplitude) of the expected FFT peak after the
    Hanning window is applied. Uses 5 wavelength bins; only bin index 2
    carries the oscillation.
    """
    wl = np.linspace(400.0, 800.0, 5)
    for i in range(n_points):
        delay = i * dt_ps
        sig = np.zeros(5)
        sig[2] = np.sin(2 * np.pi * freq_thz * delay)
        widget.on_signal_updated(delay, wl, sig)
    # Pin the probe to the bin carrying the signal so the FFT actually sees it
    widget._probe_wl_spin.setValue(float(wl[2]))
    QApplication.instance().processEvents()


class TestFFTInteractiveInspection:
    """Hover/click on the FFT plot reveals frequency + amplitude readout."""

    def test_fft_data_cached_after_kinetic_update(self, widget):
        """FFT computation populates the cached freqs/values arrays."""
        _feed_known_oscillation(widget)
        # FFT bins should be cached (rfft of 64-point signal → 33 bins minus DC = 32)
        assert len(widget._fft_freqs) > 0
        assert len(widget._fft_vals) == len(widget._fft_freqs)
        # Frequencies must be monotonically increasing and start at the first non-DC bin
        assert np.all(np.diff(widget._fft_freqs) > 0)
        assert widget._fft_freqs[0] > 0  # DC bin was dropped

    def test_snap_returns_nearest_bin(self, widget):
        """_snap_to_fft_bin returns the FFT data point closest to a given frequency."""
        _feed_known_oscillation(widget, freq_thz=2.0, n_points=64, dt_ps=0.05)
        # Nyquist = 10 THz, bin spacing = 10/32 = 0.3125 THz; nearest bin to 2.0 should be ~2.0
        f_snap, amp_snap = widget._snap_to_fft_bin(2.0)
        assert f_snap is not None
        assert abs(f_snap - 2.0) < 0.4  # within one bin
        # The cached amplitude should be the peak (since the kinetic is sin(2π·2·t))
        peak_idx = int(np.argmax(widget._fft_vals))
        assert abs(widget._fft_freqs[peak_idx] - 2.0) < 0.4
        # The snapped amplitude should equal the cached amplitude at the snap freq
        snap_idx = int(np.argmin(np.abs(widget._fft_freqs - 2.0)))
        assert amp_snap == pytest.approx(widget._fft_vals[snap_idx])

    def test_snap_with_no_data_returns_none(self, widget):
        """Snapping before any FFT exists returns (None, None) safely."""
        f, a = widget._snap_to_fft_bin(1.0)
        assert f is None
        assert a is None

    def test_click_updates_selection_label(self, widget):
        """Clicking the FFT plot writes the snapped freq, period, and amplitude."""
        from unittest.mock import MagicMock
        from PySide6.QtCore import Qt as _Qt, QPointF as _QPointF

        _feed_known_oscillation(widget, freq_thz=2.0)
        # Pick a frequency near the peak and feed scene coordinates that map to it
        target_freq = widget._fft_freqs[int(np.argmax(widget._fft_vals))]
        vb = widget._fft_plot.getPlotItem().getViewBox()
        target_amp = widget._fft_vals[int(np.argmax(widget._fft_vals))]
        scene_point = vb.mapViewToScene(_QPointF(float(target_freq), float(target_amp)))

        # Force the view box to claim it contains the scene_point
        # (in tests the widget hasn't actually been shown, so coordinates may not map cleanly)
        event = MagicMock()
        event.button.return_value = _Qt.MouseButton.LeftButton
        event.scenePos.return_value = scene_point
        # Patch the contains() check so the click handler proceeds
        original_contains = vb.sceneBoundingRect().contains
        widget._fft_plot.getPlotItem().getViewBox().sceneBoundingRect = lambda: MagicMock(
            contains=lambda p: True
        )

        widget._on_fft_mouse_clicked(event)

        text = widget._fft_selection_label.text()
        # Selection label should show frequency, period, and amplitude
        assert "THz" in text
        assert "ps" in text
        assert "amp" in text
        # Persistent indicator visible at the snapped frequency
        assert widget._fft_selected_indicator.isVisible()
        assert widget._fft_selected_indicator.pos().x() == pytest.approx(
            target_freq, rel=1e-6
        )

    def test_click_with_no_fft_data_does_nothing(self, widget):
        """Clicking when no FFT exists should leave the UI untouched."""
        from unittest.mock import MagicMock
        from PySide6.QtCore import Qt as _Qt

        event = MagicMock()
        event.button.return_value = _Qt.MouseButton.LeftButton
        # Force "contains" to return True so we'd reach the snap stage if we had data
        widget._fft_plot.getPlotItem().getViewBox().sceneBoundingRect = lambda: MagicMock(
            contains=lambda p: True
        )
        event.scenePos.return_value = MagicMock()

        widget._on_fft_mouse_clicked(event)
        # No FFT data → indicator stays hidden and label keeps the default
        assert not widget._fft_selected_indicator.isVisible()
        assert "Click" in widget._fft_selection_label.text()

    def test_clear_resets_fft_state(self, widget):
        """clear() empties FFT caches and resets the selection label."""
        _feed_known_oscillation(widget)
        assert len(widget._fft_freqs) > 0
        widget.clear()
        assert len(widget._fft_freqs) == 0
        assert len(widget._fft_vals) == 0
        assert not widget._fft_selected_indicator.isVisible()
        assert widget._fft_selection_label.text() == "Click a peak to inspect"
