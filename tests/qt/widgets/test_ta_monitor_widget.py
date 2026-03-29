"""Tests for TAMonitorWidget dark frame UI."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

os.environ["ANDOR_MOCK"] = "1"


@pytest.fixture
def mock_hw():
    mgr = MagicMock()
    mgr.motion_manager = MagicMock()
    mgr.motion_manager.get_axis.return_value = None
    mgr.motion_manager.all_axes = {}
    return mgr


@pytest.fixture
def widget(qt_app, mock_hw):
    from andor_qt.widgets.ta.monitor_widget import TAMonitorWidget
    w = TAMonitorWidget(hw_manager=mock_hw)
    yield w
    w.deleteLater()


class TestDarkFrameUI:
    def test_has_dark_requested_signal(self, widget):
        assert hasattr(widget, "dark_requested")

    def test_has_acquire_dark_button(self, widget):
        from PySide6.QtWidgets import QPushButton
        btns = widget.findChildren(QPushButton)
        btn_texts = [b.text() for b in btns]
        assert any("Dark" in t for t in btn_texts), \
            f"No 'Acquire Dark' button found. Buttons: {btn_texts}"

    def test_has_clear_dark_button(self, widget):
        from PySide6.QtWidgets import QPushButton
        btns = widget.findChildren(QPushButton)
        btn_texts = [b.text() for b in btns]
        assert any("Clear" in t and "Dark" in t for t in btn_texts), \
            f"No 'Clear Dark' button found. Buttons: {btn_texts}"

    def test_has_dark_status_label(self, widget):
        assert hasattr(widget, "_dark_status_label")

    def test_dark_requested_emits_config(self, widget):
        from andor_qt.ta.scan_config import TAScanConfig
        received = []
        widget.dark_requested.connect(lambda c: received.append(c))
        # Simulate clicking Acquire Dark
        widget._on_acquire_dark()
        assert len(received) == 1
        assert isinstance(received[0], TAScanConfig)

    def test_clear_dark_emits_signal(self, widget):
        received = []
        widget.dark_cleared.connect(lambda: received.append(True))
        widget._on_clear_dark()
        assert len(received) == 1

    def test_set_dark_status_updates_label(self, widget):
        widget.set_dark_status("Dark: 1000 frames, 12:00:00")
        assert "1000" in widget._dark_status_label.text()


class TestStaticPhaseSaveCache:
    """After single-phase complete, cached pump/ref must be separate arrays."""

    def test_cache_updated_after_single_phase_pump(self, qt_app, mock_hw):
        """After pump phase, _last_pump should hold pump data, not ref data."""
        import numpy as np
        from andor_qt.windows.ta_panel import TAWindowPanel

        panel = TAWindowPanel(hw_manager=mock_hw)

        # Simulate single-phase completion with distinct pump data
        pump_data = np.ones(100) * 5000.0
        panel._static_pump_avg = pump_data
        panel._on_single_phase_completed("pump", np.linspace(400, 800, 100), pump_data)

        cached_pump = getattr(panel._monitor_widget, "_last_pump", None)
        assert cached_pump is not None, "Pump data should be cached after phase complete"
        np.testing.assert_array_equal(cached_pump, pump_data)
        panel.deleteLater()

    def test_cache_separate_after_both_phases(self, qt_app, mock_hw):
        """After both phases, _last_pump and _last_ref must be different arrays."""
        import numpy as np
        from andor_qt.windows.ta_panel import TAWindowPanel

        panel = TAWindowPanel(hw_manager=mock_hw)

        pump_data = np.ones(100) * 5000.0
        ref_data = np.ones(100) * 4000.0

        panel._on_single_phase_completed("pump", np.linspace(400, 800, 100), pump_data)
        panel._on_single_phase_completed("ref", np.linspace(400, 800, 100), ref_data)

        cached_pump = panel._monitor_widget._last_pump
        cached_ref = panel._monitor_widget._last_ref
        assert not np.array_equal(cached_pump, cached_ref), \
            "Cached pump and ref must be different after both phases"
        np.testing.assert_array_equal(cached_pump, pump_data)
        np.testing.assert_array_equal(cached_ref, ref_data)
        panel.deleteLater()


class TestDarkFrameIntegration:
    def test_ta_panel_has_dark_frame_storage(self, qt_app, mock_hw):
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw)
        assert hasattr(panel, "_dark_frame")
        assert panel._dark_frame is None
        panel.deleteLater()
