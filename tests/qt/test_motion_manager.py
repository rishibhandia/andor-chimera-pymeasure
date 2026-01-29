"""Tests for MotionControllerManager.

Tests for config parsing, controller creation, axis management.
"""

from __future__ import annotations

import pytest

from andor_qt.core.motion_manager import MotionControllerManager, CONTROLLER_TYPES


# =============================================================================
# MotionControllerManager Creation Tests
# =============================================================================


class TestMotionControllerManagerCreation:
    """Tests for manager creation."""

    def test_create_empty_config(self):
        """Manager can be created with empty config."""
        manager = MotionControllerManager({})
        assert manager is not None

    def test_create_with_disabled_config(self):
        """Manager can be created with disabled motion controllers."""
        config = {"enabled": False}
        manager = MotionControllerManager(config)
        manager.initialize()
        assert len(manager.controllers) == 0

    def test_create_with_mock_controller(self):
        """Manager creates mock controller from config."""
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "test_stage",
                    "type": "mock",
                    "axes": [{"name": "delay", "index": 1}],
                }
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()

        assert len(manager.controllers) == 1
        assert "test_stage" in manager.controllers


class TestMotionControllerManagerInitialization:
    """Tests for manager initialization."""

    def test_initialize_creates_controllers(self):
        """Initialize creates controllers from config."""
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "stage1",
                    "type": "mock",
                    "axes": [{"name": "x", "index": 1}],
                },
                {
                    "name": "stage2",
                    "type": "mock",
                    "axes": [{"name": "y", "index": 1}],
                },
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()

        assert len(manager.controllers) == 2
        assert "stage1" in manager.controllers
        assert "stage2" in manager.controllers

    def test_initialize_with_home_on_startup(self):
        """Initialize homes controllers with home_on_startup=True."""
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "stage",
                    "type": "mock",
                    "home_on_startup": True,
                    "axes": [{"name": "delay", "index": 1}],
                }
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()

        # Axis should be at position 0 after homing
        axis = manager.get_axis("delay")
        assert axis.position == 0.0


class TestMotionControllerManagerAxisAccess:
    """Tests for axis access methods."""

    def test_get_axis_by_name(self):
        """get_axis returns axis by name."""
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "stage",
                    "type": "mock",
                    "axes": [{"name": "delay", "index": 1}],
                }
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()

        axis = manager.get_axis("delay")
        assert axis is not None
        assert axis.name == "delay"

    def test_get_axis_missing_returns_none(self):
        """get_axis returns None for missing axis."""
        config = {"enabled": True, "controllers": []}
        manager = MotionControllerManager(config)
        manager.initialize()

        assert manager.get_axis("nonexistent") is None

    def test_all_axes_property(self):
        """all_axes returns dict of all axes from all controllers."""
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "stage1",
                    "type": "mock",
                    "axes": [
                        {"name": "x", "index": 1},
                        {"name": "y", "index": 2},
                    ],
                },
                {
                    "name": "stage2",
                    "type": "mock",
                    "axes": [{"name": "z", "index": 1}],
                },
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()

        all_axes = manager.all_axes
        assert len(all_axes) == 3
        assert "x" in all_axes
        assert "y" in all_axes
        assert "z" in all_axes


class TestMotionControllerManagerAxisConfig:
    """Tests for axis configuration."""

    def test_axis_limits_from_config(self):
        """Axis limits are set from config."""
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "stage",
                    "type": "mock",
                    "axes": [
                        {
                            "name": "delay",
                            "index": 1,
                            "position_min": 10.0,
                            "position_max": 200.0,
                        }
                    ],
                }
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()

        axis = manager.get_axis("delay")
        assert axis.position_min == 10.0
        assert axis.position_max == 200.0

    def test_axis_velocity_from_config(self):
        """Axis velocity is set from config."""
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "stage",
                    "type": "mock",
                    "axes": [
                        {
                            "name": "delay",
                            "index": 1,
                            "velocity": 50.0,
                        }
                    ],
                }
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()

        axis = manager.get_axis("delay")
        assert axis.velocity == 50.0


class TestMotionControllerManagerShutdown:
    """Tests for manager shutdown."""

    def test_shutdown_shuts_down_controllers(self):
        """Shutdown shuts down all controllers."""
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "stage",
                    "type": "mock",
                    "axes": [{"name": "delay", "index": 1}],
                }
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()
        manager.shutdown()

        # Controller should be shut down (axes disabled)
        axis = manager.get_axis("delay")
        assert not axis.enabled


class TestControllerTypeRegistry:
    """Tests for controller type registry."""

    def test_mock_controller_in_registry(self):
        """Mock controller type is in registry."""
        assert "mock" in CONTROLLER_TYPES

    def test_unknown_controller_type_logged(self, caplog):
        """Unknown controller type logs warning."""
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "stage",
                    "type": "unknown_type",
                    "axes": [{"name": "delay", "index": 1}],
                }
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()

        assert "Unknown controller type" in caplog.text
        assert len(manager.controllers) == 0
