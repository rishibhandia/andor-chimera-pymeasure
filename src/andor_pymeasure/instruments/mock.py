"""Mock SDK implementations for testing PyMeasure instruments.

This module provides mock implementations of pyAndorSDK2 and pyAndorSpectrograph
that can be used for testing without real hardware.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from unittest.mock import MagicMock

import numpy as np


# SDK return codes
DRV_SUCCESS = 20002
DRV_TEMPERATURE_STABILIZED = 20036
DRV_TEMPERATURE_NOT_REACHED = 20037
DRV_TEMPERATURE_NOT_STABILIZED = 20035
DRV_TEMPERATURE_OFF = 20034
DRV_TEMPERATURE_DRIFT = 20038
DRV_ACQUIRING = 20072

ATSPECTROGRAPH_SUCCESS = 0


@dataclass
class MockCameraState:
    """Mock camera internal state."""

    initialized: bool = False
    xpixels: int = 1024
    ypixels: int = 256
    pixel_width: float = 26.0
    pixel_height: float = 26.0
    serial_number: int = 12345
    temperature: float = 20.0
    target_temperature: int = -60
    cooler_on: bool = False
    exposure_time: float = 0.1
    read_mode: int = 0  # 0=FVB, 4=Image
    acquisition_mode: int = 1  # 1=Single scan
    hbin: int = 1
    vbin: int = 1
    acquiring: bool = False


@dataclass
class MockSpectrographState:
    """Mock spectrograph internal state."""

    initialized: bool = False
    num_devices: int = 1
    serial_number: str = "SPC-001"
    num_gratings: int = 2
    current_grating: int = 1
    current_wavelength: float = 500.0
    num_pixels: int = 1024
    pixel_width: float = 26.0
    gratings: List[dict] = field(default_factory=lambda: [
        {"lines": 150.0, "blaze": "500nm", "wl_min": 200.0, "wl_max": 1100.0},
        {"lines": 600.0, "blaze": "500nm", "wl_min": 300.0, "wl_max": 800.0},
    ])


class MockAtmcdErrors:
    """Mock atmcd_errors module."""

    class Error_Codes:
        DRV_SUCCESS = DRV_SUCCESS
        DRV_TEMPERATURE_STABILIZED = DRV_TEMPERATURE_STABILIZED
        DRV_TEMPERATURE_NOT_REACHED = DRV_TEMPERATURE_NOT_REACHED
        DRV_TEMPERATURE_NOT_STABILIZED = DRV_TEMPERATURE_NOT_STABILIZED
        DRV_TEMPERATURE_OFF = DRV_TEMPERATURE_OFF
        DRV_TEMPERATURE_DRIFT = DRV_TEMPERATURE_DRIFT
        DRV_ACQUIRING = DRV_ACQUIRING


class MockAtmcdCodes:
    """Mock atmcd_codes module."""

    class Acquisition_Mode:
        SINGLE_SCAN = 1
        ACCUMULATE = 2
        KINETICS = 3
        FAST_KINETICS = 4
        RUN_TILL_ABORT = 5

    class Read_Mode:
        FULL_VERTICAL_BINNING = 0
        MULTI_TRACK = 1
        RANDOM_TRACK = 2
        SINGLE_TRACK = 3
        IMAGE = 4

    class Trigger_Mode:
        INTERNAL = 0
        EXTERNAL = 1


class MockAtmcd:
    """Mock atmcd SDK for camera control.

    This class simulates the Andor SDK2 camera interface for testing.
    """

    def __init__(self, sdk_path: str = ""):
        import threading
        self._state = MockCameraState()
        self._sdk_path = sdk_path
        self._last_temp_check = time.time()
        self._lock = threading.Lock()

    def Initialize(self, path: str) -> int:
        """Initialize the camera SDK."""
        self._state.initialized = True
        return DRV_SUCCESS

    def ShutDown(self) -> int:
        """Shutdown the camera SDK."""
        self._state.initialized = False
        return DRV_SUCCESS

    def GetCameraSerialNumber(self) -> Tuple[int, int]:
        """Get camera serial number."""
        return (DRV_SUCCESS, self._state.serial_number)

    def GetDetector(self) -> Tuple[int, int, int]:
        """Get detector dimensions."""
        return (DRV_SUCCESS, self._state.xpixels, self._state.ypixels)

    def GetPixelSize(self) -> Tuple[int, float, float]:
        """Get pixel dimensions in micrometers."""
        return (DRV_SUCCESS, self._state.pixel_width, self._state.pixel_height)

    def GetEMGainRange(self) -> Tuple[int, int, int]:
        """Get EM gain range."""
        return (DRV_SUCCESS, 0, 1000)

    def GetTemperature(self) -> Tuple[int, float]:
        """Get current temperature with simulated cooling/warming."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_temp_check
            self._last_temp_check = now

            # Simulate temperature change (5°C per second cooling, 2°C per second warming)
            if self._state.cooler_on:
                if self._state.temperature > self._state.target_temperature:
                    # Cooling
                    self._state.temperature -= min(5.0 * elapsed, self._state.temperature - self._state.target_temperature)
            else:
                if self._state.temperature < 20.0:
                    # Warming towards room temp
                    self._state.temperature += min(2.0 * elapsed, 20.0 - self._state.temperature)

            # Determine status
            if not self._state.cooler_on:
                return (DRV_TEMPERATURE_OFF, self._state.temperature)
            elif abs(self._state.temperature - self._state.target_temperature) < 1.0:
                return (DRV_TEMPERATURE_STABILIZED, self._state.temperature)
            else:
                return (DRV_TEMPERATURE_NOT_REACHED, self._state.temperature)

    def SetTemperature(self, target: int) -> int:
        """Set target temperature."""
        self._state.target_temperature = target
        return DRV_SUCCESS

    def CoolerON(self) -> int:
        """Turn cooler on."""
        self._state.cooler_on = True
        return DRV_SUCCESS

    def CoolerOFF(self) -> int:
        """Turn cooler off."""
        self._state.cooler_on = False
        return DRV_SUCCESS

    def SetExposureTime(self, exposure: float) -> int:
        """Set exposure time in seconds."""
        self._state.exposure_time = exposure
        return DRV_SUCCESS

    def SetAcquisitionMode(self, mode: int) -> int:
        """Set acquisition mode."""
        self._state.acquisition_mode = mode
        return DRV_SUCCESS

    def SetReadMode(self, mode: int) -> int:
        """Set read mode."""
        self._state.read_mode = mode
        return DRV_SUCCESS

    def SetTriggerMode(self, mode: int) -> int:
        """Set trigger mode."""
        return DRV_SUCCESS

    def SetImage(
        self, hbin: int, vbin: int, hstart: int, hend: int, vstart: int, vend: int
    ) -> int:
        """Set image parameters."""
        self._state.hbin = hbin
        self._state.vbin = vbin
        return DRV_SUCCESS

    def PrepareAcquisition(self) -> int:
        """Prepare for acquisition."""
        return DRV_SUCCESS

    def StartAcquisition(self) -> int:
        """Start acquisition."""
        self._state.acquiring = True
        return DRV_SUCCESS

    def AbortAcquisition(self) -> int:
        """Abort acquisition."""
        self._state.acquiring = False
        return DRV_SUCCESS

    def WaitForAcquisition(self) -> int:
        """Wait for acquisition to complete."""
        # Simulate exposure time
        time.sleep(min(self._state.exposure_time, 0.1))  # Cap at 0.1s for tests
        self._state.acquiring = False
        return DRV_SUCCESS

    def GetImages16(
        self, first: int, last: int, size: int
    ) -> Tuple[int, List[int], int, int]:
        """Get acquired image data as 16-bit."""
        # Generate mock data
        np.random.seed(42)  # Reproducible for tests

        if self._state.read_mode == 0:  # FVB
            data = self._generate_mock_spectrum(self._state.xpixels)
        else:  # Image
            eff_x = self._state.xpixels // self._state.hbin
            eff_y = self._state.ypixels // self._state.vbin
            data = self._generate_mock_image(eff_x, eff_y).flatten()

        return (DRV_SUCCESS, data.tolist(), 1, 1)

    def _generate_mock_spectrum(self, xpixels: int) -> np.ndarray:
        """Generate mock 1D spectrum with Gaussian peaks."""
        x = np.arange(xpixels)
        spectrum = np.zeros(xpixels)

        # Add Gaussian peaks at fixed positions
        for center, width, height in [(256, 30, 10000), (512, 40, 15000), (768, 25, 8000)]:
            spectrum += height * np.exp(-0.5 * ((x - center) / width) ** 2)

        # Add noise
        spectrum += np.random.normal(100, 20, xpixels)
        return np.maximum(spectrum, 0).astype(np.int32)

    def _generate_mock_image(self, xpixels: int, ypixels: int) -> np.ndarray:
        """Generate mock 2D image."""
        y = np.arange(ypixels)
        x = np.arange(xpixels)
        Y, X = np.meshgrid(y, x, indexing='ij')

        # Create image with Gaussian blob
        cx, cy = xpixels // 2, ypixels // 2
        sigma = min(xpixels, ypixels) // 4
        image = 10000 * np.exp(-((X - cx)**2 + (Y - cy)**2) / (2 * sigma**2))

        # Add noise
        image += np.random.normal(100, 20, image.shape)
        return np.maximum(image, 0).astype(np.int32)


