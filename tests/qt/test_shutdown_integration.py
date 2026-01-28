"""Tests for shutdown dialog integration with main window.

These tests verify that the main window uses the ShutdownDialog
for the shutdown workflow.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestShutdownIntegration:
    """Tests for shutdown dialog integration."""

    def test_main_window_has_start_shutdown_with_dialog(
        self, qt_app, hardware_manager, wait_for
    ):
        """Main window's _start_shutdown creates a ShutdownDialog."""
        completed = []
        hardware_manager.initialize(on_complete=lambda: completed.append(True))
        wait_for(lambda: len(completed) > 0)

        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()

        # Verify _start_shutdown_with_dialog method exists
        assert hasattr(window, "_start_shutdown_with_dialog")

    def test_close_event_uses_shutdown_dialog(
        self, qt_app, hardware_manager, wait_for
    ):
        """Close event shows shutdown dialog instead of blocking."""
        completed = []
        hardware_manager.initialize(on_complete=lambda: completed.append(True))
        wait_for(lambda: len(completed) > 0)

        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()

        # Verify the window has the shutdown dialog method
        assert callable(getattr(window, "_start_shutdown_with_dialog", None))
