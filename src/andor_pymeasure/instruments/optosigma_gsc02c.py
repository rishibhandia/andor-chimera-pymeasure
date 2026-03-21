"""OptoSigma GSC-02C RS-232 rotation stage controller driver.

Protocol: RS-232, 9600 baud, 8N1, rtscts=True, CR+LF terminator (\\r\\n).
Motion commands (``A:``, ``M:``, ``J:``) must be followed by ``G:`` to execute.
While BUSY only ``L:``, ``Q:``, ``!:``, ``?:`` are accepted.

Position units are **degrees** in the Axis interface.
Internally, pulses are used (default 400 pulses/degree for OSMS-YAW half-step).

``position_ps`` raises ``NotImplementedError`` — rotation stages have no optical delay.

Example usage::

    ctrl = GSC02C(
        port="COM4",
        axis_configs=[{"name": "polarizer", "index": 1}],
    )
    ctrl.get_axis("polarizer").position = 45.0  # rotate to 45°
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional

from andor_pymeasure.instruments.motion_controller import (
    Axis,
    MockAxis,
    MockMotionController,
    MotionController,
)

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

#: Default pulses per degree for OSMS-YAW in half-step mode (0.0025°/pulse)
DEFAULT_PULSES_PER_DEGREE = 400


# ---------------------------------------------------------------------------
# Axis
# ---------------------------------------------------------------------------


class GSC02CAxis(Axis):
    """Single axis on an OptoSigma GSC-02C controller.

    Position is in **degrees**. Internally converted to pulses for commands.
    ``position_ps`` is not supported — raises ``NotImplementedError``.
    """

    def __init__(
        self,
        index: int,
        controller: "GSC02C",
        name: str = "",
        position_min: float = -360.0,
        position_max: float = 360.0,
        velocity: float = 5000.0,
        pulses_per_degree: float = DEFAULT_PULSES_PER_DEGREE,
        units: str = "deg",
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
        self.pulses_per_degree = pulses_per_degree

    # -- position_ps overrides ---------------------------------------------

    @property
    def position_ps(self) -> float:
        """Not supported for rotation stages."""
        raise NotImplementedError("position_ps is not defined for rotation stages")

    @position_ps.setter
    def position_ps(self, value: float) -> None:
        raise NotImplementedError("position_ps is not defined for rotation stages")

    # -- pulses helper -----------------------------------------------------

    @property
    def position_pulses(self) -> int:
        """Current position in pulses."""
        return round(self.position * self.pulses_per_degree)

    @position_pulses.setter
    def position_pulses(self, value: int) -> None:
        self.position = value / self.pulses_per_degree

    # -- Axis interface ----------------------------------------------------

    @property
    def position(self) -> float:
        """Get current position in degrees from controller."""
        raw = self.controller._query("Q:")
        parts = raw.split(",")
        pulse_str = parts[self.index - 1].strip()
        # Fixed-width format: sign + padded digits, e.g. "-        0" or "+    18000"
        pulses = int(pulse_str.replace(" ", ""))
        return pulses / self.pulses_per_degree

    @position.setter
    def position(self, value: float) -> None:
        """Move to absolute position in degrees, blocking until done."""
        value = max(self.position_min, min(value, self.position_max))
        pulses = round(abs(value) * self.pulses_per_degree)
        direction = "+" if value >= 0 else "-"
        self.controller._send(f"A:{self.index}{direction}P{pulses}")
        self.controller._send("G:")
        self.wait_for_stop()

    @property
    def is_moving(self) -> bool:
        """Poll !: for busy/ready status."""
        return self.controller._query("!:").strip() == "B"

    def enable(self) -> None:
        """Hold motor (re-energise after free)."""
        self.controller._send(f"C:{self.index}1")
        self._enabled = True

    def disable(self) -> None:
        """Free motor (de-energise, allows manual rotation)."""
        self.controller._send(f"C:{self.index}0")
        self._enabled = False

    def home(self, home_type: int = 1) -> None:
        """Home axis toward CW limit (H:n-), block until done."""
        self.controller._send(f"H:{self.index}-")
        self.wait_for_stop()

    def stop(self) -> None:
        """Decelerate and stop all axes (L:W)."""
        self.controller._send("L:W")


# ---------------------------------------------------------------------------
# Controller — real hardware
# ---------------------------------------------------------------------------


class GSC02C(MotionController):
    """OptoSigma GSC-02C two-axis controller (RS-232 serial).

    Args:
        port: COM port (e.g. ``"COM4"``).
        baudrate: Baud rate (default 9600, set by DIP switches on controller).
        axis_configs: List of axis configuration dicts. Each may contain:
            ``name``, ``index``, ``position_min``, ``position_max``,
            ``pulses_per_degree``, ``units``.
        name: Controller name.
        home_on_startup: Home all axes after initialization.
    """

    def __init__(
        self,
        port: str = "COM4",
        baudrate: int = 9600,
        axis_configs: Optional[List[Dict]] = None,
        name: str = "OptoSigma GSC-02C",
        home_on_startup: bool = False,
        **kwargs,
    ):
        super().__init__(name=name, home_on_startup=home_on_startup)

        import serial

        self._conn = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            rtscts=True,
            timeout=5.0,
        )
        self._conn_lock = threading.Lock()

        configs = axis_configs or [{"name": "axis1", "index": 1}]
        for cfg in configs:
            axis = GSC02CAxis(
                index=cfg.get("index", 1),
                controller=self,
                name=cfg.get("name", f"axis{cfg.get('index', 1)}"),
                position_min=cfg.get("position_min", -360.0),
                position_max=cfg.get("position_max", 360.0),
                velocity=cfg.get("velocity", 5000.0),
                pulses_per_degree=cfg.get("pulses_per_degree", DEFAULT_PULSES_PER_DEGREE),
                units=cfg.get("units", "deg"),
            )
            self._axes[axis.name] = axis

        log.info(f"GSC02C '{name}' connected on {port}")

        if home_on_startup:
            self.home_all()

    # -- transport I/O -----------------------------------------------------

    def _send(self, cmd: str) -> None:
        """Send a command (no response expected)."""
        with self._conn_lock:
            self._conn.write(f"{cmd}\r\n".encode("ascii"))

    def _query(self, cmd: str) -> str:
        """Send a command and return the response (stripped)."""
        with self._conn_lock:
            self._conn.write(f"{cmd}\r\n".encode("ascii"))
            return self._conn.readline().decode("ascii").strip()

    # -- controller-level operations ---------------------------------------

    def emergency_stop(self) -> None:
        """Immediate stop all axes (L:E — works during homing)."""
        self._send("L:E")

    def shutdown(self) -> None:
        """Close serial connection."""
        try:
            self._conn.close()
        except Exception:
            pass
        log.info(f"{self._name}: Shutdown complete")


# ---------------------------------------------------------------------------
# Mock — for testing without hardware
# ---------------------------------------------------------------------------


class MockGSC02CAxis(MockAxis):
    """Mock GSC-02C axis using degrees as position units.

    ``position_ps`` raises ``NotImplementedError``.
    """

    def __init__(self, *args, pulses_per_degree: float = DEFAULT_PULSES_PER_DEGREE, **kwargs):
        super().__init__(*args, **kwargs)
        self.pulses_per_degree = pulses_per_degree

    @property
    def position_ps(self) -> float:
        raise NotImplementedError("position_ps is not defined for rotation stages")

    @position_ps.setter
    def position_ps(self, value: float) -> None:
        raise NotImplementedError("position_ps is not defined for rotation stages")

    @property
    def position_pulses(self) -> int:
        """Current position in pulses."""
        return round(self.position * self.pulses_per_degree)

    @position_pulses.setter
    def position_pulses(self, value: int) -> None:
        self.position = value / self.pulses_per_degree


class MockGSC02C(MockMotionController):
    """Mock OptoSigma GSC-02C for testing without hardware.

    Uses ``MockGSC02CAxis`` which raises ``NotImplementedError`` for
    ``position_ps`` and provides ``position_pulses``.
    """

    def __init__(
        self,
        axis_configs: Optional[List[Dict]] = None,
        name: str = "Mock OptoSigma GSC-02C",
        home_on_startup: bool = False,
        **kwargs,
    ):
        MotionController.__init__(self, name=name, home_on_startup=home_on_startup)

        configs = axis_configs or [{"name": "axis1", "index": 1}]
        for cfg in configs:
            axis = MockGSC02CAxis(
                index=cfg.get("index", 1),
                controller=self,
                name=cfg.get("name", f"axis{cfg.get('index', 1)}"),
                position_min=cfg.get("position_min", -360.0),
                position_max=cfg.get("position_max", 360.0),
                velocity=cfg.get("velocity", 1000.0),
                units=cfg.get("units", "deg"),
                pulses_per_degree=cfg.get("pulses_per_degree", DEFAULT_PULSES_PER_DEGREE),
            )
            self._axes[axis.name] = axis

        log.info(f"MockGSC02C initialized with axes: {list(self._axes.keys())}")

        if home_on_startup:
            self.home_all()

    def emergency_stop(self) -> None:
        """Stop all axes immediately."""
        for axis in self._axes.values():
            axis.stop()
        log.info(f"{self._name}: Emergency stop")
