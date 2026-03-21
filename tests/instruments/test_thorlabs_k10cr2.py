"""Tests for ThorlabsK10CR2 Kinesis rotation stage controller.

Tests use only MockThorlabsK10CR2 (no Kinesis DLLs needed in CI).
Also verifies that ThorlabsK10CR2 class raises ImportError when
thorlabs-kinesis is not available.

position_ps raises NotImplementedError (rotation stage, no optical delay).
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from andor_pymeasure.instruments.thorlabs_k10cr2 import (
    MockThorlabsK10CR2,
    ThorlabsK10CR2,
)


# ---------------------------------------------------------------------------
# MockThorlabsK10CR2 tests
# ---------------------------------------------------------------------------


class TestMockThorlabsK10CR2:
    def _make_ctrl(self, **kwargs):
        axis_configs = kwargs.pop(
            "axis_configs",
            [{"name": "waveplate", "index": 0}],
        )
        return MockThorlabsK10CR2(axis_configs=axis_configs, **kwargs)

    def test_creates_axes(self):
        ctrl = self._make_ctrl()
        assert ctrl.get_axis("waveplate") is not None

    def test_default_position_is_zero(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("waveplate")
        assert axis.position == pytest.approx(0.0)

    def test_set_position_rotates(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("waveplate")
        axis.position = 90.0
        assert axis.position == pytest.approx(90.0)

    def test_position_clamped_to_limits(self):
        ctrl = MockThorlabsK10CR2(
            axis_configs=[{"name": "wp", "index": 0, "position_max": 180.0}]
        )
        axis = ctrl.get_axis("wp")
        axis.position = 400.0
        assert axis.position == pytest.approx(180.0)

    def test_position_ps_raises(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("waveplate")
        with pytest.raises(NotImplementedError):
            _ = axis.position_ps

    def test_set_position_ps_raises(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("waveplate")
        with pytest.raises(NotImplementedError):
            axis.position_ps = 100.0

    def test_is_not_moving_at_rest(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("waveplate")
        assert axis.is_moving is False

    def test_enable_disable(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("waveplate")
        axis.disable()
        assert axis.enabled is False
        axis.enable()
        assert axis.enabled is True

    def test_home_resets_to_zero(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("waveplate")
        axis.position = 180.0
        axis.home()
        assert axis.position == pytest.approx(0.0)

    def test_stop(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("waveplate")
        axis.stop()
        assert axis.is_moving is False

    def test_emergency_stop(self):
        ctrl = self._make_ctrl()
        ctrl.emergency_stop()

    def test_shutdown(self):
        ctrl = self._make_ctrl()
        ctrl.shutdown()


# ---------------------------------------------------------------------------
# ThorlabsK10CR2 — verify ImportError when Kinesis absent
# ---------------------------------------------------------------------------


class TestThorlabsK10CR2Import:
    def test_raises_import_error_when_kinesis_absent(self):
        """ThorlabsK10CR2 should raise ImportError when thorlabs-kinesis missing."""
        with patch.dict(sys.modules, {"thorlabs_kinesis": None, "thorlabs_kinesis.benchtop_stepper_motor": None}):
            with pytest.raises((ImportError, TypeError)):
                ThorlabsK10CR2(
                    axis_configs=[{"name": "wp", "index": 0}],
                    serial_number=55000001,
                )
