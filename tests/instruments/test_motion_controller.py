"""Tests for multi-axis motion controller.

Tests for Axis, MockAxis, MotionController, and MockMotionController classes.
"""

from __future__ import annotations

import pytest
import time
import threading

from andor_pymeasure.instruments.motion_controller import (
    Axis,
    MockAxis,
    MotionController,
    MockMotionController,
    SPEED_OF_LIGHT_MM_PS,
)


# =============================================================================
# Axis Base Class Tests
# =============================================================================


class TestAxisConstants:
    """Tests for module constants."""

    def test_speed_of_light_value(self):
        """Speed of light constant is correct."""
        # c = 299,792,458 m/s = 0.299792458 mm/ps
        assert abs(SPEED_OF_LIGHT_MM_PS - 0.299792458) < 1e-9


class TestAxisPositionConversions:
    """Tests for position unit conversions."""

    def test_position_ps_from_mm(self):
        """Position in ps is correctly calculated from mm."""
        # Create a mock controller and axis
        controller = MockMotionController()
        axis = controller.axes[0]

        axis.position = 10.0  # 10 mm
        # delay_ps = (2 * position_mm) / SPEED_OF_LIGHT_MM_PS
        expected_ps = (2 * 10.0) / SPEED_OF_LIGHT_MM_PS
        assert abs(axis.position_ps - expected_ps) < 0.001

    def test_position_ps_setter(self):
        """Position can be set in ps."""
        controller = MockMotionController()
        axis = controller.axes[0]

        target_ps = 100.0
        axis.position_ps = target_ps

        # position_mm = (position_ps * SPEED_OF_LIGHT_MM_PS) / 2
        expected_mm = (target_ps * SPEED_OF_LIGHT_MM_PS) / 2
        assert abs(axis.position - expected_mm) < 0.001

    def test_position_ps_roundtrip(self):
        """Setting ps and reading ps returns same value."""
        controller = MockMotionController()
        axis = controller.axes[0]

        target_ps = 50.0
        axis.position_ps = target_ps
        assert abs(axis.position_ps - target_ps) < 0.001


# =============================================================================
# MockAxis Tests
# =============================================================================


class TestMockAxisBasics:
    """Tests for MockAxis basic functionality."""

    def test_create_axis_with_name(self):
        """MockAxis can be created with a name."""
        controller = MockMotionController(
            axis_configs=[{"name": "delay", "index": 1}]
        )
        assert "delay" in [a.name for a in controller.axes]

    def test_axis_default_position(self):
        """Axis starts at position 0."""
        controller = MockMotionController()
        assert controller.axes[0].position == 0.0

    def test_axis_position_setter(self):
        """Axis position can be set."""
        controller = MockMotionController()
        axis = controller.axes[0]
        axis.position = 50.0
        assert axis.position == 50.0

    def test_axis_position_clamped_to_max(self):
        """Position is clamped to max limit."""
        controller = MockMotionController(
            axis_configs=[{"name": "test", "index": 1, "position_max": 100.0}]
        )
        axis = controller.test
        axis.position = 200.0  # Over max
        assert axis.position == 100.0

    def test_axis_position_clamped_to_min(self):
        """Position is clamped to min limit."""
        controller = MockMotionController(
            axis_configs=[{"name": "test", "index": 1, "position_min": 10.0}]
        )
        axis = controller.test
        axis.position = 0.0  # Under min
        assert axis.position == 10.0


class TestMockAxisMotion:
    """Tests for MockAxis motion control."""

    def test_axis_is_moving_initially_false(self):
        """Axis is not moving initially."""
        controller = MockMotionController()
        assert not controller.axes[0].is_moving

    def test_axis_motion_done_initially_true(self):
        """Axis motion is done initially."""
        controller = MockMotionController()
        assert controller.axes[0].motion_done

    def test_axis_home(self):
        """Home moves axis to position 0."""
        controller = MockMotionController()
        axis = controller.axes[0]
        axis.position = 50.0
        axis.home()
        axis.wait_for_stop()
        assert axis.position == 0.0

    def test_axis_stop(self):
        """Stop halts motion."""
        controller = MockMotionController()
        axis = controller.axes[0]
        axis._moving = True
        axis.stop()
        assert not axis.is_moving

    def test_axis_enable_disable(self):
        """Axis can be enabled/disabled."""
        controller = MockMotionController()
        axis = controller.axes[0]

        axis.enable()
        assert axis.enabled

        axis.disable()
        assert not axis.enabled


