"""Integration tests for AndorCamera and AndorSpectrograph together.

These tests verify that the camera and spectrograph work together correctly,
including wavelength calibration and combined acquisition workflows.

Fixtures (mock_sdk, initialized_camera, initialized_spectrograph, hardware_pair)
are provided by conftest.py.
"""

from __future__ import annotations

import numpy as np
import pytest


class TestCameraIntegration:
    """Integration tests for camera functionality."""

    def test_camera_initialization(self, initialized_camera):
        """Camera initializes and reports correct detector info."""
        assert initialized_camera._initialized
        assert initialized_camera.xpixels == 1024
        assert initialized_camera.ypixels == 256
        assert initialized_camera.info is not None
        assert initialized_camera.info.serial_number == "12345"

    def test_camera_fvb_acquisition(self, initialized_camera):
        """Camera acquires FVB spectrum."""
        initialized_camera.set_exposure(0.01)
        data = initialized_camera.acquire_fvb()

        assert isinstance(data, np.ndarray)
        assert data.ndim == 1
        assert len(data) == initialized_camera.xpixels
        assert np.all(data >= 0)

    def test_camera_image_acquisition(self, initialized_camera):
        """Camera acquires 2D image."""
        initialized_camera.set_exposure(0.01)
        data = initialized_camera.acquire_image(hbin=1, vbin=1)

        assert isinstance(data, np.ndarray)
        assert data.ndim == 2
        assert data.shape == (initialized_camera.ypixels, initialized_camera.xpixels)

    def test_camera_binned_acquisition(self, initialized_camera):
        """Camera acquires with binning."""
        initialized_camera.set_exposure(0.01)
        data = initialized_camera.acquire_image(hbin=2, vbin=2)

        expected_x = initialized_camera.xpixels // 2
        expected_y = initialized_camera.ypixels // 2
        assert data.shape == (expected_y, expected_x)


class TestSpectrographIntegration:
    """Integration tests for spectrograph functionality."""

    def test_spectrograph_initialization(self, initialized_spectrograph):
        """Spectrograph initializes and reports correct info."""
        assert initialized_spectrograph._initialized
        assert initialized_spectrograph.info is not None
        assert initialized_spectrograph.info.num_gratings == 2
        assert initialized_spectrograph.info.serial_number == "SPC-001"

    def test_spectrograph_grating_change(self, initialized_spectrograph):
        """Spectrograph changes grating."""
        initialized_spectrograph.grating = 2
        assert initialized_spectrograph.grating == 2

        initialized_spectrograph.grating = 1
        assert initialized_spectrograph.grating == 1

    def test_spectrograph_wavelength_change(self, initialized_spectrograph):
        """Spectrograph changes wavelength."""
        initialized_spectrograph.wavelength = 600.0
        assert initialized_spectrograph.wavelength == 600.0

    def test_spectrograph_calibration(self, initialized_spectrograph):
        """Spectrograph generates calibration."""
        cal = initialized_spectrograph.get_calibration(1024, 26.0)

        assert isinstance(cal, np.ndarray)
        assert len(cal) == 1024
        assert cal[0] < cal[-1]  # Wavelengths increasing


class TestCombinedHardware:
    """Integration tests for camera and spectrograph together."""

    def test_hardware_pair_initialization(self, hardware_pair):
        """Both devices initialize correctly."""
        camera, spectrograph = hardware_pair

        assert camera._initialized
        assert spectrograph._initialized

    def test_calibration_for_detector(self, hardware_pair):
        """Spectrograph calibration matches camera detector."""
        camera, spectrograph = hardware_pair

        # Get calibration for camera's detector size
        cal = spectrograph.get_calibration(camera.xpixels, camera.info.pixel_width)

        assert len(cal) == camera.xpixels
        assert cal[0] < cal[-1]

    def test_spectrum_with_calibration(self, hardware_pair):
        """Acquire spectrum with wavelength calibration."""
        camera, spectrograph = hardware_pair

        # Set wavelength
        spectrograph.wavelength = 550.0

        # Get calibration
        cal = spectrograph.get_calibration(camera.xpixels, camera.info.pixel_width)

        # Acquire spectrum
        camera.set_exposure(0.01)
        spectrum = camera.acquire_fvb()

        # Verify shapes match
        assert len(spectrum) == len(cal)

        # Calibration should be centered around 550nm
        center_idx = len(cal) // 2
        assert abs(cal[center_idx] - 550.0) < 20.0  # Within 20nm of center

    def test_grating_affects_calibration_range(self, hardware_pair):
        """Different gratings produce different wavelength ranges."""
        camera, spectrograph = hardware_pair

        spectrograph.wavelength = 500.0

        # Grating 1 (150 l/mm - lower dispersion)
        spectrograph.grating = 1
        cal1 = spectrograph.get_calibration(camera.xpixels, camera.info.pixel_width)
        range1 = cal1[-1] - cal1[0]

        # Grating 2 (600 l/mm - higher dispersion)
        spectrograph.grating = 2
        cal2 = spectrograph.get_calibration(camera.xpixels, camera.info.pixel_width)
        range2 = cal2[-1] - cal2[0]

        # Higher lines/mm = smaller wavelength range
        assert range2 < range1

    def test_image_acquisition_with_calibration(self, hardware_pair):
        """Acquire 2D image with calibration."""
        camera, spectrograph = hardware_pair

        spectrograph.wavelength = 500.0
        cal = spectrograph.get_calibration(camera.xpixels, camera.info.pixel_width)

        camera.set_exposure(0.01)
        image = camera.acquire_image(hbin=1, vbin=1)

        # Image width should match calibration length
        assert image.shape[1] == len(cal)

    def test_binned_image_calibration(self, hardware_pair):
        """Binned image calibration is adjusted correctly."""
        camera, spectrograph = hardware_pair

        hbin = 2
        expected_pixels = camera.xpixels // hbin

        # Get calibration for binned pixels
        cal = spectrograph.get_calibration(expected_pixels, camera.info.pixel_width * hbin)

        camera.set_exposure(0.01)
        image = camera.acquire_image(hbin=hbin, vbin=1)

        assert image.shape[1] == len(cal)
        assert len(cal) == expected_pixels


class TestShutdownSequence:
    """Tests for proper shutdown handling."""

    def test_camera_shutdown(self, initialized_camera):
        """Camera shuts down cleanly."""
        initialized_camera.shutdown()
        assert not initialized_camera._initialized

    def test_spectrograph_shutdown(self, initialized_spectrograph):
        """Spectrograph shuts down cleanly."""
        initialized_spectrograph.shutdown()
        assert not initialized_spectrograph._initialized

    def test_combined_shutdown(self, hardware_pair):
        """Both devices shut down cleanly."""
        camera, spectrograph = hardware_pair

        camera.shutdown()
        spectrograph.shutdown()

        assert not camera._initialized
        assert not spectrograph._initialized
