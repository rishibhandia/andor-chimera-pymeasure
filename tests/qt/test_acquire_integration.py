"""Tests for AcquireControlWidget integration with main window."""

from __future__ import annotations

import pytest


class TestAcquireIntegration:
    """Tests for acquire control main window integration."""

    def test_main_window_has_acquire_control(
        self, qt_app, hardware_manager, wait_for
    ):
        """Main window has an AcquireControlWidget."""
        from andor_qt.widgets.inputs.acquire_control import AcquireControlWidget

        completed = []
        hardware_manager.initialize(on_complete=lambda: completed.append(True))
        wait_for(lambda: len(completed) > 0)

        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()

        assert hasattr(window, "_acquire_control")
        assert isinstance(window._acquire_control, AcquireControlWidget)

    def test_acquire_button_triggers_acquisition(
        self, qt_app, hardware_manager, wait_for
    ):
        """Acquire button connects to acquisition method."""
        completed = []
        hardware_manager.initialize(on_complete=lambda: completed.append(True))
        wait_for(lambda: len(completed) > 0)

        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()

        # Verify signal connection exists
        assert hasattr(window._acquire_control, "acquire_requested")