# =============================================================================
# MotionController Tests
# =============================================================================


class TestMotionControllerBasics:
    """Tests for MotionController basic functionality."""

    def test_create_mock_controller(self):
        """MockMotionController can be created."""
        controller = MockMotionController()
        assert controller is not None

    def test_controller_has_axes(self):
        """Controller has axes property."""
        controller = MockMotionController()
        assert len(controller.axes) > 0

    def test_controller_axis_by_name(self):
        """Axis can be accessed by name as attribute."""
        controller = MockMotionController(
            axis_configs=[{"name": "delay", "index": 1}]
        )
        axis = controller.delay
        assert axis.name == "delay"

    def test_controller_axis_by_name_missing_raises(self):
        """Accessing non-existent axis raises AttributeError."""
        controller = MockMotionController()
        with pytest.raises(AttributeError):
            _ = controller.nonexistent

    def test_controller_get_axis(self):
        """get_axis returns axis by name."""
        controller = MockMotionController(
            axis_configs=[{"name": "test_axis", "index": 1}]
        )
        axis = controller.get_axis("test_axis")
        assert axis is not None
        assert axis.name == "test_axis"

    def test_controller_get_axis_missing_returns_none(self):
        """get_axis returns None for missing axis."""
        controller = MockMotionController()
        assert controller.get_axis("nonexistent") is None


class TestMotionControllerMultiAxis:
    """Tests for multi-axis controller functionality."""

    def test_create_with_multiple_axes(self):
        """Controller can have multiple axes."""
        controller = MockMotionController(
            axis_configs=[
                {"name": "x", "index": 1},
                {"name": "y", "index": 2},
                {"name": "z", "index": 3},
            ]
        )
        assert len(controller.axes) == 3
        assert controller.x is not None
        assert controller.y is not None
        assert controller.z is not None

    def test_home_all(self):
        """home_all homes all axes."""
        controller = MockMotionController(
            axis_configs=[
                {"name": "x", "index": 1},
                {"name": "y", "index": 2},
            ]
        )
        controller.x.position = 10.0
        controller.y.position = 20.0

        controller.home_all()

        assert controller.x.position == 0.0
        assert controller.y.position == 0.0

    def test_enable_all(self):
        """enable_all enables all axes."""
        controller = MockMotionController(
            axis_configs=[
                {"name": "x", "index": 1},
                {"name": "y", "index": 2},
            ]
        )
        controller.enable_all()

        assert controller.x.enabled
        assert controller.y.enabled

    def test_disable_all(self):
        """disable_all disables all axes."""
        controller = MockMotionController(
            axis_configs=[
                {"name": "x", "index": 1},
                {"name": "y", "index": 2},
            ]
        )
        controller.enable_all()
        controller.disable_all()

        assert not controller.x.enabled
        assert not controller.y.enabled


class TestMotionControllerConfig:
    """Tests for controller configuration."""

    def test_home_on_startup_default_false(self):
        """home_on_startup defaults to False."""
        controller = MockMotionController()
        assert not controller.home_on_startup

    def test_home_on_startup_configurable(self):
        """home_on_startup can be set."""
        controller = MockMotionController(home_on_startup=True)
        assert controller.home_on_startup

    def test_axis_limits_from_config(self):
        """Axis limits can be set from config."""
        controller = MockMotionController(
            axis_configs=[{
                "name": "delay",
                "index": 1,
                "position_min": 10.0,
                "position_max": 200.0,
            }]
        )
        axis = controller.delay
        assert axis.position_min == 10.0
        assert axis.position_max == 200.0

    def test_axis_velocity_from_config(self):
        """Axis velocity can be set from config."""
        controller = MockMotionController(
            axis_configs=[{
                "name": "delay",
                "index": 1,
                "velocity": 50.0,
            }]
        )
        assert controller.delay.velocity == 50.0


class TestMotionControllerShutdown:
    """Tests for controller shutdown."""

    def test_shutdown(self):
        """Shutdown cleans up controller."""
        controller = MockMotionController()
        controller.shutdown()
        # Should not raise

    def test_shutdown_disables_axes(self):
        """Shutdown disables all axes."""
        controller = MockMotionController(
            axis_configs=[
                {"name": "x", "index": 1},
                {"name": "y", "index": 2},
            ]
        )
        controller.enable_all()
        controller.shutdown()

        assert not controller.x.enabled
        assert not controller.y.enabled
