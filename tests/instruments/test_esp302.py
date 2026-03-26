"""Unit tests for Newport ESP302 driver.

Uses a FakeSerial transport that records outgoing commands and returns
pre-programmed responses, so no real hardware is required.
"""

from __future__ import annotations

import io
from collections import deque
from unittest.mock import MagicMock, patch

import pytest

from andor_pymeasure.instruments.newport_esp302 import (
    MockNewportESP302,
    MockNewportESP302Axis,
    NewportESP302,
    NewportESP302Axis,
)
from andor_pymeasure.instruments.motion_controller import SPEED_OF_LIGHT_MM_PS


# ---------------------------------------------------------------------------
# Fake serial transport
# ---------------------------------------------------------------------------


class FakeSerial:
    """Minimal serial port simulator for ESP302 testing.

    Queues pre-programmed response lines (terminated \\r\\n) to be returned
    by readline().  Sent commands are accumulated in ``sent``.
    """

    def __init__(self, responses=()):
        self.sent: list[str] = []
        self._responses: deque[bytes] = deque(
            f"{r}\r\n".encode() for r in responses
        )

    def write(self, data: bytes) -> None:
        self.sent.append(data.decode())

    def readline(self) -> bytes:
        if self._responses:
            return self._responses.popleft()
        return b"\r\n"

    def close(self) -> None:
        pass

    def queue_response(self, response: str) -> None:
        """Add a response to the queue."""
        self._responses.append(f"{response}\r\n".encode())


def make_esp302(fake_serial: FakeSerial, axis_configs=None) -> NewportESP302:
    """Create a NewportESP302 wired to a FakeSerial without opening a real port."""
    axis_configs = axis_configs or [{"name": "delay", "index": 2}]
    with patch("serial.Serial", return_value=fake_serial):
        ctrl = NewportESP302(
            transport="serial",
            port="COM_FAKE",
            baudrate=19200,
            axis_configs=axis_configs,
        )
    return ctrl


# ---------------------------------------------------------------------------
# Startup sequence
# ---------------------------------------------------------------------------


