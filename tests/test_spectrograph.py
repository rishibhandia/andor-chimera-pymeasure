"""Pytest tests for AndorSpectrograph PyMeasure instrument wrapper.

These tests use mock SDK implementations to test the spectrograph interface
without requiring real hardware.

Fixtures (mock_sdk, spectrograph, initialized_spectrograph) are provided by conftest.py.
"""

from __future__ import annotations

import numpy as np
import pytest


class TestAndorSpectrographInitialization:
    """Tests for spectrograph initialization and shutdown."""

    def test_initialize_success(self, spectrograph):
        """Spectrograph initializes and reads grating info."""
        spectrograph.initialize()

        assert spectrograph._initialized
        assert spectrograph.info is not None
        assert spectrograph.info.num_gratings == 2
        assert spectrograph.info.serial_number == "SPC-001"

    def test_initialize_already_initialized(self, initialized_spectrograph, caplog):
        """Re-initializing logs a warning."""
        initialized_spectrograph.initialize()
        assert "already initialized" in caplog.text.lower()

    def test_shutdown_success(self, initialized_spectrograph):
        """Spectrograph shuts down cleanly."""
        initialized_spectrograph.shutdown()
        assert not initialized_spectrograph._initialized

    def test_shutdown_not_initialized(self, spectrograph):
        """Shutdown on non-initialized spectrograph is a no-op."""
        spectrograph.shutdown()  # Should not raise
        assert not spectrograph._initialized


class TestAndorSpectrographGrating:
    """Tests for grating control."""

    def test_grating_getter(self, initialized_spectrograph):
        """Grating getter returns current grating."""
        grating = initialized_spectrograph.grating
        assert grating == 1  # Default

    def test_grating_setter(self, initialized_spectrograph):
        """Setting grating changes the current grating."""
        initialized_spectrograph.grating = 2
        assert initialized_spectrograph.grating == 2

    def test_grating_setter_invalid_range(self, initialized_spectrograph):
        """Setting invalid grating raises ValueError."""
        with pytest.raises(ValueError, match="out of range"):
            initialized_spectrograph.grating = 5

    def test_grating_setter_not_initialized(self, spectrograph):
        """Setting grating raises if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            spectrograph.grating = 1

    def test_grating_getter_not_initialized(self, spectrograph):
        """Grating getter returns 0 if not initialized."""
        assert spectrograph.grating == 0


class TestAndorSpectrographWavelength:
    """Tests for wavelength control."""

    def test_wavelength_getter(self, initialized_spectrograph):
        """Wavelength getter returns current wavelength."""
        wavelength = initialized_spectrograph.wavelength
        assert wavelength == 500.0  # Default

    def test_wavelength_setter(self, initialized_spectrograph):
        """Setting wavelength changes the current wavelength."""
        initialized_spectrograph.wavelength = 600.0
        assert initialized_spectrograph.wavelength == 600.0

    def test_wavelength_setter_validates_range(self, initialized_spectrograph):
        """Setting wavelength validates against limits."""
        with pytest.raises(ValueError, match="out of range"):
            initialized_spectrograph.wavelength = 99999.0

    def test_wavelength_setter_below_min(self, initialized_spectrograph):
        """Setting wavelength below minimum raises ValueError."""
        with pytest.raises(ValueError, match="out of range"):
            initialized_spectrograph.wavelength = 50.0  # Below min

    def test_wavelength_setter_not_initialized(self, spectrograph):
        """Setting wavelength raises if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            spectrograph.wavelength = 500.0

    def test_wavelength_getter_not_initialized(self, spectrograph):
        """Wavelength getter returns 0.0 if not initialized."""
        assert spectrograph.wavelength == 0.0


