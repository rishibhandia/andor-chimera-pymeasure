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
