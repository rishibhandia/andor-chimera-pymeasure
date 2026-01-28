"""Tests for ShutdownDialog.

These tests verify the shutdown dialog shows temperature progress
and handles the shutdown workflow.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestShutdownDialogStructure:
    """Tests for shutdown dialog UI structure."""

    def test_dialog_shows_status_label(self, qt_app):
        """Shutdown dialog has a status label."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()

        assert hasattr(dialog, "_status_label")
        assert dialog._status_label.text() != ""

    def test_dialog_shows_temperature(self, qt_app):
        """Shutdown dialog has a temperature label."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()

        assert hasattr(dialog, "_temp_label")

    def test_dialog_shows_progress_bar(self, qt_app):
        """Shutdown dialog has a progress bar."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()

        assert hasattr(dialog, "_progress_bar")

    def test_dialog_has_force_quit_button(self, qt_app):
        """Shutdown dialog has a Force Quit button."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()

        assert hasattr(dialog, "_force_quit_btn")


class TestShutdownDialogBehavior:
    """Tests for shutdown dialog behavior."""

    def test_progress_updates_with_temperature(self, qt_app):
        """Progress bar updates when temperature changes."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()
        dialog.set_temperature_range(-60.0, -20.0)

        dialog.update_temperature(-40.0, "NOT_REACHED")

        # Should be approximately 50% progress
        assert dialog._progress_bar.value() == 50

    def test_temperature_label_updates(self, qt_app):
        """Temperature label updates with new value."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()

        dialog.update_temperature(-45.5, "NOT_REACHED")

        assert "-45.5" in dialog._temp_label.text()

    def test_status_label_updates(self, qt_app):
        """Status label can be updated."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()

        dialog.set_status("Warming up camera...")

        assert "Warming up" in dialog._status_label.text()

    def test_force_quit_emits_signal(self, qt_app, handler_factory):
        """Force quit button emits force_quit_requested signal."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()
        handler = handler_factory("quit_handler")
        dialog.force_quit_requested.connect(handler)

        dialog._force_quit_btn.click()

        handler.assert_called_once()

    def test_shutdown_complete(self, qt_app):
        """on_shutdown_complete updates dialog."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()

        dialog.on_shutdown_complete()

        assert dialog._progress_bar.value() == 100
        assert "complete" in dialog._status_label.text().lower()
