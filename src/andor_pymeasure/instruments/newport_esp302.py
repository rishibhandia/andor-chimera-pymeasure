"""Newport ESP302 multi-axis motion controller driver.

Supports two transports:
- ``transport="serial"``  — RS-232C with hardware flow control (rtscts=True)
- ``transport="socket"``  — TCP/IP port 5001 (raw ASCII telnet-style)

Protocol: raw ASCII, ``{axis}{cmd}{param}\\r``, responses terminated ``\\r\\n``.
Polling ``{n}MD?`` is used for non-blocking motion wait (WS blocks the port).

Example usage::

    ctrl = NewportESP302(
        transport="serial",
        port="COM3",
        baudrate=19200,
        axis_configs=[{
            "name": "delay",
            "index": 1,
            "velocity": 20.0,
            "acceleration": 5.0,
            "position_min": 0.0,
            "position_max": 150.0,
        }],
    )
    ctrl.get_axis("delay").position = 50.0
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Dict, List, Optional

from andor_pymeasure.instruments.motion_controller import (
    SPEED_OF_LIGHT_MM_PS,
    Axis,
    MockAxis,
    MockMotionController,
    MotionController,
)

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


# ---------------------------------------------------------------------------
# Axis
# ---------------------------------------------------------------------------


class NewportESP302Axis(Axis):
    """Single axis on a Newport ESP302 controller.

    Adds ``t0_offset_mm`` so that ``position_ps`` reports delay relative
    to the optical t0 position, not the stage origin.

    Two velocity/acceleration profiles are supported:

    - **Initialization profile** (``init_velocity``, ``init_acceleration``):
      used during the startup sequence (motor on, set limits, homing).
      Typically faster so the stage reaches home quickly.
    - **Measurement profile** (``velocity``, ``acceleration``):
      set on the controller after startup and used for all subsequent moves
      during data acquisition. Typically slower for accurate positioning.
    """

    def __init__(
        self,
        index: int,
        controller: "NewportESP302",
        name: str = "",
        position_min: float = 0.0,
        position_max: float = 300.0,
        velocity: float = 0.5,
        acceleration: float = 50.0,
        init_velocity: float = 5.0,
        init_acceleration: float = 10.0,
        units: str = "mm",
    ):
        super().__init__(
            index=index,
            controller=controller,
            name=name,
            position_min=position_min,
            position_max=position_max,
            velocity=velocity,
            units=units,
        )
        self.acceleration = acceleration
        self.init_velocity = init_velocity
        self.init_acceleration = init_acceleration
        self.t0_offset_mm: float = 0.0

    # -- position_ps override to honour t0_offset_mm ----------------------

    @property
    def position_ps(self) -> float:
        """Get current position as optical delay in ps, relative to t0."""
        return (2 * (self.position - self.t0_offset_mm)) / SPEED_OF_LIGHT_MM_PS

    @position_ps.setter
    def position_ps(self, value: float) -> None:
        """Set position from optical delay in ps, relative to t0."""
        self.position = self.t0_offset_mm + (value * SPEED_OF_LIGHT_MM_PS) / 2

    # -- low-level helpers -------------------------------------------------

    def _send(self, cmd: str) -> None:
        self.controller._send(cmd)

    def _query(self, cmd: str) -> str:
        return self.controller._query(cmd)

    # -- Axis interface ----------------------------------------------------

    @property
    def position(self) -> float:
        """Get current position in mm from controller."""
        raw = self._query(f"{self.index}TP")
        return float(raw)

    @position.setter
    def position(self, value: float) -> None:
        """Move to absolute position in mm, blocking until done."""
        # Clamp to limits before sending
        value = max(self.position_min, min(value, self.position_max))
        self._send(f"{self.index}PA{value}")
        self.wait_for_stop()

    @property
    def is_moving(self) -> bool:
        """Check if axis is currently moving by polling MD?."""
        raw = self._query(f"{self.index}MD?")
        return raw.strip() != "1"

    def enable(self) -> None:
        """Enable axis motor (MO)."""
        self._send(f"{self.index}MO")
        self._enabled = True

    def disable(self) -> None:
        """Disable axis motor (MF — soft power off)."""
        self._send(f"{self.index}MF")
        self._enabled = False

    def home(self, home_type: int = 1) -> None:
        """Home axis: set home to 0 (SH0) then run home search (OR1)."""
        self._send(f"{self.index}SH0")
        self._send(f"{self.index}OR{home_type}")
        self.wait_for_stop()

    def move_fast(self, position_mm: float) -> None:
        """Move to absolute position using init_velocity/init_acceleration, then restore measurement profile."""
        n = self.index
        self._send(f"{n}VA{self.init_velocity}")
        self._send(f"{n}AC{self.init_acceleration}")
        value = max(self.position_min, min(position_mm, self.position_max))
        self._send(f"{n}PA{value}")
        self.wait_for_stop()
        self._send(f"{n}VA{self.velocity}")
        self._send(f"{n}AC{self.acceleration}")

    def stop(self) -> None:
        """Stop axis motion (ST — uses programmed deceleration)."""
        self._send(f"{self.index}ST")


# ---------------------------------------------------------------------------
# Controller — real hardware
# ---------------------------------------------------------------------------


class NewportESP302(MotionController):
    """Newport ESP302 motion controller (serial or socket transport).

    Args:
        transport: ``"serial"`` or ``"socket"``.
        port: COM port for serial transport (e.g. ``"COM3"``).
        baudrate: Baud rate for serial (default 19200).
        host: IP address for socket transport.
        tcp_port: TCP port for socket transport (default 5001).
        axis_configs: List of axis configuration dicts. Each dict may contain:
            ``name``, ``index``, ``position_min``, ``position_max``,
            ``velocity``, ``acceleration``, ``units``.
        name: Controller name.
        home_on_startup: Home all axes after initialization.
    """

    def __init__(
        self,
        transport: str = "socket",
        port: str = "COM3",
        baudrate: int = 19200,
        host: str = "",  # Configure in %APPDATA%/AndorSpectrometer/config.yaml
        tcp_port: int = 5001,
        axis_configs: Optional[List[Dict]] = None,
        name: str = "Newport ESP302",
        home_on_startup: bool = False,
        **kwargs,
    ):
        super().__init__(name=name, home_on_startup=home_on_startup)
        self._transport = transport
        self._conn_lock = threading.Lock()

        if transport == "serial":
            import serial

            self._conn = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                rtscts=True,
                timeout=2.0,
            )
        elif transport == "socket":
            self._conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._conn.connect((host, tcp_port))
            self._conn.settimeout(2.0)
            self._socket_buf = b""
        else:
            raise ValueError(f"Unknown transport: {transport!r}")

        configs = axis_configs or [{"name": "delay", "index": 2}]
        for cfg in configs:
            axis = NewportESP302Axis(
                index=cfg.get("index", 2),
                controller=self,
                name=cfg.get("name", f"axis{cfg.get('index', 2)}"),
                position_min=cfg.get("position_min", 0.0),
                position_max=cfg.get("position_max", 600.0),
                velocity=cfg.get("velocity", 0.5),
                acceleration=cfg.get("acceleration", 50.0),
                init_velocity=cfg.get("init_velocity", 5.0),
                init_acceleration=cfg.get("init_acceleration", 10.0),
                units=cfg.get("units", "mm"),
            )
            self._axes[axis.name] = axis
            self._startup_axis(axis)

        if home_on_startup:
            self.home_all()

    def _startup_axis(self, axis: NewportESP302Axis) -> None:
        """Send startup sequence for one axis.

        Uses the initialization velocity/acceleration profile during setup,
        then switches to the measurement profile for subsequent moves.
        """
        n = axis.index
        self._send(f"{n}MO")
        self._send(f"{n}SN2")  # mm units
        # Use initialization profile for startup (faster for homing etc.)
        self._send(f"{n}VA{axis.init_velocity}")
        self._send(f"{n}AC{axis.init_acceleration}")
        self._send(f"{n}SL{axis.position_min}")
        self._send(f"{n}SR{axis.position_max}")
        # Switch to measurement profile — used for all data acquisition moves
        self._send(f"{n}VA{axis.velocity}")
        self._send(f"{n}AC{axis.acceleration}")
        axis._enabled = True

    # -- transport I/O -----------------------------------------------------

    def _send(self, cmd: str) -> None:
        """Send a command (no response expected)."""
        data = f"{cmd}\r".encode()
        with self._conn_lock:
            if self._transport == "serial":
                self._conn.write(data)
            else:
                self._conn.sendall(data)

    def _query(self, cmd: str) -> str:
        """Send a command and return the response."""
        with self._conn_lock:
            data = f"{cmd}\r".encode()
            if self._transport == "serial":
                self._conn.write(data)
                return self._conn.readline().decode().strip()
            else:
                self._conn.sendall(data)
                return self._socket_readline()

    def _socket_readline(self) -> str:
        """Read until \\r\\n from socket buffer."""
        while b"\r\n" not in self._socket_buf:
            chunk = self._conn.recv(1024)
            self._socket_buf += chunk
        line, self._socket_buf = self._socket_buf.split(b"\r\n", 1)
        return line.decode().strip()

    # -- controller-level operations ---------------------------------------

    def emergency_stop(self) -> None:
        """Emergency stop all axes (AB command — no axis prefix)."""
        self._send("AB")

    def shutdown(self) -> None:
        """Disable all axes and close connection."""
        self.disable_all()
        try:
            self._conn.close()
        except Exception:
            pass
        log.info(f"{self._name}: Shutdown complete")


# ---------------------------------------------------------------------------
# Mock — for testing without hardware
# ---------------------------------------------------------------------------


class MockNewportESP302Axis(MockAxis):
    """Mock ESP302 axis that adds t0_offset_mm support."""

    def __init__(self, *args, **kwargs):
        acceleration = kwargs.pop("acceleration", 50.0)
        init_velocity = kwargs.pop("init_velocity", 5.0)
        init_acceleration = kwargs.pop("init_acceleration", 10.0)
        super().__init__(*args, **kwargs)
        self.acceleration = acceleration
        self.init_velocity = init_velocity
        self.init_acceleration = init_acceleration
        self.t0_offset_mm: float = 0.0

    @property
    def position_ps(self) -> float:
        """Get delay in ps relative to t0 offset."""
        return (2 * (self.position - self.t0_offset_mm)) / SPEED_OF_LIGHT_MM_PS

    @position_ps.setter
    def position_ps(self, value: float) -> None:
        self.position = self.t0_offset_mm + (value * SPEED_OF_LIGHT_MM_PS) / 2

    def move_fast(self, position_mm: float) -> None:
        """Mock fast move — same as regular position move (no velocity concept in mock)."""
        value = max(self.position_min, min(position_mm, self.position_max))
        self.position = value


class MockNewportESP302(MockMotionController):
    """Mock Newport ESP302 for testing without hardware.

    Behaves identically to ``MockMotionController`` but uses
    ``MockNewportESP302Axis`` which includes ``t0_offset_mm`` and the
    corrected ``position_ps`` property.
    """

    def __init__(
        self,
        axis_configs: Optional[List[Dict]] = None,
        name: str = "Mock Newport ESP302",
        home_on_startup: bool = False,
        **kwargs,
    ):
        # Bypass parent __init__ to use our axis type
        MotionController.__init__(self, name=name, home_on_startup=home_on_startup)

        configs = axis_configs or [{"name": "delay", "index": 2}]
        for cfg in configs:
            axis = MockNewportESP302Axis(
                index=cfg.get("index", 2),
                controller=self,
                name=cfg.get("name", f"axis{cfg.get('index', 2)}"),
                position_min=cfg.get("position_min", 0.0),
                position_max=cfg.get("position_max", 600.0),
                velocity=cfg.get("velocity", 1000.0),
                units=cfg.get("units", "mm"),
                acceleration=cfg.get("acceleration", 50.0),
                init_velocity=cfg.get("init_velocity", 5.0),
                init_acceleration=cfg.get("init_acceleration", 10.0),
            )
            self._axes[axis.name] = axis

        log.info(f"MockNewportESP302 initialized with axes: {list(self._axes.keys())}")

        if home_on_startup:
            self.home_all()

    def emergency_stop(self) -> None:
        """Stop all axes immediately."""
        for axis in self._axes.values():
            axis.stop()
        log.info(f"{self._name}: Emergency stop")
