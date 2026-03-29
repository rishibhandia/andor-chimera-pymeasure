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


class TestDarkFrameIntegration:
    def test_ta_panel_has_dark_frame_storage(self, qt_app, mock_hw):
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw)
        assert hasattr(panel, "_dark_frame")
        assert panel._dark_frame is None
        panel.deleteLater()
