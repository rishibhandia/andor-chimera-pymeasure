"""Motion controller manager for coordinating multiple motion controllers.

This module provides the MotionControllerManager that creates and manages
motion controllers based on configuration. It supports multiple controller
types and provides unified access to all axes across controllers.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from andor_pymeasure.instruments.motion_controller import Axis, MotionController

log = logging.getLogger(__name__)

# Import controller classes
from andor_pymeasure.instruments.motion_controller import MockMotionController

# Controller type registry - maps type names to controller classes
CONTROLLER_TYPES: Dict[str, Type["MotionController"]] = {
    "mock": MockMotionController,
    # Future additions:
    # "newport_esp301": NewportESP301,
    # "sigmakoki_gsc01": SigmaKokiGSC01,
    # "sigmakoki_gsc02c": SigmaKokiGSC02C,
    # "thorlabs_kdc101": ThorlabsKDC101,
}


class MotionControllerManager:
    """Manages all motion controllers from configuration.

    Creates PyMeasure Instrument-style controller instances based on
    configuration. Provides unified access to all axes across controllers.

    Usage:
        config = {
            "enabled": True,
            "controllers": [
                {
                    "name": "delay_stage",
                    "type": "mock",
                    "home_on_startup": False,
                    "axes": [{"name": "delay", "index": 1}],
                }
            ],
        }
        manager = MotionControllerManager(config)
        manager.initialize()

        # Access axis
        axis = manager.get_axis("delay")
        axis.position_ps = 10.0
    """

    def __init__(self, config: dict):
        """Initialize the manager with configuration.

        Args:
            config: Motion controller configuration dict. Expected format:
                {
                    "enabled": True,
                    "controllers": [
                        {
                            "name": "controller_name",
                            "type": "mock",
                            "home_on_startup": False,
                            "axes": [{"name": "axis_name", "index": 1, ...}],
                            "connection": {...},  # type-specific connection params
                        },
                        ...
                    ],
                }
        """
        self._config = config
        self._controllers: Dict[str, "MotionController"] = {}
        self._initialized = False

    @property
    def enabled(self) -> bool:
        """Check if motion controllers are enabled."""
        return self._config.get("enabled", True)

    @property
    def controllers(self) -> Dict[str, "MotionController"]:
        """Get all controllers by name."""
        return self._controllers

    @property
    def all_axes(self) -> Dict[str, "Axis"]:
        """Get all axes from all controllers.

        Returns:
            Dict mapping axis name to Axis instance.
        """
        axes = {}
        for ctrl in self._controllers.values():
            for axis in ctrl.axes:
                axes[axis.name] = axis
        return axes

    def initialize(self) -> None:
        """Create and initialize all controllers from config.

        Creates controller instances based on config. Controllers with
        home_on_startup=True will be homed after creation.
        """
        if self._initialized:
            log.warning("MotionControllerManager already initialized")
            return

        if not self.enabled:
            log.info("Motion controllers disabled in config")
            self._initialized = True
            return

        for ctrl_config in self._config.get("controllers", []):
            ctrl_type = ctrl_config.get("type", "mock")
            ctrl_name = ctrl_config.get("name", f"controller_{len(self._controllers)}")

            # Get controller class from registry
            ctrl_class = CONTROLLER_TYPES.get(ctrl_type)
            if not ctrl_class:
                log.warning(f"Unknown controller type: {ctrl_type}, skipping {ctrl_name}")
                continue

            try:
                # Extract axis configs
                axis_configs = ctrl_config.get("axes", [])

                # Extract connection params if present
                connection_params = ctrl_config.get("connection", {})

                # Create controller
                controller = ctrl_class(
                    axis_configs=axis_configs,
                    name=ctrl_name,
                    home_on_startup=ctrl_config.get("home_on_startup", False),
                    **connection_params,
                )

                self._controllers[ctrl_name] = controller
                log.info(
                    f"Created {ctrl_type} controller '{ctrl_name}' "
                    f"with axes: {[a.name for a in controller.axes]}"
                )

            except Exception as e:
                log.error(f"Failed to create controller '{ctrl_name}': {e}")

        self._initialized = True
        log.info(f"MotionControllerManager initialized with {len(self._controllers)} controllers")

    def get_axis(self, name: str) -> Optional["Axis"]:
        """Get axis by name across all controllers.

        Args:
            name: Axis name to find.

        Returns:
            Axis instance or None if not found.
        """
        for ctrl in self._controllers.values():
            axis = ctrl.get_axis(name)
            if axis is not None:
                return axis
        return None

    def get_controller(self, name: str) -> Optional["MotionController"]:
        """Get controller by name.

        Args:
            name: Controller name.

        Returns:
            Controller instance or None if not found.
        """
        return self._controllers.get(name)

    def home_all(self) -> None:
        """Home all axes on all controllers."""
        log.info("Homing all motion axes...")
        for ctrl in self._controllers.values():
            ctrl.home_all()
        log.info("All motion axes homed")

    def shutdown(self) -> None:
        """Shutdown all controllers."""
        log.info("Shutting down motion controllers...")
        for name, ctrl in self._controllers.items():
            try:
                ctrl.shutdown()
                log.debug(f"Controller '{name}' shut down")
            except Exception as e:
                log.error(f"Error shutting down controller '{name}': {e}")
        log.info("Motion controllers shutdown complete")
