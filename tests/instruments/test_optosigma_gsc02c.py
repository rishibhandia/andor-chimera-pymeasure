"""Tests for OptoSigma GSC-02C RS-232 rotation stage controller driver.

Tests cover:
- MockGSC02C: position read/write in pulses and degrees, home, stop, emergency stop
- GSC02C serial transport with mocked serial.Serial
- position_ps raises NotImplementedError (rotation stage — no delay)
- Axis command sequences: A: + G:, H:, L:, L:E
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from andor_pymeasure.instruments.optosigma_gsc02c import (
    GSC02C,
    GSC02CAxis,
    MockGSC02C,
)


# ---------------------------------------------------------------------------
# MockGSC02C tests
# ---------------------------------------------------------------------------


class TestMockGSC02C:
    def _make_ctrl(self, **kwargs):
        axis_configs = kwargs.pop(
            "axis_configs",
            [{"name": "polarizer", "index": 1}],
        )
        return MockGSC02C(axis_configs=axis_configs, **kwargs)

    def test_creates_axes(self):
        ctrl = self._make_ctrl()
        assert ctrl.get_axis("polarizer") is not None

    def test_default_position_is_zero_pulses(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        assert axis.position == pytest.approx(0.0)

    def test_set_position_updates_degrees(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        axis.position = 45.0
        assert axis.position == pytest.approx(45.0)

    def test_position_clamped_to_limits(self):
        ctrl = self._make_ctrl(
            axis_configs=[{"name": "polarizer", "index": 1, "position_max": 90.0}]
        )
        axis = ctrl.get_axis("polarizer")
        axis.position = 200.0
        assert axis.position == pytest.approx(90.0)

    def test_position_pulses_property(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        axis.position = 45.0  # 45 degrees
        # 45° × 400 pulses/° = 18000 pulses
        assert axis.position_pulses == 18000

    def test_set_position_pulses(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        axis.position_pulses = 4000  # 4000 / 400 = 10°
        assert axis.position == pytest.approx(10.0)

    def test_pulses_per_degree_configurable(self):
        ctrl = MockGSC02C(
            axis_configs=[{"name": "polarizer", "index": 1, "pulses_per_degree": 200}]
        )
        axis = ctrl.get_axis("polarizer")
        axis.position = 90.0
        assert axis.position_pulses == 18000  # 90 × 200

    def test_position_ps_raises(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        with pytest.raises(NotImplementedError):
            _ = axis.position_ps

    def test_set_position_ps_raises(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        with pytest.raises(NotImplementedError):
            axis.position_ps = 100.0

    def test_is_not_moving_at_rest(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        assert axis.is_moving is False

    def test_enable_disable(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        axis.disable()
        assert axis.enabled is False
        axis.enable()
        assert axis.enabled is True

    def test_home_resets_to_zero(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        axis.position = 90.0
        axis.home()
        assert axis.position == pytest.approx(0.0)

    def test_stop(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("polarizer")
        axis.stop()  # Should not raise
        assert axis.is_moving is False

    def test_emergency_stop(self):
        ctrl = self._make_ctrl()
        ctrl.emergency_stop()  # Should not raise

    def test_shutdown(self):
        ctrl = self._make_ctrl()
        ctrl.shutdown()  # Should not raise


# ---------------------------------------------------------------------------
# GSC02C real hardware (mocked serial)
# ---------------------------------------------------------------------------


class TestGSC02CSerial:
    def _mock_serial(self, responses: list[str]):
        """Build a mock serial.Serial with readline side effects."""
        mock_s = MagicMock()
        mock_s.readline.side_effect = [f"{r}\r\n".encode() for r in responses]
        return mock_s

    @patch("serial.Serial")
    def test_connects_with_correct_params(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s
        mock_s.readline.return_value = b"R\r\n"

        ctrl = GSC02C(port="COM4", baudrate=9600, axis_configs=[{"name": "pol", "index": 1}])

        call_kwargs = mock_serial_cls.call_args[1]
        assert call_kwargs["port"] == "COM4"
        assert call_kwargs["baudrate"] == 9600
        assert call_kwargs["rtscts"] is True

    @patch("serial.Serial")
    def test_position_query_sends_Q(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s
        # Q: response: "pos1, pos2, ACK1, ACK2, ACK3"
        # Return for Q: during construction (if any) and then our test query
        mock_s.readline.return_value = b"-        0,+        0,K,K,R\r\n"

        ctrl = GSC02C(port="COM4", axis_configs=[{"name": "pol", "index": 1}])
        axis = ctrl.get_axis("pol")
        mock_s.write.reset_mock()
        mock_s.readline.return_value = b"-        0,+        0,K,K,R\r\n"

        pos = axis.position
        assert pos == pytest.approx(0.0)
        written = b"".join(c.args[0] for c in mock_s.write.call_args_list)
        assert b"Q:\r\n" in written

    @patch("serial.Serial")
    def test_set_position_sends_A_then_G(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s
        # is_busy poll: first "B" (busy), then "R" (ready) so wait_for_stop exits
        mock_s.readline.side_effect = [
            b"R\r\n",  # !: during any startup check
            b"R\r\n",  # is_busy poll after G:
        ]

        ctrl = GSC02C(port="COM4", axis_configs=[{"name": "pol", "index": 1}])
        mock_s.write.reset_mock()
        mock_s.readline.side_effect = [b"R\r\n"]  # ready

        axis = ctrl.get_axis("pol")
        axis.position = 45.0  # 45° → 18000 pulses

        written = b"".join(c.args[0] for c in mock_s.write.call_args_list)
        assert b"A:1+P18000\r\n" in written
        assert b"G:\r\n" in written

    @patch("serial.Serial")
    def test_negative_position_sends_minus_direction(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s
        mock_s.readline.return_value = b"R\r\n"

        ctrl = GSC02C(
            port="COM4",
            axis_configs=[{"name": "pol", "index": 1, "position_min": -180.0}],
        )
        mock_s.write.reset_mock()
        mock_s.readline.return_value = b"R\r\n"

        axis = ctrl.get_axis("pol")
        axis.position = -45.0  # 45° CW → minus direction

        written = b"".join(c.args[0] for c in mock_s.write.call_args_list)
        assert b"A:1-P18000\r\n" in written

    @patch("serial.Serial")
    def test_home_sends_H_minus(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s
        mock_s.readline.return_value = b"R\r\n"

        ctrl = GSC02C(port="COM4", axis_configs=[{"name": "pol", "index": 1}])
        mock_s.write.reset_mock()
        mock_s.readline.return_value = b"R\r\n"

        axis = ctrl.get_axis("pol")
        axis.home()

        written = b"".join(c.args[0] for c in mock_s.write.call_args_list)
        assert b"H:1-\r\n" in written

    @patch("serial.Serial")
    def test_stop_sends_L_W(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s

        ctrl = GSC02C(port="COM4", axis_configs=[{"name": "pol", "index": 1}])
        mock_s.write.reset_mock()

        axis = ctrl.get_axis("pol")
        axis.stop()

        mock_s.write.assert_called_with(b"L:W\r\n")

    @patch("serial.Serial")
    def test_emergency_stop_sends_LE(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s

        ctrl = GSC02C(port="COM4", axis_configs=[{"name": "pol", "index": 1}])
        mock_s.write.reset_mock()

        ctrl.emergency_stop()

        mock_s.write.assert_called_with(b"L:E\r\n")

    @patch("serial.Serial")
    def test_is_moving_polls_busy(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s
        mock_s.readline.return_value = b"B\r\n"  # busy

        ctrl = GSC02C(port="COM4", axis_configs=[{"name": "pol", "index": 1}])
        axis = ctrl.get_axis("pol")
        mock_s.readline.return_value = b"B\r\n"

        assert axis.is_moving is True

    @patch("serial.Serial")
    def test_position_ps_raises_not_implemented(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s
        mock_s.readline.return_value = b"-        0,+        0,K,K,R\r\n"

        ctrl = GSC02C(port="COM4", axis_configs=[{"name": "pol", "index": 1}])
        axis = ctrl.get_axis("pol")

        with pytest.raises(NotImplementedError):
            _ = axis.position_ps

    @patch("serial.Serial")
    def test_shutdown_closes_serial(self, mock_serial_cls):
        mock_s = MagicMock()
        mock_serial_cls.return_value = mock_s

        ctrl = GSC02C(port="COM4", axis_configs=[{"name": "pol", "index": 1}])
        ctrl.shutdown()

        mock_s.close.assert_called_once()
