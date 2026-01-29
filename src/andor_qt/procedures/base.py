"""Base procedure with shared hardware support.

This module provides a mixin for PyMeasure procedures that can use
shared hardware instances from the HardwareManager.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from andor_pymeasure.instruments.andor_camera import AndorCamera
    from andor_pymeasure.instruments.andor_spectrograph import AndorSpectrograph
    from andor_qt.core.motion_manager import MotionControllerManager

log = logging.getLogger(__name__)


class SharedHardwareMixin:
    """Mixin providing shared hardware support for procedures.

    Procedures using this mixin will check for injected hardware references
    before creating their own instances. This allows the GUI to share
    hardware with procedures without reinitializing.

    Usage:
        class MyProcedure(SharedHardwareMixin, Procedure):
            ...

        # Inject shared hardware
        from andor_qt.core import HardwareManager
        HardwareManager.instance().inject_into_procedure(MyProcedure)
    """

    # Class-level shared hardware references (set by HardwareManager.inject_into_procedure)
    _shared_camera: Optional["AndorCamera"] = None
    _shared_spectrograph: Optional["AndorSpectrograph"] = None
    _shared_motion_manager: Optional["MotionControllerManager"] = None

    def _init_hardware(self) -> None:
        """Initialize hardware, using shared instances if available.

        This method should be called in startup() instead of directly
        creating camera/spectrograph instances.

        Sets:
            self.camera: Camera instance (shared or new)
            self.spectrograph: Spectrograph instance (shared or new)
            self._owns_camera: True if this procedure created the camera
            self._owns_spectrograph: True if this procedure created the spectrograph
        """
        # Camera
        if self._shared_camera is not None:
            log.info("Using shared camera instance")
            self.camera = self._shared_camera
            self._owns_camera = False
        else:
            log.info("Creating new camera instance")
            from andor_pymeasure.instruments.andor_camera import AndorCamera

            self.camera = AndorCamera()
            self.camera.initialize()
            self._owns_camera = True

        # Spectrograph
        if self._shared_spectrograph is not None:
            log.info("Using shared spectrograph instance")
            self.spectrograph = self._shared_spectrograph
            self._owns_spectrograph = False
        else:
            log.info("Creating new spectrograph instance")
            from andor_pymeasure.instruments.andor_spectrograph import AndorSpectrograph

            self.spectrograph = AndorSpectrograph()
            self.spectrograph.initialize()
            self._owns_spectrograph = True

        # Motion manager (always shared, never owned by procedure)
        if self._shared_motion_manager is not None:
            log.info("Using shared motion manager")
            self.motion_manager = self._shared_motion_manager
        else:
            log.info("No shared motion manager available")
            self.motion_manager = None

    def _cleanup_hardware(self) -> None:
        """Cleanup hardware, only shutting down owned instances.

        This method should be called in shutdown() instead of directly
        calling shutdown on camera/spectrograph.
        """
        if hasattr(self, "_owns_camera") and self._owns_camera:
            if hasattr(self, "camera") and self.camera:
                log.info("Shutting down owned camera instance")
                self.camera.shutdown()
        else:
            log.info("Skipping camera shutdown (shared instance)")

        if hasattr(self, "_owns_spectrograph") and self._owns_spectrograph:
            if hasattr(self, "spectrograph") and self.spectrograph:
                log.info("Shutting down owned spectrograph instance")
                self.spectrograph.shutdown()
        else:
            log.info("Skipping spectrograph shutdown (shared instance)")
