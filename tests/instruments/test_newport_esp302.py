"""Tests for NewportESP302 motion controller driver.

Tests cover:
- MockNewportESP302: position read/write, enable/disable, home, stop, emergency stop
- NewportESP302 serial transport with mocked serial.Serial
- ps/mm conversion via inherited position_ps property
- Startup command sequence
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, call, patch

import pytest

from andor_pymeasure.instruments.newport_esp302 import (
    MockNewportESP302,
    NewportESP302,
    NewportESP302Axis,
)


# ---------------------------------------------------------------------------
# MockNewportESP302 tests
# ---------------------------------------------------------------------------


class TestMockNewportESP302:
    def _make_ctrl(self, **kwargs):
        axis_configs = kwargs.pop(
            "axis_configs",
            [{"name": "delay", "index": 1, "position_min": 0.0, "position_max": 150.0}],
        )
        return MockNewportESP302(axis_configs=axis_configs, **kwargs)

    def test_creates_axes(self):
        ctrl = self._make_ctrl()
        assert len(ctrl.axes) == 1
        assert ctrl.get_axis("delay") is not None

    def test_default_position_is_zero(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        assert axis.position == pytest.approx(0.0)

    def test_set_position_moves_axis(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        axis.position = 50.0
        assert axis.position == pytest.approx(50.0)

    def test_position_clamped_to_limits(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        axis.position = 200.0  # beyond max 150
        assert axis.position == pytest.approx(150.0)

    def test_position_ps_roundtrip(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        axis.position_ps = 100.0  # 100 ps
        # position_mm = 100 * 0.299792458 / 2 ≈ 14.989...
        expected_mm = 100.0 * 0.299792458 / 2
        assert axis.position == pytest.approx(expected_mm, rel=1e-5)
        assert axis.position_ps == pytest.approx(100.0, rel=1e-5)

    def test_is_not_moving_at_rest(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        assert axis.is_moving is False

    def test_enable_disable(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        axis.disable()
        assert axis.enabled is False
        axis.enable()
        assert axis.enabled is True

    def test_home_resets_to_zero(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        axis.position = 75.0
        axis.home()
        assert axis.position == pytest.approx(0.0)

    def test_stop_halts_motion(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        # Stop while at rest should be a no-op
        axis.stop()
        assert axis.is_moving is False

    def test_emergency_stop(self):
        ctrl = self._make_ctrl()
        # Should not raise
        ctrl.emergency_stop()

    def test_shutdown(self):
        ctrl = self._make_ctrl()
        ctrl.shutdown()  # Should not raise

    def test_multiple_axes(self):
        ctrl = MockNewportESP302(
            axis_configs=[
                {"name": "delay", "index": 1},
                {"name": "pump", "index": 2},
            ]
        )
        assert ctrl.get_axis("delay") is not None
        assert ctrl.get_axis("pump") is not None

    def test_t0_offset_default_zero(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        assert axis.t0_offset_mm == pytest.approx(0.0)

    def test_set_t0_offset(self):
        ctrl = self._make_ctrl()
        axis = ctrl.get_axis("delay")
        axis.t0_offset_mm = 10.0
        assert axis.t0_offset_mm == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# NewportESP302Axis ps↔mm with t0 offset
# ---------------------------------------------------------------------------


class TestNewportESP302AxisT0:
    def test_position_ps_uses_t0_offset(self):
        ctrl = MockNewportESP302(
            axis_configs=[{"name": "delay", "index": 1}]
        )
        axis = ctrl.get_axis("delay")
        axis.t0_offset_mm = 5.0
        axis.position = 10.0
        # delay_ps = 2 * (position - t0) / c
        expected_ps = 2 * (10.0 - 5.0) / 0.299792458
        assert axis.position_ps == pytest.approx(expected_ps, rel=1e-5)

    def test_set_position_ps_uses_t0_offset(self):
        ctrl = MockNewportESP302(
            axis_configs=[{"name": "delay", "index": 1}]
        )
        axis = ctrl.get_axis("delay")
        axis.t0_offset_mm = 5.0
        axis.position_ps = 0.0  # t0 → stage at t0_offset_mm
        assert axis.position == pytest.approx(5.0, rel=1e-5)


# ---------------------------------------------------------------------------
# NewportESP302 serial transport (mocked)
# ---------------------------------------------------------------------------


class TestNewportESP302Serial:
    """Tests for NewportESP302 with serial transport using mock serial.Serial."""

    def _make_responses(self, responses: list[str]):
        """Build a mock serial that returns encoded responses from a list."""
        mock_serial = MagicMock()
        encoded = [f"{r}\r\n".encode() for r in responses]
        mock_serial.readline.side_effect = encoded
        return mock_serial

    @patch("serial.Serial")
    def test_connects_via_serial(self, mock_serial_cls):
        mock_conn = self._make_responses(["1"])  # for MD? poll during home
        mock_serial_cls.return_value = mock_conn

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            baudrate=19200,
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_serial_cls.assert_called_once()
        call_kwargs = mock_serial_cls.call_args[1]
        assert call_kwargs["port"] == "COM3"
        assert call_kwargs["baudrate"] == 19200
        assert call_kwargs["rtscts"] is True

    @patch("serial.Serial")
    def test_startup_sends_mo_sn_va_ac_sl_sr(self, mock_serial_cls):
        mock_conn = MagicMock()
        mock_serial_cls.return_value = mock_conn

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[
                {
                    "name": "delay",
                    "index": 1,
                    "velocity": 20.0,
                    "acceleration": 10.0,
                    "position_min": -50.0,
                    "position_max": 100.0,
                }
            ],
        )

        written = b"".join(c.args[0] for c in mock_conn.write.call_args_list)
        assert b"1MO\r" in written
        assert b"1SN2\r" in written
        assert b"1VA20.0\r" in written
        assert b"1AC10.0\r" in written
        assert b"1SL-50.0\r" in written
        assert b"1SR100.0\r" in written

    @patch("serial.Serial")
    def test_position_query_sends_tp(self, mock_serial_cls):
        mock_conn = self._make_responses(["75.0"])
        mock_serial_cls.return_value = mock_conn

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_conn.write.reset_mock()
        mock_conn.readline.side_effect = [b"75.0\r\n"]

        axis = ctrl.get_axis("delay")
        pos = axis.position
        assert pos == pytest.approx(75.0)
        mock_conn.write.assert_called_with(b"1TP\r")

    @patch("serial.Serial")
    def test_set_position_sends_pa(self, mock_serial_cls):
        mock_conn = MagicMock()
        mock_serial_cls.return_value = mock_conn
        # MD? polling response: "1" means done
        mock_conn.readline.return_value = b"1\r\n"

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_conn.write.reset_mock()

        axis = ctrl.get_axis("delay")
        axis.position = 30.0

        written = b"".join(c.args[0] for c in mock_conn.write.call_args_list)
        assert b"1PA30.0\r" in written

    @patch("serial.Serial")
    def test_is_moving_polls_md(self, mock_serial_cls):
        mock_conn = self._make_responses(["0"])  # "0" = still moving
        mock_serial_cls.return_value = mock_conn

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_conn.readline.return_value = b"0\r\n"

        axis = ctrl.get_axis("delay")
        assert axis.is_moving is True

    @patch("serial.Serial")
    def test_home_sends_sh_or(self, mock_serial_cls):
        mock_conn = MagicMock()
        mock_serial_cls.return_value = mock_conn
        mock_conn.readline.return_value = b"1\r\n"  # MD? = done

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_conn.write.reset_mock()

        axis = ctrl.get_axis("delay")
        axis.home()

        written = b"".join(c.args[0] for c in mock_conn.write.call_args_list)
        assert b"1SH0\r" in written
        assert b"1OR1\r" in written

    @patch("serial.Serial")
    def test_stop_sends_st(self, mock_serial_cls):
        mock_conn = MagicMock()
        mock_serial_cls.return_value = mock_conn

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_conn.write.reset_mock()

        axis = ctrl.get_axis("delay")
        axis.stop()

        mock_conn.write.assert_called_with(b"1ST\r")

    @patch("serial.Serial")
    def test_emergency_stop_sends_ab(self, mock_serial_cls):
        mock_conn = MagicMock()
        mock_serial_cls.return_value = mock_conn

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_conn.write.reset_mock()

        ctrl.emergency_stop()

        mock_conn.write.assert_called_with(b"AB\r")

    @patch("serial.Serial")
    def test_enable_sends_mo(self, mock_serial_cls):
        mock_conn = MagicMock()
        mock_serial_cls.return_value = mock_conn

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_conn.write.reset_mock()

        axis = ctrl.get_axis("delay")
        axis.enable()

        mock_conn.write.assert_called_with(b"1MO\r")

    @patch("serial.Serial")
    def test_disable_sends_mf(self, mock_serial_cls):
        mock_conn = MagicMock()
        mock_serial_cls.return_value = mock_conn

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_conn.write.reset_mock()

        axis = ctrl.get_axis("delay")
        axis.disable()

        mock_conn.write.assert_called_with(b"1MF\r")

    @patch("serial.Serial")
    def test_shutdown_closes_connection(self, mock_serial_cls):
        mock_conn = MagicMock()
        mock_serial_cls.return_value = mock_conn

        ctrl = NewportESP302(
            transport="serial",
            port="COM3",
            axis_configs=[{"name": "delay", "index": 1}],
        )
        ctrl.shutdown()

        mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# NewportESP302 socket transport
# ---------------------------------------------------------------------------


class TestNewportESP302Socket:
    @patch("socket.socket")
    def test_connects_via_socket(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        # recv returns "1\r\n" for any MD? or query
        mock_sock.recv.return_value = b"1\r\n"

        ctrl = NewportESP302(
            transport="socket",
            host="192.168.0.10",
            tcp_port=5001,
            axis_configs=[{"name": "delay", "index": 1}],
        )

        mock_sock.connect.assert_called_once_with(("192.168.0.10", 5001))

    @patch("socket.socket")
    def test_socket_sends_crlf_terminated_pa(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.recv.return_value = b"1\r\n"

        ctrl = NewportESP302(
            transport="socket",
            host="192.168.0.10",
            tcp_port=5001,
            axis_configs=[{"name": "delay", "index": 1}],
        )
        mock_sock.sendall.reset_mock()
        mock_sock.recv.return_value = b"1\r\n"

        axis = ctrl.get_axis("delay")
        axis.position = 20.0

        sent = b"".join(c.args[0] for c in mock_sock.sendall.call_args_list)
        assert b"1PA20.0\r" in sent
