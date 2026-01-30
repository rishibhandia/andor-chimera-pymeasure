"""Pytest tests for AndorCamera PyMeasure instrument wrapper.

These tests use mock SDK implementations to test the camera interface
without requiring real hardware.

Fixtures (mock_sdk, camera, initialized_camera) are provided by conftest.py.
"""

from __future__ import annotations

import numpy as np
import pytest


class TestAndorCameraInitialization:
    """Tests for camera initialization and shutdown."""

    def test_initialize_success(self, camera):
        """Camera initializes and reads detector info."""
        camera.initialize()

        assert camera._initialized
        assert camera.xpixels == 1024
        assert camera.ypixels == 256
        assert camera.info is not None
        assert camera.info.serial_number == "12345"

    def test_initialize_already_initialized(self, initialized_camera, caplog):
        """Re-initializing logs a warning."""
        initialized_camera.initialize()
        assert "already initialized" in caplog.text.lower()

    def test_shutdown_success(self, initialized_camera):
        """Camera shuts down cleanly."""
        # Warm up first (mock is already warm)
        initialized_camera.shutdown()
        assert not initialized_camera._initialized

    def test_shutdown_not_initialized(self, camera):
        """Shutdown on non-initialized camera is a no-op."""
        camera.shutdown()  # Should not raise
        assert not camera._initialized


class TestAndorCameraTemperature:
    """Tests for temperature control."""

    def test_temperature_property(self, initialized_camera):
        """Temperature returns current value."""
        temp = initialized_camera.temperature
        assert isinstance(temp, float)
        assert temp == 20.0  # Default mock temperature

    def test_temperature_status_off(self, initialized_camera):
        """Temperature status is OFF when cooler is off."""
        status = initialized_camera.temperature_status
        assert status == "OFF"

    def test_cooler_on_sets_target(self, initialized_camera):
        """Cooler ON sets target temperature."""
        initialized_camera.cooler_on(target=-60)
        assert initialized_camera._cooler_on

    def test_cooler_off(self, initialized_camera):
        """Cooler can be turned off."""
        initialized_camera.cooler_on(target=-60)
        initialized_camera.cooler_off()
        assert not initialized_camera._cooler_on

    def test_cooler_on_not_initialized(self, camera):
        """Cooler ON raises if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            camera.cooler_on(target=-60)


class TestAndorCameraExposure:
    """Tests for exposure time setting."""

    def test_set_exposure(self, initialized_camera):
        """Exposure time can be set."""
        initialized_camera.set_exposure(0.5)
        # The mock stores the value - we'd need to read it back through SDK

    def test_set_exposure_not_initialized(self, camera):
        """Set exposure raises if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            camera.set_exposure(0.1)


