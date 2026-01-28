"""Tests for AcquireControlWidget.

These tests verify the acquire/abort control widget.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestAcquireControlStructure:
    """Tests for acquire control widget structure."""

    def test_widget_has_acquire_button(self, qt_app):
        """Widget has an Acquire button."""
        from andor_qt.widgets.inputs.acquire_control import AcquireControlWidget

        widget = AcquireControlWidget()

        assert hasattr(widget, "_acquire_btn")
        assert widget._acquire_btn.text() == "Acquire"

    def test_widget_has_abort_button(self, qt_app):
        """Widget has an Abort button."""
        from andor_qt.widgets.inputs.acquire_control import AcquireControlWidget

        widget = AcquireControlWidget()

        assert hasattr(widget, "_abort_btn")
        assert widget._abort_btn.text() == "Abort"


class TestAcquireControlSignals:
    """Tests for acquire control signal emission."""

    def test_acquire_button_emits_signal(self, qt_app, handler_factory):
        """Acquire button emits acquire_requested signal."""
        from andor_qt.widgets.inputs.acquire_control import AcquireControlWidget

        widget = AcquireControlWidget()
        handler = handler_factory("acquire_handler")
        widget.acquire_requested.connect(handler)

        widget._acquire_btn.click()

        handler.assert_called_once()

    def test_abort_button_emits_signal(self, qt_app, handler_factory):
        """Abort button emits abort_requested signal."""
        from andor_qt.widgets.inputs.acquire_control import AcquireControlWidget

        widget = AcquireControlWidget()
        widget.set_acquiring(True)  # Enable abort button
        handler = handler_factory("abort_handler")
        widget.abort_requested.connect(handler)

        widget._abort_btn.click()

        handler.assert_called_once()


class TestAcquireControlState:
    """Tests for acquire control state management."""

    def test_buttons_disabled_during_acquisition(self, qt_app):
        """Acquire button is disabled during acquisition."""
        from andor_qt.widgets.inputs.acquire_control import AcquireControlWidget

        widget = AcquireControlWidget()

        widget.set_acquiring(True)

        assert not widget._acquire_btn.isEnabled()
        assert widget._abort_btn.isEnabled()

    def test_buttons_enabled_after_acquisition(self, qt_app):
        """Acquire button is re-enabled after acquisition."""
        from andor_qt.widgets.inputs.acquire_control import AcquireControlWidget

        widget = AcquireControlWidget()

        widget.set_acquiring(True)
        widget.set_acquiring(False)

        assert widget._acquire_btn.isEnabled()
        assert not widget._abort_btn.isEnabled()

    def test_initial_state(self, qt_app):
        """Initial state: Acquire enabled, Abort disabled."""
        from andor_qt.widgets.inputs.acquire_control import AcquireControlWidget

        widget = AcquireControlWidget()

        assert widget._acquire_btn.isEnabled()
        assert not widget._abort_btn.isEnabled()
