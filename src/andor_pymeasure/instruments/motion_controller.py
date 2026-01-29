"""Multi-axis motion controller base classes and Mock implementation.

This module provides base classes for multi-axis motion controllers
following the PyMeasure Instrument pattern. Controllers manage multiple
axes, each of which can be positioned independently.

Conversion: delay_ps = (2 * position_mm) / (c * 1e-12)
where c = 299.792458 mm/ns (speed of light)
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Speed of light in mm/ps
SPEED_OF_LIGHT_MM_PS = 0.299792458  # mm/ps


@dataclass(frozen=True)
class AxisInfo:
    """Axis configuration and limits."""

    name: str = ""
    index: int = 1
    position_min: float = 0.0  # mm
    position_max: float = 300.0  # mm
    velocity: float = 10.0  # mm/s
    units: str = "mm"


class Axis(ABC):
    """Abstract base class for a single motion axis.

    This class provides the interface for controlling a single axis.
    Subclasses should implement the abstract methods for specific hardware.

    The axis position can be accessed/set in either mm or ps units.
    """

    def __init__(
        self,
        index: int,
        controller: "MotionController",
        name: str = "",
        position_min: float = 0.0,
        position_max: float = 300.0,
        velocity: float = 10.0,
        units: str = "mm",
    ):
        """Initialize axis.

        Args:
            index: Axis index on the controller (1-indexed typically).
            controller: Parent controller instance.
            name: Human-readable name for this axis.
            position_min: Minimum position in mm.
            position_max: Maximum position in mm.
            velocity: Movement velocity in mm/s.
            units: Default units for display ("mm", "ps", "fs", "um", "deg").
        """
        self.index = index
        self.controller = controller
        self.name = name or f"axis{index}"
        self.position_min = position_min
        self.position_max = position_max
        self.velocity = velocity
        self.units = units
        self._enabled = False
        self._lock = threading.Lock()

    @property
    @abstractmethod
    def position(self) -> float:
        """Get current position in mm."""
        pass

    @position.setter
    @abstractmethod
    def position(self, value: float) -> None:
        """Set position in mm (may block until motion complete)."""
        pass

    @property
    def position_ps(self) -> float:
        """Get current position as optical delay in picoseconds.

        Uses round-trip delay: light travels to mirror and back.
        """
        return (2 * self.position) / SPEED_OF_LIGHT_MM_PS

    @position_ps.setter
    def position_ps(self, value: float) -> None:
        """Set position as optical delay in picoseconds."""
        self.position = (value * SPEED_OF_LIGHT_MM_PS) / 2

    @property
    def delay_range_ps(self) -> tuple[float, float]:
        """Get delay range in ps."""
        min_ps = (2 * self.position_min) / SPEED_OF_LIGHT_MM_PS
        max_ps = (2 * self.position_max) / SPEED_OF_LIGHT_MM_PS
        return (min_ps, max_ps)

    @property
    @abstractmethod
    def is_moving(self) -> bool:
        """Check if axis is currently moving."""
        pass

    @property
    def motion_done(self) -> bool:
        """Check if motion is complete (inverse of is_moving)."""
        return not self.is_moving

    @property
    def enabled(self) -> bool:
        """Check if axis motor is enabled."""
        return self._enabled

    @abstractmethod
    def enable(self) -> None:
        """Enable the axis motor."""
        pass

    @abstractmethod
    def disable(self) -> None:
        """Disable the axis motor."""
        pass

    @abstractmethod
    def home(self, home_type: int = 1) -> None:
        """Start homing the axis.

        Args:
            home_type: Type of homing routine (controller-specific).
        """
        pass

    def wait_for_stop(self, delay: float = 0, interval: float = 0.05) -> None:
        """Wait for axis motion to complete.

        Args:
            delay: Initial delay before checking (seconds).
            interval: Polling interval (seconds).
        """
        if delay > 0:
            time.sleep(delay)

        while self.is_moving:
            time.sleep(interval)

    @abstractmethod
    def stop(self) -> None:
        """Stop any motion immediately."""
        pass

    def __repr__(self) -> str:
        return f"Axis({self.name}, index={self.index}, pos={self.position:.3f}mm)"


class MockAxis(Axis):
    """Mock axis implementation for testing without hardware.

    Simulates motion with configurable velocity and limits.
    """

    def __init__(
        self,
        index: int,
        controller: "MockMotionController",
        name: str = "",
        position_min: float = 0.0,
        position_max: float = 300.0,
        velocity: float = 1000.0,  # Fast for tests
        units: str = "mm",
    ):
        super().__init__(
            index, controller, name,
            position_min, position_max, velocity, units
        )
        self._position = 0.0
        self._moving = False
        self._target = 0.0
        self._enabled = True  # Mock starts enabled

    @property
    def position(self) -> float:
        """Get current position in mm."""
        return self._position

    @position.setter
    def position(self, value: float) -> None:
        """Set position in mm (simulates blocking move)."""
        # Clamp to limits
        value = max(self.position_min, min(value, self.position_max))

        with self._lock:
            self._target = value
            self._moving = True

        # Simulate movement time
        distance = abs(value - self._position)
        move_time = distance / self.velocity

        log.debug(
            f"MockAxis {self.name}: Moving to {value}mm "
            f"(distance: {distance:.2f}mm, time: {move_time:.4f}s)"
        )

        if move_time > 0:
            time.sleep(move_time)

        with self._lock:
            self._position = value
            self._moving = False

        log.debug(f"MockAxis {self.name}: Move complete, position = {self._position}mm")

    @property
    def is_moving(self) -> bool:
        """Check if axis is moving."""
        return self._moving

    def enable(self) -> None:
        """Enable the axis motor."""
        self._enabled = True
        log.debug(f"MockAxis {self.name}: Enabled")

    def disable(self) -> None:
        """Disable the axis motor."""
        self._enabled = False
        log.debug(f"MockAxis {self.name}: Disabled")

    def home(self, home_type: int = 1) -> None:
        """Home the axis (move to position 0)."""
        log.info(f"MockAxis {self.name}: Homing...")
        self.position = 0.0
        log.info(f"MockAxis {self.name}: Home complete")

    def stop(self) -> None:
        """Stop any motion."""
        with self._lock:
            self._moving = False
            self._target = self._position
        log.debug(f"MockAxis {self.name}: Stopped")


class MotionController(ABC):
    """Abstract base class for multi-axis motion controllers.

    This class provides the interface for controllers that manage
    multiple motion axes. Subclasses implement communication for
    specific hardware.
    """

    def __init__(
        self,
        name: str = "Motion Controller",
        home_on_startup: bool = False,
        **kwargs,
    ):
        """Initialize controller.

        Args:
            name: Controller name for identification.
            home_on_startup: Whether to home all axes on initialization.
            **kwargs: Additional controller-specific options.
        """
        self._name = name
        self.home_on_startup = home_on_startup
        self._axes: Dict[str, Axis] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        """Get controller name."""
        return self._name

    @property
    def axes(self) -> List[Axis]:
        """Get list of all axes."""
        return list(self._axes.values())

    def get_axis(self, name: str) -> Optional[Axis]:
        """Get axis by name.

        Args:
            name: Axis name.

        Returns:
            Axis instance or None if not found.
        """
        return self._axes.get(name)

    def __getattr__(self, name: str) -> Axis:
        """Access axis by name as attribute.

        Args:
            name: Axis name.

        Returns:
            Axis instance.

        Raises:
            AttributeError: If axis not found.
        """
        # Avoid infinite recursion for special attributes
        if name.startswith("_"):
            raise AttributeError(name)

        if name in self._axes:
            return self._axes[name]
        raise AttributeError(f"No axis named '{name}'")

    def home_all(self) -> None:
        """Home all axes."""
        log.info(f"{self._name}: Homing all axes...")
        for axis in self._axes.values():
            axis.home()
        log.info(f"{self._name}: All axes homed")

    def enable_all(self) -> None:
        """Enable all axes."""
        for axis in self._axes.values():
            axis.enable()
        log.debug(f"{self._name}: All axes enabled")

    def disable_all(self) -> None:
        """Disable all axes."""
        for axis in self._axes.values():
            axis.disable()
        log.debug(f"{self._name}: All axes disabled")

    def wait_for_all(self, interval: float = 0.05) -> None:
        """Wait for all axes to stop moving.

        Args:
            interval: Polling interval in seconds.
        """
        while any(axis.is_moving for axis in self._axes.values()):
            time.sleep(interval)

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown the controller and release resources."""
        pass

    def __repr__(self) -> str:
        axis_names = [a.name for a in self.axes]
        return f"{self.__class__.__name__}({self._name}, axes={axis_names})"


