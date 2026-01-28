"""Tests for SpectrumProcedure and ImageProcedure.

These tests verify that PyMeasure procedures correctly acquire spectra
and images using mock hardware.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# Fixtures from parent conftest.py are available


class EventCapture:
    """Capture events emitted by procedures."""

    def __init__(self):
        self.results: list[dict[str, Any]] = []
        self.progress: list[float] = []

    def emit(self, name: str, data: Any) -> None:
        """Capture emit calls."""
        if name == "results":
            self.results.append(data)
        elif name == "progress":
            self.progress.append(data)

    @property
    def wavelengths(self) -> list[float]:
        """Get all wavelength values from results."""
        return [r.get("Wavelength", 0.0) for r in self.results]

    @property
    def intensities(self) -> list[float]:
        """Get all intensity values from results."""
        return [r.get("Intensity", 0.0) for r in self.results]

    def clear(self) -> None:
        """Clear captured events."""
        self.results.clear()
        self.progress.clear()


@pytest.fixture
def event_capture():
    """Create event capture for procedure testing."""
    return EventCapture()


class TestSpectrumProcedureParameters:
    """Tests for SpectrumProcedure parameter definitions."""

    def test_parameters_defined(self, mock_sdk):
        """All required parameters are defined."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()

        # Check parameter attributes exist
        assert hasattr(proc, "exposure_time")
        assert hasattr(proc, "center_wavelength")
        assert hasattr(proc, "grating")
        assert hasattr(proc, "num_accumulations")
        assert hasattr(proc, "cooler_enabled")
        assert hasattr(proc, "target_temperature")

    def test_data_columns(self, mock_sdk):
        """DATA_COLUMNS is correctly defined."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        assert SpectrumProcedure.DATA_COLUMNS == ["Wavelength", "Intensity"]


class TestSpectrumProcedureStartup:
    """Tests for SpectrumProcedure.startup()."""

    def test_startup_initializes_camera(self, mock_sdk):
        """Startup initializes camera."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False

        proc.startup()

        assert hasattr(proc, "camera")
        assert proc.camera._initialized

        proc.shutdown()

    def test_startup_initializes_spectrograph(self, mock_sdk):
        """Startup initializes spectrograph."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False

        proc.startup()

        assert hasattr(proc, "spectrograph")
        assert proc.spectrograph._initialized

        proc.shutdown()

    def test_startup_enables_cooler_when_configured(self, mock_sdk):
        """Startup enables cooler when cooler_enabled is True."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = True
        proc.target_temperature = -70

        proc.startup()

        assert proc.camera._cooler_on

        proc.shutdown()

    def test_startup_skips_cooler_when_disabled(self, mock_sdk):
        """Startup skips cooler when cooler_enabled is False."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False

        proc.startup()

        assert not proc.camera._cooler_on

        proc.shutdown()


class TestSpectrumProcedureExecute:
    """Tests for SpectrumProcedure.execute()."""

    def test_execute_sets_grating(self, mock_sdk, event_capture):
        """Execute sets spectrograph grating."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False
        proc.grating = 2
        proc.exposure_time = 0.01
        proc.num_accumulations = 1
        proc.center_wavelength = 500.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        assert proc.spectrograph.grating == 2

        proc.shutdown()

    def test_execute_sets_wavelength(self, mock_sdk, event_capture):
        """Execute sets spectrograph wavelength."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.num_accumulations = 1
        proc.center_wavelength = 600.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        assert proc.spectrograph.wavelength == 600.0

        proc.shutdown()

    def test_execute_emits_results(self, mock_sdk, event_capture):
        """Execute emits wavelength and intensity results."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.num_accumulations = 1
        proc.center_wavelength = 500.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        # Should emit results for each pixel
        assert len(event_capture.results) == proc.camera.xpixels

        # Each result should have Wavelength and Intensity
        for result in event_capture.results:
            assert "Wavelength" in result
            assert "Intensity" in result

        proc.shutdown()

    def test_execute_results_count_matches_pixels(self, mock_sdk, event_capture):
        """Execute emits one result per pixel."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.num_accumulations = 1
        proc.center_wavelength = 500.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        expected_pixels = proc.camera.xpixels
        proc.execute()

        assert len(event_capture.results) == expected_pixels

        proc.shutdown()

    def test_execute_emits_progress(self, mock_sdk, event_capture):
        """Execute emits progress updates."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.num_accumulations = 1
        proc.center_wavelength = 500.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        assert len(event_capture.progress) > 0
        assert event_capture.progress[-1] == 100

        proc.shutdown()

    def test_execute_accumulates_multiple_scans(self, mock_sdk, event_capture):
        """Execute accumulates when num_accumulations > 1."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.num_accumulations = 3
        proc.center_wavelength = 500.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        # Should have 3 progress updates (one per accumulation)
        assert len(event_capture.progress) == 3

        proc.shutdown()

    def test_execute_respects_should_stop(self, mock_sdk, event_capture):
        """Execute stops when should_stop returns True."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.num_accumulations = 1
        proc.center_wavelength = 500.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: True  # Always stop

        proc.startup()
        proc.execute()

        # Should not emit any results (stopped before acquisition)
        assert len(event_capture.results) == 0

        proc.shutdown()


