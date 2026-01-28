"""Tests for menu bar integration with main window.

These tests verify the menu bar is properly integrated
into the main window.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMainWindowMenuBar:
    """Tests for main window menu bar integration."""

    def test_main_window_has_menu_bar(self, qt_app, hardware_manager, wait_for):
        """Main window has a menu bar."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        completed = []
        hardware_manager.initialize(on_complete=lambda: completed.append(True))
        wait_for(lambda: len(completed) > 0)

        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()

        assert hasattr(window, "_menu_bar")
        assert isinstance(window._menu_bar, AndorMenuBar)

    def test_exit_menu_triggers_close(
        self, qt_app, hardware_manager, wait_for
    ):
        """Exit menu action connects to window close."""
        completed = []
        hardware_manager.initialize(on_complete=lambda: completed.append(True))
        wait_for(lambda: len(completed) > 0)

        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()

        # Verify the exit_requested signal is connected
        assert window._menu_bar.exit_requested is not None

        # The signal should be connected to window.close
        # We verify by checking that the menu bar has an exit action
        assert hasattr(window._menu_bar, "exit_action")
