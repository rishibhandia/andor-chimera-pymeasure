"""Tests for AndorMenuBar.

These tests verify the menu bar has correct structure and actions.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestMenuBarStructure:
    """Tests for menu bar structure."""

    def test_menu_bar_has_file_menu(self, qt_app):
        """Menu bar has a File menu."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        menus = [action.text() for action in menu_bar.actions()]

        assert any("File" in text for text in menus)

    def test_menu_bar_has_acquisition_menu(self, qt_app):
        """Menu bar has an Acquisition menu."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        menus = [action.text() for action in menu_bar.actions()]

        assert any("Acquisition" in text for text in menus)

    def test_menu_bar_has_help_menu(self, qt_app):
        """Menu bar has a Help menu."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        menus = [action.text() for action in menu_bar.actions()]

        assert any("Help" in text for text in menus)


class TestMenuBarShortcuts:
    """Tests for menu bar keyboard shortcuts."""

    def test_save_action_shortcut_is_ctrl_s(self, qt_app):
        """Save action has Ctrl+S shortcut."""
        from PySide6.QtGui import QKeySequence

        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()

        assert menu_bar.save_action.shortcut() == QKeySequence("Ctrl+S")

    def test_acquire_action_shortcut_is_enter(self, qt_app):
        """Acquire action has Enter/Return shortcut."""
        from PySide6.QtGui import QKeySequence

        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()

        assert menu_bar.acquire_action.shortcut() == QKeySequence("Return")

    def test_abort_action_shortcut_is_escape(self, qt_app):
        """Abort action has Escape shortcut."""
        from PySide6.QtGui import QKeySequence

        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()

        assert menu_bar.abort_action.shortcut() == QKeySequence("Escape")


class TestMenuBarSignals:
    """Tests for menu bar signal emission."""

    def test_save_action_emits_signal(self, qt_app, handler_factory):
        """Save action triggers save_requested signal."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        handler = handler_factory("save_handler")
        menu_bar.save_requested.connect(handler)

        menu_bar.save_action.trigger()

        handler.assert_called_once()

    def test_acquire_action_emits_signal(self, qt_app, handler_factory):
        """Acquire action triggers acquire_requested signal."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        handler = handler_factory("acquire_handler")
        menu_bar.acquire_requested.connect(handler)

        menu_bar.acquire_action.trigger()

        handler.assert_called_once()

    def test_abort_action_emits_signal(self, qt_app, handler_factory):
        """Abort action triggers abort_requested signal."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        handler = handler_factory("abort_handler")
        menu_bar.abort_requested.connect(handler)

        menu_bar.abort_action.trigger()

        handler.assert_called_once()

    def test_exit_action_emits_signal(self, qt_app, handler_factory):
        """Exit action triggers exit_requested signal."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        handler = handler_factory("exit_handler")
        menu_bar.exit_requested.connect(handler)

        menu_bar.exit_action.trigger()

        handler.assert_called_once()

    def test_load_calibration_action_emits_signal(self, qt_app, handler_factory):
        """Load calibration action triggers load_calibration_requested signal."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        handler = handler_factory("cal_handler")
        menu_bar.load_calibration_requested.connect(handler)

        menu_bar.load_calibration_action.trigger()

        handler.assert_called_once()

    def test_benchmark_action_emits_signal(self, qt_app, handler_factory):
        """Benchmark action triggers benchmark_requested signal."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        handler = handler_factory("bench_handler")
        menu_bar.benchmark_requested.connect(handler)

        menu_bar.benchmark_action.trigger()

        handler.assert_called_once()

    def test_about_action_emits_signal(self, qt_app, handler_factory):
        """About action triggers about_requested signal."""
        from andor_qt.widgets.menu_bar import AndorMenuBar

        menu_bar = AndorMenuBar()
        handler = handler_factory("about_handler")
        menu_bar.about_requested.connect(handler)

        menu_bar.about_action.trigger()

        handler.assert_called_once()
