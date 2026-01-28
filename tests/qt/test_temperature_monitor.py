"""Tests for TemperatureMonitorWidget.

These tests verify the enhanced temperature monitoring display.
"""

from __future__ import annotations

import pytest


class TestTemperatureMonitorStructure:
    """Tests for temperature monitor UI structure."""

    def test_widget_shows_current_temperature(self, qt_app):
        """Widget has a current temperature display."""
        from andor_qt.widgets.hardware.temperature_monitor import (
            TemperatureMonitorWidget,
        )

        widget = TemperatureMonitorWidget()

        assert hasattr(widget, "_current_temp_label")

    def test_widget_shows_target_temperature(self, qt_app):
        """Widget has a target temperature display."""
        from andor_qt.widgets.hardware.temperature_monitor import (
            TemperatureMonitorWidget,
        )

        widget = TemperatureMonitorWidget()

        assert hasattr(widget, "_target_temp_label")

    def test_widget_shows_status_indicator(self, qt_app):
        """Widget has a status indicator."""
        from andor_qt.widgets.hardware.temperature_monitor import (
            TemperatureMonitorWidget,
        )

        widget = TemperatureMonitorWidget()

        assert hasattr(widget, "_status_label")


class TestTemperatureMonitorBehavior:
    """Tests for temperature monitor behavior."""

    def test_set_temperature_updates_label(self, qt_app):
        """set_temperature updates the current temperature display."""
        from andor_qt.widgets.hardware.temperature_monitor import (
            TemperatureMonitorWidget,
        )

        widget = TemperatureMonitorWidget()

        widget.set_temperature(-45.5, "NOT_REACHED")

        assert "-45.5" in widget._current_temp_label.text()

    def test_set_target_updates_label(self, qt_app):
        """set_target updates the target temperature display."""
        from andor_qt.widgets.hardware.temperature_monitor import (
            TemperatureMonitorWidget,
        )

        widget = TemperatureMonitorWidget()

        widget.set_target(-60)

        assert "-60" in widget._target_temp_label.text()

    def test_status_color_stabilized(self, qt_app):
        """Status indicator shows green when stabilized."""
        from andor_qt.widgets.hardware.temperature_monitor import (
            TemperatureMonitorWidget,
        )

        widget = TemperatureMonitorWidget()

        widget.set_temperature(-60.0, "STABILIZED")

        # Status label should contain "STABILIZED"
        assert "STABILIZED" in widget._status_label.text()
        # Color should be set via stylesheet (green indicator)
        style = widget._status_label.styleSheet()
        assert "green" in style.lower() or "#" in style

    def test_status_color_not_reached(self, qt_app):
        """Status indicator shows amber/yellow when not reached."""
        from andor_qt.widgets.hardware.temperature_monitor import (
            TemperatureMonitorWidget,
        )

        widget = TemperatureMonitorWidget()

        widget.set_temperature(-40.0, "NOT_REACHED")

        assert "NOT_REACHED" in widget._status_label.text()
        style = widget._status_label.styleSheet()
        assert "orange" in style.lower() or "yellow" in style.lower() or "#" in style