class TestAndorSpectrographWavelengthLimits:
    """Tests for wavelength limits."""

    def test_get_wavelength_limits_default_grating(self, initialized_spectrograph):
        """Get wavelength limits for current grating."""
        wl_min, wl_max = initialized_spectrograph.get_wavelength_limits()
        assert wl_min == 200.0  # Grating 1 limits
        assert wl_max == 1100.0

    def test_get_wavelength_limits_specific_grating(self, initialized_spectrograph):
        """Get wavelength limits for specific grating."""
        wl_min, wl_max = initialized_spectrograph.get_wavelength_limits(grating=2)
        assert wl_min == 300.0  # Grating 2 limits
        assert wl_max == 800.0

    def test_get_wavelength_limits_not_initialized(self, spectrograph):
        """Wavelength limits returns (0, 0) if not initialized."""
        limits = spectrograph.get_wavelength_limits()
        assert limits == (0.0, 0.0)


class TestAndorSpectrographCalibration:
    """Tests for wavelength calibration."""

    def test_get_calibration_returns_wavelengths(self, initialized_spectrograph):
        """Calibration returns wavelength array."""
        cal = initialized_spectrograph.get_calibration(1024, 26.0)

        assert isinstance(cal, np.ndarray)
        assert len(cal) == 1024
        assert cal[0] < cal[-1]  # Wavelengths increasing

    def test_get_calibration_centered_on_wavelength(self, initialized_spectrograph):
        """Calibration is centered on current wavelength."""
        initialized_spectrograph.wavelength = 600.0
        cal = initialized_spectrograph.get_calibration(1024, 26.0)

        center_idx = len(cal) // 2
        # Center wavelength should be near 600nm
        assert abs(cal[center_idx] - 600.0) < 10.0

    def test_get_calibration_different_gratings(self, initialized_spectrograph):
        """Different gratings have different dispersion."""
        initialized_spectrograph.wavelength = 500.0

        initialized_spectrograph.grating = 1
        cal1 = initialized_spectrograph.get_calibration(1024, 26.0)
        range1 = cal1[-1] - cal1[0]

        initialized_spectrograph.grating = 2
        cal2 = initialized_spectrograph.get_calibration(1024, 26.0)
        range2 = cal2[-1] - cal2[0]

        # Grating 2 has higher lines/mm, so smaller range
        assert range2 < range1

    def test_get_calibration_not_initialized(self, spectrograph):
        """Calibration raises if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            spectrograph.get_calibration(1024, 26.0)


class TestAndorSpectrographInfo:
    """Tests for spectrograph info properties."""

    def test_info_not_initialized(self, spectrograph):
        """info returns None if not initialized."""
        assert spectrograph.info is None

    def test_info_after_init(self, initialized_spectrograph):
        """info is populated after initialization."""
        info = initialized_spectrograph.info
        assert info is not None
        assert info.num_gratings == 2
        assert info.serial_number == "SPC-001"
        assert info.has_shutter
        assert not info.has_filter

    def test_info_gratings(self, initialized_spectrograph):
        """Grating info is available."""
        info = initialized_spectrograph.info
        assert len(info.gratings) == 2

        g1 = info.gratings[0]
        assert g1.index == 1
        assert g1.lines_per_mm == 150.0
        assert g1.blaze == "500nm"

        g2 = info.gratings[1]
        assert g2.index == 2
        assert g2.lines_per_mm == 600.0


class TestAndorSpectrographThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_grating_changes(self, initialized_spectrograph):
        """Multiple grating changes don't corrupt state."""
        import threading

        results = []
        errors = []

        def change_grating(target):
            try:
                initialized_spectrograph.grating = target
                results.append(initialized_spectrograph.grating)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=change_grating, args=(1,)),
            threading.Thread(target=change_grating, args=(2,)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors should occur
        assert not errors
        # Final state should be one of the targets
        assert initialized_spectrograph.grating in [1, 2]


class TestAndorSpectrographBlockingBehavior:
    """Tests verifying SetGrating is blocking (no IsGratingMoving)."""

    def test_grating_change_is_blocking(self, initialized_spectrograph):
        """Grating change completes before returning."""
        initialized_spectrograph.grating = 2

        # Immediately reading should return the new value
        # (if it wasn't blocking, we might get the old value)
        assert initialized_spectrograph.grating == 2

    def test_wavelength_change_is_blocking(self, initialized_spectrograph):
        """Wavelength change completes before returning."""
        initialized_spectrograph.wavelength = 600.0

        # Immediately reading should return the new value
        assert initialized_spectrograph.wavelength == 600.0
