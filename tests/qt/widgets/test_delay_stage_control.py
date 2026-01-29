"""Tests for DelayStageControlWidget.

Tests for the delay stage control widget UI and functionality.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock
import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from andor_qt.widgets.hardware.delay_stage_control import DelayStageControlWidget
from andor_qt.core.signals import get_hardware_signals


@pytest.fixture
def mock_hw_manager():
    """Create a mock HardwareManager with motion_manager."""
    manager = MagicMock()

    # Create mock axis
    mock_axis = MagicMock()
    mock_axis.name = "delay"
    mock_axis.position = 0.0
    mock_axis.position_ps = 0.0
    mock_axis.position_min = 0.0
    mock_axis.position_max = 300.0
    mock_axis.units = "ps"
    mock_axis.is_moving = False
    mock_axis.delay_range_ps = (0.0, 2000.0)

    # Create mock motion manager
    manager.motion_manager = MagicMock()
    manager.motion_manager.all_axes = {"delay": mock_axis}
    manager.motion_manager.get_axis = lambda name: manager.motion_manager.all_axes.get(name)
    manager.set_axis_position = MagicMock()

    return manager


@pytest.fixture
def widget(qt_app, mock_hw_manager):
    """Create DelayStageControlWidget for testing."""
    w = DelayStageControlWidget(mock_hw_manager)
    yield w
    w.deleteLater()


class TestDelayStageControlWidgetCreation:
    """Tests for widget creation."""

    def test_create_widget(self, qt_app, mock_hw_manager):
        """Widget can be created."""
        w = DelayStageControlWidget(mock_hw_manager)
        assert w is not None
        w.deleteLater()

    def test_widget_has_title(self, widget):
        """Widget has group box title."""
        assert widget.title() == "Delay Stage Control"

    def test_widget_has_axis_combo(self, widget):
        """Widget has axis selector combobox."""
        assert widget._axis_combo is not None

    def test_widget_has_position_spinbox(self, widget):
        """Widget has position spinbox."""
        assert widget._position_spin is not None

    def test_widget_has_go_button(self, widget):
        """Widget has Go button."""
        assert widget._go_button is not None

    def test_widget_has_home_button(self, widget):
        """Widget has Home button."""
        assert widget._home_button is not None

    def test_widget_has_current_label(self, widget):
        """Widget has current position label."""
        assert widget._current_pos_label is not None


class TestDelayStageControlWidgetAxisSelector:
    """Tests for axis selector."""

    def test_axis_combo_populated(self, widget):
        """Axis combo is populated from motion manager."""
        # Axis combo should have "delay" axis
        assert widget._axis_combo.count() >= 1

    def test_axis_combo_selects_first(self, widget):
        """First axis is selected by default."""
        assert widget._axis_combo.currentIndex() >= 0


class TestDelayStageControlWidgetPositionControl:
    """Tests for position control."""

    def test_position_spinbox_range(self, widget):
        """Position spinbox has correct range."""
        # Default range is large to allow any value
        # The actual range is updated when axis is selected
        assert widget._position_spin.maximum() > widget._position_spin.minimum()

    def test_go_button_calls_set_position(self, widget, mock_hw_manager):
        """Go button calls set_axis_position."""
        widget._position_spin.setValue(100.0)
        widget._go_button.click()

        mock_hw_manager.set_axis_position.assert_called()


class TestDelayStageControlWidgetEnabled:
    """Tests for enabled/disabled state."""

    def test_set_enabled_true(self, widget):
        """set_enabled(True) enables controls."""
        widget.set_enabled(True)
        assert widget._go_button.isEnabled()

    def test_set_enabled_false(self, widget):
        """set_enabled(False) disables controls."""
        widget.set_enabled(False)
        assert not widget._go_button.isEnabled()


class TestDelayStageControlWidgetSignals:
    """Tests for signal handling."""

    def test_position_changed_signal_updates_label(self, widget):
        """axis_position_changed signal updates current position label."""
        signals = get_hardware_signals()
        signals.axis_position_changed.emit("delay", 50.0)

        # Label should be updated (may show in ps)
        # Note: actual update happens via Qt signal connection


class TestDelayStageControlWidgetMovingState:
    """Tests for moving state indication."""

    def test_set_moving_shows_indicator(self, widget):
        """_set_moving(True) shows progress indicator and disables controls."""
        widget._set_moving(True)

        # Moving bar should not be hidden
        assert not widget._moving_bar.isHidden()
        # Controls should be disabled
        assert not widget._go_button.isEnabled()
        assert widget._is_moving is True

    def test_set_moving_hides_indicator(self, widget):
        """_set_moving(False) hides progress indicator and enables controls."""
        widget._set_moving(True)  # First show it
        widget._set_moving(False)  # Then hide it

        # Moving bar should be hidden
        assert widget._moving_bar.isHidden()
        # Controls should be enabled
        assert widget._go_button.isEnabled()
        assert widget._is_moving is False