class TestSpectrumProcedureShutdown:
    """Tests for SpectrumProcedure.shutdown()."""

    def test_shutdown_closes_camera(self, mock_sdk):
        """Shutdown closes camera."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False

        proc.startup()
        assert proc.camera._initialized

        proc.shutdown()
        assert not proc.camera._initialized

    def test_shutdown_closes_spectrograph(self, mock_sdk):
        """Shutdown closes spectrograph."""
        from andor_pymeasure.procedures.spectrum import SpectrumProcedure

        proc = SpectrumProcedure()
        proc.cooler_enabled = False

        proc.startup()
        assert proc.spectrograph._initialized

        proc.shutdown()
        assert not proc.spectrograph._initialized


class TestImageProcedureParameters:
    """Tests for ImageProcedure parameter definitions."""

    def test_parameters_defined(self, mock_sdk):
        """All required parameters are defined."""
        from andor_pymeasure.procedures.spectrum import ImageProcedure

        proc = ImageProcedure()

        # Check parameter attributes exist
        assert hasattr(proc, "exposure_time")
        assert hasattr(proc, "center_wavelength")
        assert hasattr(proc, "grating")
        assert hasattr(proc, "hbin")
        assert hasattr(proc, "vbin")
        assert hasattr(proc, "cooler_enabled")
        assert hasattr(proc, "target_temperature")

    def test_data_columns(self, mock_sdk):
        """DATA_COLUMNS is correctly defined."""
        from andor_pymeasure.procedures.spectrum import ImageProcedure

        assert ImageProcedure.DATA_COLUMNS == ["Wavelength", "Y_Position", "Intensity"]


class TestImageProcedureExecute:
    """Tests for ImageProcedure.execute()."""

    def test_execute_acquires_2d_image(self, mock_sdk, event_capture):
        """Execute acquires 2D image data."""
        from andor_pymeasure.procedures.spectrum import ImageProcedure

        proc = ImageProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.hbin = 1
        proc.vbin = 1
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        # Should emit x * y results
        expected_points = proc.camera.xpixels * proc.camera.ypixels
        assert len(event_capture.results) == expected_points

        proc.shutdown()

    def test_execute_emits_3_columns(self, mock_sdk, event_capture):
        """Execute emits Wavelength, Y_Position, and Intensity."""
        from andor_pymeasure.procedures.spectrum import ImageProcedure

        proc = ImageProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.hbin = 1
        proc.vbin = 1
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        # Each result should have all 3 columns
        for result in event_capture.results:
            assert "Wavelength" in result
            assert "Y_Position" in result
            assert "Intensity" in result

        proc.shutdown()

    def test_execute_applies_binning(self, mock_sdk, event_capture):
        """Execute applies horizontal and vertical binning."""
        from andor_pymeasure.procedures.spectrum import ImageProcedure

        proc = ImageProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.hbin = 2
        proc.vbin = 2
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        expected_x = proc.camera.xpixels // 2
        expected_y = proc.camera.ypixels // 2
        expected_points = expected_x * expected_y

        proc.execute()

        assert len(event_capture.results) == expected_points

        proc.shutdown()
