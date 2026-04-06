"""Tests for MotionControllerManager.set_axis_hardware_index.

Tests that the delay axis hardware index can be changed at runtime,
enabling the user to select ESP302 axes 1-3 from the UI.
"""

from __future__ import annotations

import pytest

from andor_qt.core.motion_manager import MotionControllerManager


def _make_manager(axis_index: int = 2) -> MotionControllerManager:
    """Create and initialize a manager with a single mock ESP302 axis."""
    config = {
        "enabled": True,
        "controllers": [
            {
                "name": "esp",
                "type": "mock_esp302",
                "axes": [{"name": "delay", "index": axis_index}],
            }
        ],
    }
    mgr = MotionControllerManager(config)
    mgr.initialize()
    return mgr


class TestSetAxisHardwareIndex:
    """Tests for MotionControllerManager.set_axis_hardware_index."""

    def test_changes_axis_index(self):
        """set_axis_hardware_index mutates axis.index to the new value."""
        mgr = _make_manager(axis_index=2)
        axis = mgr.get_axis("delay")
        assert axis.index == 2

        mgr.set_axis_hardware_index("delay", 3)
        assert axis.index == 3

    def test_changes_axis_index_to_1(self):
        """Can switch from default axis 2 to axis 1."""
        mgr = _make_manager(axis_index=2)
        mgr.set_axis_hardware_index("delay", 1)
        assert mgr.get_axis("delay").index == 1

    def test_same_object_after_index_change(self):
        """The axis object identity is preserved after index change."""
        mgr = _make_manager(axis_index=2)
        axis_before = mgr.get_axis("delay")
        mgr.set_axis_hardware_index("delay", 3)
        axis_after = mgr.get_axis("delay")
        assert axis_before is axis_after

    def test_unknown_axis_raises_key_error(self):
        """set_axis_hardware_index raises KeyError for unknown axis name."""
        mgr = _make_manager()
        with pytest.raises(KeyError, match="no_such_axis"):
            mgr.set_axis_hardware_index("no_such_axis", 1)

    def test_index_zero_raises_value_error(self):
        """Index 0 is out of range and raises ValueError."""
        mgr = _make_manager()
        with pytest.raises(ValueError, match="must be between 1 and 3"):
            mgr.set_axis_hardware_index("delay", 0)

    def test_index_four_raises_value_error(self):
        """Index 4 is out of range and raises ValueError."""
        mgr = _make_manager()
        with pytest.raises(ValueError, match="must be between 1 and 3"):
            mgr.set_axis_hardware_index("delay", 4)

    def test_negative_index_raises_value_error(self):
        """Negative index raises ValueError."""
        mgr = _make_manager()
        with pytest.raises(ValueError, match="must be between 1 and 3"):
            mgr.set_axis_hardware_index("delay", -1)

    def test_index_change_persists_across_get_axis_calls(self):
        """After changing index, subsequent get_axis calls reflect the change."""
        mgr = _make_manager(axis_index=1)
        mgr.set_axis_hardware_index("delay", 3)
        # Fresh lookup should see index=3
        assert mgr.get_axis("delay").index == 3