class MockATSpectrograph:
    """Mock ATSpectrograph SDK for spectrograph control.

    This class simulates the Andor Spectrograph SDK for testing.
    """

    ATSPECTROGRAPH_SUCCESS = ATSPECTROGRAPH_SUCCESS

    def __init__(self, dll_path: str = ""):
        self._state = MockSpectrographState()
        self._dll_path = dll_path

    def Initialize(self, path: str) -> int:
        """Initialize the spectrograph SDK."""
        self._state.initialized = True
        return ATSPECTROGRAPH_SUCCESS

    def Close(self) -> int:
        """Close the spectrograph SDK."""
        self._state.initialized = False
        return ATSPECTROGRAPH_SUCCESS

    def GetNumberDevices(self) -> Tuple[int, int]:
        """Get number of connected spectrographs."""
        return (ATSPECTROGRAPH_SUCCESS, self._state.num_devices)

    def GetSerialNumber(self, device: int, buf_len: int) -> Tuple[int, str]:
        """Get spectrograph serial number."""
        return (ATSPECTROGRAPH_SUCCESS, self._state.serial_number)

    def GetFunctionReturnDescription(
        self, ret_code: int, buf_len: int
    ) -> Tuple[int, str]:
        """Get error description."""
        if ret_code == ATSPECTROGRAPH_SUCCESS:
            return (ATSPECTROGRAPH_SUCCESS, "Success")
        return (ATSPECTROGRAPH_SUCCESS, f"Error code: {ret_code}")

    def IsGratingPresent(self, device: int) -> Tuple[int, bool]:
        """Check if grating turret is present."""
        return (ATSPECTROGRAPH_SUCCESS, True)

    def IsShutterPresent(self, device: int) -> Tuple[int, bool]:
        """Check if shutter is present."""
        return (ATSPECTROGRAPH_SUCCESS, True)

    def IsFilterPresent(self, device: int) -> Tuple[int, bool]:
        """Check if filter wheel is present."""
        return (ATSPECTROGRAPH_SUCCESS, False)

    def GetNumberGratings(self, device: int) -> Tuple[int, int]:
        """Get number of gratings installed."""
        return (ATSPECTROGRAPH_SUCCESS, self._state.num_gratings)

    def GetGratingInfo(
        self, device: int, grating: int, buf_len: int
    ) -> Tuple[int, float, str, int, int]:
        """Get grating info."""
        if 1 <= grating <= len(self._state.gratings):
            g = self._state.gratings[grating - 1]
            return (ATSPECTROGRAPH_SUCCESS, g["lines"], g["blaze"], 0, 0)
        return (1, 0.0, "", 0, 0)  # Error

    def GetWavelengthLimits(
        self, device: int, grating: int
    ) -> Tuple[int, float, float]:
        """Get wavelength limits for a grating."""
        if 1 <= grating <= len(self._state.gratings):
            g = self._state.gratings[grating - 1]
            return (ATSPECTROGRAPH_SUCCESS, g["wl_min"], g["wl_max"])
        return (1, 0.0, 0.0)  # Error

    def GetGrating(self, device: int) -> Tuple[int, int]:
        """Get current grating."""
        return (ATSPECTROGRAPH_SUCCESS, self._state.current_grating)

    def SetGrating(self, device: int, grating: int) -> int:
        """Set grating (blocking call)."""
        if 1 <= grating <= self._state.num_gratings:
            self._state.current_grating = grating
            # Simulate blocking wait for grating movement
            time.sleep(0.01)  # Small delay for tests
            return ATSPECTROGRAPH_SUCCESS
        return 1  # Error

    def GetWavelength(self, device: int) -> Tuple[int, float]:
        """Get current wavelength."""
        return (ATSPECTROGRAPH_SUCCESS, self._state.current_wavelength)

    def SetWavelength(self, device: int, wavelength: float) -> int:
        """Set wavelength (blocking call)."""
        grating = self._state.current_grating
        g = self._state.gratings[grating - 1]
        if g["wl_min"] <= wavelength <= g["wl_max"]:
            self._state.current_wavelength = wavelength
            # Simulate blocking wait for wavelength motor
            time.sleep(0.01)  # Small delay for tests
            return ATSPECTROGRAPH_SUCCESS
        return 1  # Error

    def SetNumberPixels(self, device: int, num_pixels: int) -> int:
        """Set number of pixels for calibration."""
        self._state.num_pixels = num_pixels
        return ATSPECTROGRAPH_SUCCESS

    def SetPixelWidth(self, device: int, pixel_width: float) -> int:
        """Set pixel width for calibration."""
        self._state.pixel_width = pixel_width
        return ATSPECTROGRAPH_SUCCESS

    def GetCalibration(
        self, device: int, num_pixels: int
    ) -> Tuple[int, List[float]]:
        """Get wavelength calibration array."""
        center = self._state.current_wavelength
        grating = self._state.current_grating
        g = self._state.gratings[grating - 1]

        # Estimate dispersion based on grating
        nm_per_pixel = 0.1 * (150.0 / g["lines"])
        half_range = num_pixels * nm_per_pixel / 2

        wavelengths = np.linspace(
            center - half_range, center + half_range, num_pixels
        ).tolist()

        return (ATSPECTROGRAPH_SUCCESS, wavelengths)


def create_mock_sdk_modules():
    """Create mock modules that can be patched into sys.modules.

    Returns:
        Dictionary of module name to mock module object.
    """
    # Create mock modules
    mock_atmcd = MagicMock()
    mock_atmcd.atmcd = MockAtmcd
    mock_atmcd.atmcd_codes = MockAtmcdCodes
    mock_atmcd.atmcd_errors = MockAtmcdErrors

    mock_spectrograph = MagicMock()
    mock_spectrograph.spectrograph = MagicMock()
    mock_spectrograph.spectrograph.ATSpectrograph = MockATSpectrograph

    return {
        "pyAndorSDK2": mock_atmcd,
        "pyAndorSDK2.atmcd": mock_atmcd,
        "pyAndorSDK2.atmcd_codes": mock_atmcd.atmcd_codes,
        "pyAndorSDK2.atmcd_errors": mock_atmcd.atmcd_errors,
        "pyAndorSpectrograph": mock_spectrograph,
        "pyAndorSpectrograph.spectrograph": mock_spectrograph.spectrograph,
    }
