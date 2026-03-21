"""Tests for TALiveDisplayWidget (real-time ΔOD display)."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

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

    def test_has_delta_od_plot(self, widget):
        assert widget.delta_od_plot is not None

    def test_has_kinetic_plot(self, widget):
        assert widget.kinetic_plot is not None

    def test_has_heatmap_plot(self, widget):
        assert widget.heatmap_plot is not None


class TestTALiveDisplaySlots:
    def test_on_delta_od_updated_no_crash(self, widget):
        wavelengths = np.linspace(400.0, 800.0, 64)
        delta_od = np.random.rand(64) * 0.01
        widget.on_delta_od_updated(1.0, wavelengths, delta_od)
        QApplication.instance().processEvents()

    def test_on_kinetic_updated_no_crash(self, widget):
        delays = np.array([0.0, 1.0, 5.0, 10.0])
        kinetic = np.random.rand(4) * 0.01
        widget.on_kinetic_updated(delays, kinetic)
        QApplication.instance().processEvents()

    def test_on_map_updated_no_crash(self, widget):
        delays = np.linspace(0.0, 10.0, 5)
        wavelengths = np.linspace(400.0, 800.0, 32)
        od_matrix = np.random.rand(5, 32) * 0.01
        widget.on_map_updated(delays, wavelengths, od_matrix)
        QApplication.instance().processEvents()

    def test_clear_resets_display(self, widget):
        wavelengths = np.linspace(400.0, 800.0, 32)
        delta_od = np.ones(32) * 0.01
        widget.on_delta_od_updated(1.0, wavelengths, delta_od)
        widget.clear()
        QApplication.instance().processEvents()

    def test_multiple_updates_no_crash(self, widget):
        wavelengths = np.linspace(400.0, 800.0, 32)
        for i in range(5):
            widget.on_delta_od_updated(float(i), wavelengths, np.ones(32) * i * 0.001)
        QApplication.instance().processEvents()
