"""Tests for TA module integration into main window.

Verifies that TAWindowPanel is created and wired correctly,
and that the main window has a TA tab.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ["ANDOR_MOCK"] = "1"


@pytest.fixture
def mock_hw_manager():
    """Create a minimal mock HardwareManager."""
    mgr = MagicMock()
    mgr.camera = MagicMock()
    mgr.spectrograph = MagicMock()
    mgr.motion_manager = MagicMock()
    mgr.motion_manager.get_axis.return_value = None
    mgr.motion_manager.all_axes = {}
    mgr.get_wavelengths.return_value = [500.0, 600.0, 700.0]
    return mgr


class TestTAWindowPanel:
    def test_creates_successfully(self, qt_app, mock_hw_manager):
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        assert panel is not None
        panel.deleteLater()

    def test_has_config_widget(self, qt_app, mock_hw_manager):
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        assert panel.config_widget is not None
        panel.deleteLater()

    def test_has_live_display(self, qt_app, mock_hw_manager):
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        assert panel.live_display is not None
        panel.deleteLater()

    def test_has_engine(self, qt_app, mock_hw_manager):
        from andor_qt.windows.ta_panel import TAWindowPanel
        from andor_qt.ta.engine import TransientAbsorptionEngine
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        assert isinstance(panel.engine, TransientAbsorptionEngine)
        panel.deleteLater()

    def test_scan_requested_connects_to_engine(self, qt_app, mock_hw_manager):
        """scan_requested signal from config widget should trigger engine start."""
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        # Should not raise when scan is requested with mock hw
        from andor_qt.ta.scan_config import TAScanConfig
        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="boxcar", scan_direction="forward",
            sample_name="test",
        )
        # Just verify emitting doesn't crash
        panel.config_widget.scan_requested.emit(config)
        panel.engine.abort()
        panel.deleteLater()


class TestMainWindowTATab:
    def test_main_window_has_ta_tab(self, qt_app, mock_sdk):
        """Main window should have a TA tab."""
        from unittest.mock import patch
        from PySide6.QtWidgets import QTabWidget
        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()
        # Find top-level tab widget
        tabs = window.findChildren(QTabWidget)
        assert len(tabs) > 0

        # One of them should have a tab called "TA" or "Transient Absorption"
        ta_tab_found = False
        for tab_widget in tabs:
            for i in range(tab_widget.count()):
                label = tab_widget.tabText(i)
                if "TA" in label or "Transient" in label:
                    ta_tab_found = True
                    break

        # Skip close() to avoid triggering the blocking shutdown sequence in tests
        window.deleteLater()

        assert ta_tab_found, "No TA tab found in main window"