class TestAndorCameraAcquisitionFVB:
    """Tests for FVB (Full Vertical Binning) acquisition."""

    def test_acquire_fvb_returns_1d_array(self, initialized_camera):
        """FVB acquisition returns 1D numpy array."""
        initialized_camera.set_exposure(0.01)  # Short exposure for test
        data = initialized_camera.acquire_fvb()

        assert isinstance(data, np.ndarray)
        assert data.ndim == 1
        assert len(data) == initialized_camera.xpixels

    def test_acquire_fvb_data_reasonable(self, initialized_camera):
        """FVB data has reasonable values."""
        initialized_camera.set_exposure(0.01)
        data = initialized_camera.acquire_fvb()

        assert np.all(data >= 0)  # No negative values
        assert np.max(data) > 0  # Has signal

    def test_acquire_fvb_not_initialized(self, camera):
        """FVB acquisition raises if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            camera.acquire_fvb()

    def test_acquire_fvb_with_hbin(self, initialized_camera):
        """FVB acquisition with horizontal binning returns reduced pixel count."""
        initialized_camera.set_exposure(0.01)
        hbin = 2
        data = initialized_camera.acquire_fvb(hbin=hbin)

        assert isinstance(data, np.ndarray)
        assert data.ndim == 1
        assert len(data) == initialized_camera.xpixels // hbin

    def test_acquire_fvb_with_hbin_4(self, initialized_camera):
        """FVB with hbin=4 returns 1/4 pixel count."""
        initialized_camera.set_exposure(0.01)
        hbin = 4
        data = initialized_camera.acquire_fvb(hbin=hbin)

        assert len(data) == initialized_camera.xpixels // hbin

    def test_acquire_fvb_invalid_hbin(self, initialized_camera):
        """FVB with invalid hbin raises ValueError."""
        initialized_camera.set_exposure(0.01)
        # 3 is not a factor of 1024
        with pytest.raises(ValueError, match="must be a factor"):
            initialized_camera.acquire_fvb(hbin=3)


class TestAndorCameraAcquisitionImage:
    """Tests for 2D image acquisition."""

    def test_acquire_image_returns_2d_array(self, initialized_camera):
        """Image acquisition returns 2D numpy array."""
        initialized_camera.set_exposure(0.01)
        data = initialized_camera.acquire_image(hbin=1, vbin=1)

        assert isinstance(data, np.ndarray)
        assert data.ndim == 2
        assert data.shape == (initialized_camera.ypixels, initialized_camera.xpixels)

    def test_acquire_image_with_binning(self, initialized_camera):
        """Image acquisition with binning returns correct shape."""
        initialized_camera.set_exposure(0.01)
        data = initialized_camera.acquire_image(hbin=2, vbin=4)

        expected_x = initialized_camera.xpixels // 2
        expected_y = initialized_camera.ypixels // 4
        assert data.shape == (expected_y, expected_x)

    def test_acquire_image_invalid_hbin(self, initialized_camera):
        """Invalid hbin raises ValueError."""
        with pytest.raises(ValueError, match="hbin"):
            initialized_camera.acquire_image(hbin=3, vbin=1)  # 1024 % 3 != 0

    def test_acquire_image_invalid_vbin(self, initialized_camera):
        """Invalid vbin raises ValueError."""
        with pytest.raises(ValueError, match="vbin"):
            initialized_camera.acquire_image(hbin=1, vbin=5)  # 256 % 5 != 0

    def test_acquire_image_not_initialized(self, camera):
        """Image acquisition raises if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            camera.acquire_image()


class TestAndorCameraAbort:
    """Tests for acquisition abort."""

    def test_abort_acquisition(self, initialized_camera):
        """Abort acquisition does not raise."""
        initialized_camera.abort_acquisition()

    def test_abort_not_initialized(self, camera):
        """Abort on non-initialized camera is a no-op."""
        camera.abort_acquisition()  # Should not raise


class TestAndorCameraWarmup:
    """Tests for warmup before shutdown."""

    def test_warmup_already_warm(self, initialized_camera):
        """Warmup returns True if already warm."""
        # Mock starts at 20C, target is -20C
        result = initialized_camera.warmup(target=-20, timeout=1.0)
        assert result

    def test_warmup_not_initialized(self, camera):
        """Warmup on non-initialized camera returns True."""
        result = camera.warmup()
        assert result


class TestAndorCameraInfo:
    """Tests for camera info properties."""

    def test_xpixels_not_initialized(self, camera):
        """xpixels returns 0 if not initialized."""
        assert camera.xpixels == 0

    def test_ypixels_not_initialized(self, camera):
        """ypixels returns 0 if not initialized."""
        assert camera.ypixels == 0

    def test_info_not_initialized(self, camera):
        """info returns None if not initialized."""
        assert camera.info is None

    def test_info_after_init(self, initialized_camera):
        """info is populated after initialization."""
        info = initialized_camera.info
        assert info is not None
        assert info.xpixels == 1024
        assert info.ypixels == 256
        assert info.pixel_width == 26.0
        assert info.pixel_height == 26.0


class TestAndorCameraTemperatureNotInitialized:
    """Tests for temperature when not initialized."""

    def test_temperature_not_initialized(self, camera):
        """Temperature returns 20.0 if not initialized."""
        assert camera.temperature == 20.0

    def test_temperature_status_not_initialized(self, camera):
        """Temperature status returns NOT_INITIALIZED if not initialized."""
        assert camera.temperature_status == "NOT_INITIALIZED"
