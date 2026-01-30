"""PyMeasure instrument wrapper for Andor SDK2 camera.

This module wraps the pyAndorSDK2 library for use with PyMeasure procedures.

Hardware Safety Rules:
- ALWAYS call CoolerON() before acquisition for optimal noise
- ALWAYS warm up camera (temp > -20C) before shutdown
- NEVER call Initialize() if already initialized
- Use locks for thread safety during SDK calls
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


@dataclass(frozen=True)
class CameraInfo:
    """Immutable camera information."""

    serial_number: str = ""
    model: str = ""
    xpixels: int = 0
    ypixels: int = 0
    pixel_width: float = 0.0
    pixel_height: float = 0.0
    em_gain_range: Tuple[int, int] = (0, 0)


class AndorCamera:
    """PyMeasure instrument wrapper for Andor SDK2 camera.

    This class provides a simplified interface to the Andor camera for use
    in PyMeasure procedures. It handles initialization, acquisition, and
    shutdown with proper safety checks.

    Example:
        camera = AndorCamera()
        camera.initialize()
        camera.set_exposure(0.1)
        camera.cooler_on(target=-60)
        data = camera.acquire_fvb()
        camera.shutdown()
    """

    def __init__(self, sdk_path: str = r"C:\Program Files\Andor SDK"):
        """Initialize the camera wrapper.

        Args:
            sdk_path: Path to the Andor SDK installation directory.
        """
        self._sdk_path = sdk_path
        self._sdk = None
        self._codes = None
        self._errors = None
        self._initialized = False
        self._lock = threading.Lock()
        self._info: Optional[CameraInfo] = None
        self._cooler_on = False

    @property
    def info(self) -> Optional[CameraInfo]:
        """Get camera information (available after initialization)."""
        return self._info

    @property
    def xpixels(self) -> int:
        """Get horizontal pixel count."""
        return self._info.xpixels if self._info else 0

    @property
    def ypixels(self) -> int:
        """Get vertical pixel count."""
        return self._info.ypixels if self._info else 0

    @property
    def temperature(self) -> float:
        """Get current temperature in Celsius."""
        if not self._initialized:
            return 20.0

        with self._lock:
            ret, temp = self._sdk.GetTemperature()
            return float(temp)

    @property
    def temperature_status(self) -> str:
        """Get temperature status string."""
        if not self._initialized:
            return "NOT_INITIALIZED"

        with self._lock:
            ret, _ = self._sdk.GetTemperature()
            status_map = {
                self._errors.Error_Codes.DRV_TEMPERATURE_STABILIZED: "STABILIZED",
                self._errors.Error_Codes.DRV_TEMPERATURE_NOT_REACHED: "NOT_REACHED",
                self._errors.Error_Codes.DRV_TEMPERATURE_DRIFT: "DRIFTING",
                self._errors.Error_Codes.DRV_TEMPERATURE_NOT_STABILIZED: "NOT_STABILIZED",
                self._errors.Error_Codes.DRV_TEMPERATURE_OFF: "OFF",
            }
            return status_map.get(ret, "UNKNOWN")

    def initialize(self) -> None:
        """Initialize the camera SDK.

        Raises:
            RuntimeError: If initialization fails.
        """
        if self._initialized:
            log.warning("Camera already initialized")
            return

        try:
            from pyAndorSDK2 import atmcd, atmcd_codes, atmcd_errors

            self._sdk = atmcd(self._sdk_path)
            self._codes = atmcd_codes
            self._errors = atmcd_errors

            ret = self._sdk.Initialize("")
            if ret != self._errors.Error_Codes.DRV_SUCCESS:
                raise RuntimeError(f"Camera initialization failed with code: {ret}")

            self._initialized = True

            # Get camera info
            ret, serial = self._sdk.GetCameraSerialNumber()
            ret, xpixels, ypixels = self._sdk.GetDetector()
            ret, xsize, ysize = self._sdk.GetPixelSize()
            ret, em_low, em_high = self._sdk.GetEMGainRange()

            self._info = CameraInfo(
                serial_number=str(serial),
                model="Andor Camera",
                xpixels=xpixels,
                ypixels=ypixels,
                pixel_width=xsize,
                pixel_height=ysize,
                em_gain_range=(em_low, em_high),
            )

            # Set default modes
            self._sdk.SetAcquisitionMode(self._codes.Acquisition_Mode.SINGLE_SCAN)
            self._sdk.SetReadMode(self._codes.Read_Mode.FULL_VERTICAL_BINNING)
            self._sdk.SetTriggerMode(self._codes.Trigger_Mode.INTERNAL)

            log.info(
                f"Camera initialized: serial={serial}, detector={xpixels}x{ypixels}"
            )

        except ImportError as e:
            raise RuntimeError(f"pyAndorSDK2 not installed: {e}")

    def set_exposure(self, exposure_time: float) -> None:
        """Set exposure time in seconds.

        Args:
            exposure_time: Exposure time in seconds.

        Raises:
            RuntimeError: If camera not initialized.
        """
        if not self._initialized:
            raise RuntimeError("Camera not initialized")

        with self._lock:
            self._sdk.SetExposureTime(exposure_time)
            log.debug(f"Exposure time set to {exposure_time}s")

    def cooler_on(self, target: int = -60) -> None:
        """Turn on the cooler with target temperature.

        Args:
            target: Target temperature in Celsius (default -60C).

        Raises:
            RuntimeError: If camera not initialized.
        """
        if not self._initialized:
            raise RuntimeError("Camera not initialized")

        with self._lock:
            self._sdk.SetTemperature(target)
            self._sdk.CoolerON()
            self._cooler_on = True
            log.info(f"Cooler ON, target temperature: {target}C")

    def cooler_off(self) -> None:
        """Turn off the cooler.

        Raises:
            RuntimeError: If camera not initialized.
        """
        if not self._initialized:
            raise RuntimeError("Camera not initialized")

        with self._lock:
            self._sdk.CoolerOFF()
            self._cooler_on = False
            log.info("Cooler OFF")

    def acquire_fvb(self, hbin: int = 1) -> np.ndarray:
        """Acquire single FVB (Full Vertical Binning) spectrum.

        Args:
            hbin: Horizontal binning factor. Must be a factor of xpixels.

        Returns:
            1D numpy array of intensities.

        Raises:
            RuntimeError: If acquisition fails.
            ValueError: If hbin is invalid.
        """
        if not self._initialized:
            raise RuntimeError("Camera not initialized")

        xpixels = self._info.xpixels

        if hbin < 1:
            raise ValueError(f"hbin must be >= 1, got {hbin}")
        if xpixels % hbin != 0:
            raise ValueError(f"hbin={hbin} must be a factor of {xpixels}")

        eff_pixels = xpixels // hbin

        with self._lock:
            # Set FVB mode
            self._sdk.SetReadMode(self._codes.Read_Mode.FULL_VERTICAL_BINNING)
            self._sdk.SetAcquisitionMode(self._codes.Acquisition_Mode.SINGLE_SCAN)

            # IMPORTANT: Use SetFVBHBin for horizontal binning in FVB mode.
            # SetImage is IGNORED in FVB mode!
            if hbin > 1:
                ret = self._sdk.SetFVBHBin(hbin)
                if ret != self._errors.Error_Codes.DRV_SUCCESS:
                    log.error(f"SetFVBHBin({hbin}) failed: {ret}")
                    raise RuntimeError(f"SetFVBHBin failed with code {ret}")
                log.debug(f"FVB mode: {eff_pixels} pixels (hbin={hbin})")
            else:
                # Reset to no binning
                ret = self._sdk.SetFVBHBin(1)
                if ret != self._errors.Error_Codes.DRV_SUCCESS:
                    log.warning(f"SetFVBHBin(1) returned: {ret}")

            # Prepare and start
            ret = self._sdk.PrepareAcquisition()
            if ret != self._errors.Error_Codes.DRV_SUCCESS:
                log.warning(f"PrepareAcquisition returned: {ret}")

            ret = self._sdk.StartAcquisition()
            if ret != self._errors.Error_Codes.DRV_SUCCESS:
                raise RuntimeError(f"StartAcquisition failed with code: {ret}")

        # Wait for acquisition (outside lock so abort can work)
        ret = self._sdk.WaitForAcquisition()
        if ret != self._errors.Error_Codes.DRV_SUCCESS:
            with self._lock:
                self._sdk.AbortAcquisition()
            raise RuntimeError(f"WaitForAcquisition failed with code: {ret}")

        # Get data - use effective pixels based on binning
        with self._lock:
            ret, arr, validfirst, validlast = self._sdk.GetImages16(
                1, 1, eff_pixels
            )
            if ret != self._errors.Error_Codes.DRV_SUCCESS:
                raise RuntimeError(f"GetImages16 failed with code: {ret}")

        data = np.array(arr, dtype=np.float64)
        log.debug(f"FVB acquisition complete: {len(data)} pixels (hbin={hbin})")
        return data

    def acquire_image(self, hbin: int = 1, vbin: int = 1) -> np.ndarray:
        """Acquire 2D image with optional binning.

        Args:
            hbin: Horizontal binning factor.
            vbin: Vertical binning factor.

        Returns:
            2D numpy array of intensities (rows=y, cols=x).

        Raises:
            RuntimeError: If acquisition fails.
        """
        if not self._initialized:
            raise RuntimeError("Camera not initialized")

        xpixels = self._info.xpixels
        ypixels = self._info.ypixels

        if xpixels % hbin != 0:
            raise ValueError(f"hbin={hbin} must be a factor of {xpixels}")
        if ypixels % vbin != 0:
            raise ValueError(f"vbin={vbin} must be a factor of {ypixels}")

        eff_x = xpixels // hbin
        eff_y = ypixels // vbin
        image_size = eff_x * eff_y

        with self._lock:
            # Set image mode
            self._sdk.SetReadMode(self._codes.Read_Mode.IMAGE)
            self._sdk.SetImage(hbin, vbin, 1, xpixels, 1, ypixels)
            self._sdk.SetAcquisitionMode(self._codes.Acquisition_Mode.SINGLE_SCAN)

            # Prepare and start
            ret = self._sdk.PrepareAcquisition()
            ret = self._sdk.StartAcquisition()
            if ret != self._errors.Error_Codes.DRV_SUCCESS:
                raise RuntimeError(f"StartAcquisition failed with code: {ret}")

        # Wait for acquisition
        ret = self._sdk.WaitForAcquisition()
        if ret != self._errors.Error_Codes.DRV_SUCCESS:
            with self._lock:
                self._sdk.AbortAcquisition()
            raise RuntimeError(f"WaitForAcquisition failed with code: {ret}")

        # Get data
        with self._lock:
            ret, arr, validfirst, validlast = self._sdk.GetImages16(1, 1, image_size)
            if ret != self._errors.Error_Codes.DRV_SUCCESS:
                raise RuntimeError(f"GetImages16 failed with code: {ret}")

        data = np.array(arr, dtype=np.float64).reshape(eff_y, eff_x)
        log.debug(f"Image acquisition complete: {eff_y}x{eff_x}")
        return data

    def abort_acquisition(self) -> None:
        """Abort any running acquisition."""
        if not self._initialized:
            return

        with self._lock:
            self._sdk.AbortAcquisition()
            log.info("Acquisition aborted")

    def warmup(self, target: float = -20.0, timeout: float = 300.0) -> bool:
        """Warm up camera to safe shutdown temperature.

        Args:
            target: Target temperature in Celsius (default -20C).
            timeout: Maximum wait time in seconds (default 300s).

        Returns:
            True if target reached, False if timed out.
        """
        if not self._initialized:
            return True

        # Turn off cooler first
        if self._cooler_on:
            self.cooler_off()

        start = time.time()
        while (time.time() - start) < timeout:
            temp = self.temperature
            log.info(f"Warming up: {temp:.1f}C (target: {target}C)")

            if temp >= target:
                log.info("Warmup complete")
                return True

            time.sleep(5)

        log.warning(f"Warmup timed out after {timeout}s")
        return False

    def shutdown(self) -> None:
        """Shutdown camera SDK.

        IMPORTANT: This method will warm up the camera if temperature is below -20C.
        """
        if not self._initialized:
            return

        try:
            # Safety: warm up before shutdown if cold
            temp = self.temperature
            if temp < -20:
                log.warning(f"Camera is cold ({temp}C). Warming up before shutdown...")
                self.warmup(target=-20, timeout=300)

            with self._lock:
                self._sdk.ShutDown()
                self._initialized = False
                log.info("Camera SDK shutdown complete")

        except Exception as e:
            log.error(f"Error during camera shutdown: {e}")
            # Still try to shutdown even if warmup failed
            try:
                with self._lock:
                    self._sdk.ShutDown()
                    self._initialized = False
            except Exception:
                pass
            raise
