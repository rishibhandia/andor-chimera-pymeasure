"""Thorlabs K10CR2 Kinesis motorized rotation stage driver.

Requires the ``thorlabs-kinesis`` package (Windows only, wraps Kinesis DLLs).
If the library is not installed, ``ThorlabsK10CR2`` raises ``ImportError`` on
instantiation. Use ``MockThorlabsK10CR2`` for tests without hardware.

Position units: **degrees** (continuous rotation, 0–360°).
``position_ps`` raises ``NotImplementedError`` — rotation stage, no optical delay.

Example usage::

    ctrl = ThorlabsK10CR2(
        serial_number=55000001,
        axis_configs=[{"name": "waveplate", "index": 0}],
    )
    ctrl.get_axis("waveplate").position = 45.0
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from andor_pymeasure.instruments.motion_controller import (
    Axis,
    MockAxis,
    MockMotionController,
    MotionController,
)

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


# ---------------------------------------------------------------------------
# Axis — real hardware
# ---------------------------------------------------------------------------


class ThorlabsK10CR2Axis(Axis):
    """Single K10CR2 stage managed via Kinesis.

    ``position_ps`` raises ``NotImplementedError`` (rotation stage).
    """

    def __init__(
        self,
        index: int,
        controller: "ThorlabsK10CR2",
        name: str = "",
        position_min: float = 0.0,
        position_max: float = 360.0,
        velocity: float = 10.0,
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

    # -- position_ps override ----------------------------------------------

    @property
    def position_ps(self) -> float:
        raise NotImplementedError("position_ps is not defined for rotation stages")

    @position_ps.setter
    def position_ps(self, value: float) -> None:
        raise NotImplementedError("position_ps is not defined for rotation stages")

    # -- Axis interface ----------------------------------------------------

    @property
    def position(self) -> float:
        """Get current position in degrees from Kinesis."""
        return self.controller._device.GetPosition_DeviceUnit(self.index) / self.controller._device_units_per_degree

    @position.setter
    def position(self, value: float) -> None:
        """Move to absolute position in degrees (blocking)."""
        value = max(self.position_min, min(value, self.position_max))
        units = round(value * self.controller._device_units_per_degree)
        self.controller._device.MoveToPosition_DeviceUnit(self.index, units)
        self.wait_for_stop()

    @property
    def is_moving(self) -> bool:
        """Check if stage is currently moving."""
        return self.controller._device.IsMoving(self.index)

    def enable(self) -> None:
        """Enable the stage motor."""
        self.controller._device.EnableChannel(self.index)
        self._enabled = True

    def disable(self) -> None:
        """Disable the stage motor."""
        self.controller._device.DisableChannel(self.index)
        self._enabled = False

    def home(self, home_type: int = 1) -> None:
        """Home the stage (blocking)."""
        self.controller._device.Home(self.index)
        self.wait_for_stop()

    def stop(self) -> None:
        """Stop the stage."""
        self.controller._device.Stop(self.index)


# ---------------------------------------------------------------------------
# Controller — real hardware
# ---------------------------------------------------------------------------


class ThorlabsK10CR2(MotionController):
    """Thorlabs K10CR2 motorized rotation stage via Kinesis DLL.

    Args:
        serial_number: Device serial number (e.g. 55000001).
        axis_configs: List of axis config dicts (``name``, ``index``, limits).
        device_units_per_degree: Encoder counts per degree (default 136533).
        name: Controller name.
        home_on_startup: Home all axes after init.

    Raises:
        ImportError: If ``thorlabs-kinesis`` package is not installed.
    """

    def __init__(
        self,
        serial_number: int = 55000001,
        axis_configs: Optional[List[Dict]] = None,
        device_units_per_degree: float = 136533.0,
        name: str = "Thorlabs K10CR2",
        home_on_startup: bool = False,
        **kwargs,
    ):
        super().__init__(name=name, home_on_startup=home_on_startup)

        try:
            import thorlabs_kinesis.benchtop_stepper_motor as bsm
        except (ImportError, TypeError) as exc:
            raise ImportError(
                "thorlabs-kinesis package is required for ThorlabsK10CR2. "
                "Install it from the Thorlabs Kinesis SDK."
            ) from exc

        self._device = bsm.BenchtopStepperMotor(str(serial_number))
        self._device_units_per_degree = device_units_per_degree

        configs = axis_configs or [{"name": "waveplate", "index": 0}]
        for cfg in configs:
            axis = ThorlabsK10CR2Axis(
                index=cfg.get("index", 0),
                controller=self,
                name=cfg.get("name", f"axis{cfg.get('index', 0)}"),
                position_min=cfg.get("position_min", 0.0),
                position_max=cfg.get("position_max", 360.0),
                velocity=cfg.get("velocity", 10.0),
                units=cfg.get("units", "deg"),
            )
            self._axes[axis.name] = axis

        log.info(f"ThorlabsK10CR2 '{name}' connected, SN={serial_number}")

        if home_on_startup:
            self.home_all()

    def emergency_stop(self) -> None:
        """Stop all axes immediately."""
        for axis in self._axes.values():
            axis.stop()

    def shutdown(self) -> None:
        """Disconnect from Kinesis device."""
        self.disable_all()
        try:
            self._device.Disconnect()
        except Exception:
            pass
        log.info(f"{self._name}: Shutdown complete")


# ---------------------------------------------------------------------------
# Mock — for testing without hardware or Kinesis
# ---------------------------------------------------------------------------


class MockThorlabsK10CR2Axis(MockAxis):
    """Mock K10CR2 axis (degrees). position_ps raises NotImplementedError."""

    @property
    def position_ps(self) -> float:
        raise NotImplementedError("position_ps is not defined for rotation stages")

    @position_ps.setter
    def position_ps(self, value: float) -> None:
        raise NotImplementedError("position_ps is not defined for rotation stages")


class MockThorlabsK10CR2(MockMotionController):
    """Mock Thorlabs K10CR2 for testing without hardware or Kinesis DLLs.

    Uses ``MockThorlabsK10CR2Axis`` which raises ``NotImplementedError``
    for ``position_ps``.
    """

    def __init__(
        self,
        axis_configs: Optional[List[Dict]] = None,
        name: str = "Mock Thorlabs K10CR2",
        home_on_startup: bool = False,
        **kwargs,
    ):
        MotionController.__init__(self, name=name, home_on_startup=home_on_startup)

        configs = axis_configs or [{"name": "waveplate", "index": 0}]
        for cfg in configs:
            axis = MockThorlabsK10CR2Axis(
                index=cfg.get("index", 0),
                controller=self,
                name=cfg.get("name", f"axis{cfg.get('index', 0)}"),
                position_min=cfg.get("position_min", 0.0),
                position_max=cfg.get("position_max", 360.0),
                velocity=cfg.get("velocity", 1000.0),
                units=cfg.get("units", "deg"),
            )
            self._axes[axis.name] = axis

        log.info(f"MockThorlabsK10CR2 initialized with axes: {list(self._axes.keys())}")

        if home_on_startup:
            self.home_all()

    def emergency_stop(self) -> None:
        """Stop all axes immediately."""
        for axis in self._axes.values():
            axis.stop()
        log.info(f"{self._name}: Emergency stop")