class MockMotionController(MotionController):
    """Mock controller for testing without hardware.

    Creates MockAxis instances based on configuration.
    """

    def __init__(
        self,
        axis_configs: Optional[List[Dict]] = None,
        name: str = "Mock Motion Controller",
        home_on_startup: bool = False,
        **kwargs,
    ):
        """Initialize mock controller.

        Args:
            axis_configs: List of axis configuration dicts. Each dict can have:
                - name: Axis name (required)
                - index: Axis index (required)
                - position_min: Minimum position in mm (default 0.0)
                - position_max: Maximum position in mm (default 300.0)
                - velocity: Movement velocity in mm/s (default 1000.0)
                - units: Default units (default "mm")
            name: Controller name.
            home_on_startup: Whether to home on startup.
            **kwargs: Additional options (ignored).
        """
        super().__init__(name=name, home_on_startup=home_on_startup, **kwargs)

        # Default to single "delay" axis if no config
        configs = axis_configs or [{"name": "delay", "index": 1}]

        for cfg in configs:
            axis = MockAxis(
                index=cfg.get("index", 1),
                controller=self,
                name=cfg.get("name", f"axis{cfg.get('index', 1)}"),
                position_min=cfg.get("position_min", 0.0),
                position_max=cfg.get("position_max", 300.0),
                velocity=cfg.get("velocity", 1000.0),
                units=cfg.get("units", "mm"),
            )
            self._axes[axis.name] = axis

        log.info(f"MockMotionController initialized with axes: {list(self._axes.keys())}")

        if home_on_startup:
            self.home_all()

    def shutdown(self) -> None:
        """Shutdown the mock controller."""
        self.disable_all()
        log.info(f"{self._name}: Shutdown complete")