class TestStartupSequence:
    """Verify commands sent during controller initialisation."""

    def test_startup_sends_motor_on(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        assert any("2MO\r" in s for s in fs.sent), f"MO not sent; got {fs.sent}"

    def test_startup_sends_mm_units(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        assert any("2SN2\r" in s for s in fs.sent), f"SN2 not sent; got {fs.sent}"

    def test_startup_sets_velocity(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs, axis_configs=[{"name": "delay", "index": 2, "velocity": 1.5}])
        assert any("2VA1.5\r" in s for s in fs.sent), f"VA not found in {fs.sent}"

    def test_startup_sets_acceleration(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs, axis_configs=[{"name": "delay", "index": 2, "acceleration": 25.0}])
        assert any("2AC25.0\r" in s for s in fs.sent), f"AC not found in {fs.sent}"

    def test_startup_sets_software_limits(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs, axis_configs=[{
            "name": "delay", "index": 2,
            "position_min": 5.0, "position_max": 250.0,
        }])
        assert any("2SL5.0\r" in s for s in fs.sent), f"SL not in {fs.sent}"
        assert any("2SR250.0\r" in s for s in fs.sent), f"SR not in {fs.sent}"

    def test_startup_switches_to_measurement_velocity(self):
        """Measurement velocity (VA) is sent AFTER init velocity."""
        fs = FakeSerial()
        ctrl = make_esp302(fs, axis_configs=[{
            "name": "delay", "index": 2,
            "init_velocity": 10.0, "velocity": 0.5,
        }])
        va_commands = [s for s in fs.sent if "2VA" in s]
        # Last VA command should be the measurement velocity
        assert va_commands[-1] == "2VA0.5\r", f"Last VA was {va_commands[-1]}"


# ---------------------------------------------------------------------------
# Position query
# ---------------------------------------------------------------------------


class TestPositionQuery:
    """Verify TP (tell position) command and response parsing."""

    def test_position_query_sends_tp(self):
        fs = FakeSerial(responses=["57.3"])
        ctrl = make_esp302(fs)
        fs.sent.clear()
        fs.queue_response("57.3")
        pos = ctrl.get_axis("delay").position
        assert any("2TP\r" in s for s in fs.sent), f"TP not sent; got {fs.sent}"

    def test_position_query_parses_float(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        fs.queue_response("123.456")
        pos = ctrl.get_axis("delay").position
        assert abs(pos - 123.456) < 1e-6

    def test_position_query_parses_negative(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        fs.queue_response("-12.5")
        pos = ctrl.get_axis("delay").position
        assert abs(pos - (-12.5)) < 1e-6


# ---------------------------------------------------------------------------
# Absolute move
# ---------------------------------------------------------------------------


class TestAbsoluteMove:
    """Verify PA command and motion-done polling."""

    def test_move_sends_pa_command(self):
        # Respond "1" to MD? (motion done immediately)
        fs = FakeSerial(responses=["1"])
        ctrl = make_esp302(fs)
        fs.sent.clear()
        fs.queue_response("1")  # MD? → done
        ctrl.get_axis("delay").position = 50.0
        assert any("2PA50.0\r" in s for s in fs.sent), f"PA not sent; got {fs.sent}"

    def test_move_polls_motion_done(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        fs.sent.clear()
        fs.queue_response("1")  # MD? → done
        ctrl.get_axis("delay").position = 25.0
        md_queries = [s for s in fs.sent if "2MD?\r" in s]
        assert len(md_queries) >= 1, f"MD? not polled; got {fs.sent}"

    def test_move_waits_while_moving(self):
        """MD? is polled until '1' is returned."""
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        fs.sent.clear()
        # Return "0" twice (still moving) then "1" (done)
        fs.queue_response("0")
        fs.queue_response("0")
        fs.queue_response("1")
        ctrl.get_axis("delay").position = 30.0
        md_queries = [s for s in fs.sent if "2MD?\r" in s]
        assert len(md_queries) == 3

    def test_move_clamps_to_max(self):
        """Move beyond position_max is clamped before PA is sent."""
        fs = FakeSerial(responses=["1"])
        ctrl = make_esp302(fs, axis_configs=[{
            "name": "delay", "index": 2, "position_max": 100.0
        }])
        fs.sent.clear()
        fs.queue_response("1")
        ctrl.get_axis("delay").position = 500.0  # over max
        pa_commands = [s for s in fs.sent if "2PA" in s]
        assert pa_commands, "No PA command sent"
        value = float(pa_commands[0].replace("2PA", "").rstrip("\r"))
        assert value <= 100.0

    def test_move_clamps_to_min(self):
        """Move below position_min is clamped before PA is sent."""
        fs = FakeSerial()
        ctrl = make_esp302(fs, axis_configs=[{
            "name": "delay", "index": 2, "position_min": 10.0
        }])
        fs.sent.clear()
        fs.queue_response("1")
        ctrl.get_axis("delay").position = 0.0  # under min
        pa_commands = [s for s in fs.sent if "2PA" in s]
        assert pa_commands
        value = float(pa_commands[0].replace("2PA", "").rstrip("\r"))
        assert value >= 10.0


# ---------------------------------------------------------------------------
# Emergency stop
# ---------------------------------------------------------------------------


class TestEmergencyStop:
    """Verify AB (all-stop) command."""

    def test_emergency_stop_sends_ab(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        fs.sent.clear()
        ctrl.emergency_stop()
        assert any("AB\r" in s for s in fs.sent), f"AB not sent; got {fs.sent}"

    def test_stop_axis_sends_st(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        fs.sent.clear()
        ctrl.get_axis("delay").stop()
        assert any("2ST\r" in s for s in fs.sent), f"ST not sent; got {fs.sent}"


# ---------------------------------------------------------------------------
# Home command
# ---------------------------------------------------------------------------


class TestHome:
    """Verify OR (home search) command."""

    def test_home_sends_or1(self):
        fs = FakeSerial(responses=["0", "1"])  # SH0 + OR1 polling
        ctrl = make_esp302(fs)
        fs.sent.clear()
        fs.queue_response("1")  # MD? → done
        ctrl.get_axis("delay").home(home_type=1)
        assert any("2OR1\r" in s for s in fs.sent), f"OR1 not sent; got {fs.sent}"

    def test_home_sends_sh0_first(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        fs.sent.clear()
        fs.queue_response("1")
        ctrl.get_axis("delay").home()
        sh_idx = next((i for i, s in enumerate(fs.sent) if "2SH0\r" in s), None)
        or_idx = next((i for i, s in enumerate(fs.sent) if "2OR" in s), None)
        assert sh_idx is not None, "SH0 not sent"
        assert or_idx is not None, "OR not sent"
        assert sh_idx < or_idx, "SH0 must come before OR"


# ---------------------------------------------------------------------------
# position_ps with t0_offset_mm
# ---------------------------------------------------------------------------


class TestPositionPsWithT0Offset:
    """Verify t0_offset_mm correctly shifts position_ps origin."""

    def test_position_ps_at_t0_is_zero(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        axis = ctrl.get_axis("delay")
        axis.t0_offset_mm = 50.0
        # When position == t0_offset_mm, delay should be 0 ps
        fs.queue_response("50.0")
        assert abs(axis.position_ps - 0.0) < 1e-9

    def test_position_ps_positive_delay(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        axis = ctrl.get_axis("delay")
        axis.t0_offset_mm = 50.0
        fs.queue_response("55.0")  # 5 mm past t0
        expected_ps = (2 * 5.0) / SPEED_OF_LIGHT_MM_PS
        assert abs(axis.position_ps - expected_ps) < 1e-6

    def test_position_ps_setter_with_t0_offset(self):
        fs = FakeSerial()
        ctrl = make_esp302(fs)
        axis = ctrl.get_axis("delay")
        axis.t0_offset_mm = 50.0
        # Setting 100 ps should command position = t0 + (100 * c/2)
        expected_mm = 50.0 + (100.0 * SPEED_OF_LIGHT_MM_PS) / 2.0
        fs.queue_response("1")  # MD? → done
        axis.position_ps = 100.0
        pa_commands = [s for s in fs.sent if "2PA" in s]
        assert pa_commands, "No PA command sent"
        value = float(pa_commands[-1].replace("2PA", "").rstrip("\r"))
        assert abs(value - expected_mm) < 1e-6


# ---------------------------------------------------------------------------
# Mock ESP302 tests (no serial needed)
# ---------------------------------------------------------------------------


class TestMockNewportESP302:
    """Verify MockNewportESP302 behaves correctly without hardware."""

    def test_creates_delay_axis(self):
        ctrl = MockNewportESP302()
        assert ctrl.get_axis("delay") is not None

    def test_default_axis_index_2(self):
        ctrl = MockNewportESP302()
        assert ctrl.get_axis("delay").index == 2

    def test_position_ps_roundtrip(self):
        ctrl = MockNewportESP302()
        axis = ctrl.get_axis("delay")
        axis.position_ps = 150.0
        assert abs(axis.position_ps - 150.0) < 1e-9

    def test_t0_offset_shifts_delay(self):
        ctrl = MockNewportESP302()
        axis = ctrl.get_axis("delay")
        axis.t0_offset_mm = 30.0
        axis.position = 30.0  # at t0
        assert abs(axis.position_ps - 0.0) < 1e-9

    def test_position_clamped_to_max(self):
        ctrl = MockNewportESP302(axis_configs=[{
            "name": "delay", "index": 2, "position_max": 100.0
        }])
        axis = ctrl.get_axis("delay")
        axis.position = 999.0
        assert axis.position == 100.0

    def test_emergency_stop(self):
        ctrl = MockNewportESP302()
        ctrl.emergency_stop()  # should not raise
