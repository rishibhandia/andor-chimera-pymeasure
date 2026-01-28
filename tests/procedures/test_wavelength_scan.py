"""Tests for WavelengthScanProcedure and WavelengthImageScanProcedure.

These tests verify wavelength scanning procedures using mock hardware.
"""

from __future__ import annotations

from typing import Any

import pytest


class EventCapture:
    """Capture events emitted by procedures."""

    def __init__(self):
        self.results: list[dict[str, Any]] = []
        self.progress: list[float] = []

    def emit(self, name: str, data: Any) -> None:
        if name == "results":
            self.results.append(data)
        elif name == "progress":
            self.progress.append(data)

    def clear(self) -> None:
        self.results.clear()
        self.progress.clear()


@pytest.fixture
def event_capture():
    return EventCapture()


class TestWavelengthScanProcedureParameters:
    """Tests for WavelengthScanProcedure parameters."""

    def test_parameters_defined(self, mock_sdk):
        """All required parameters are defined."""
        from andor_pymeasure.procedures.wavelength_scan import WavelengthScanProcedure

        proc = WavelengthScanProcedure()

        assert hasattr(proc, "wavelength_start")
        assert hasattr(proc, "wavelength_end")
        assert hasattr(proc, "wavelength_step")
        assert hasattr(proc, "exposure_time")
        assert hasattr(proc, "grating")

    def test_data_columns(self, mock_sdk):
        """DATA_COLUMNS is correctly defined."""
        from andor_pymeasure.procedures.wavelength_scan import WavelengthScanProcedure

        assert WavelengthScanProcedure.DATA_COLUMNS == [
            "Center_Wavelength",
            "Pixel_Wavelength",
            "Intensity",
        ]


class TestWavelengthScanProcedureExecute:
    """Tests for WavelengthScanProcedure.execute()."""

    def test_execute_scans_wavelengths(self, mock_sdk, event_capture):
        """Execute scans across wavelength positions."""
        from andor_pymeasure.procedures.wavelength_scan import WavelengthScanProcedure

        proc = WavelengthScanProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.wavelength_start = 400.0
        proc.wavelength_end = 500.0
        proc.wavelength_step = 50.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        # Should scan: 400, 450, 500 = 3 positions
        # Each position emits xpixels results
        expected_positions = 3
        assert len(event_capture.progress) == expected_positions
        assert event_capture.progress[-1] == 100

        proc.shutdown()

    def test_execute_emits_center_wavelength(self, mock_sdk, event_capture):
        """Execute includes center wavelength in results."""
        from andor_pymeasure.procedures.wavelength_scan import WavelengthScanProcedure

        proc = WavelengthScanProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.wavelength_start = 450.0
        proc.wavelength_end = 450.0  # Single position
        proc.wavelength_step = 50.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        # All results should have Center_Wavelength = 450
        for result in event_capture.results:
            assert "Center_Wavelength" in result
            assert result["Center_Wavelength"] == 450.0

        proc.shutdown()

    def test_execute_clips_to_grating_limits(self, mock_sdk, event_capture):
        """Execute clips wavelength range to grating limits."""
        from andor_pymeasure.procedures.wavelength_scan import WavelengthScanProcedure

        proc = WavelengthScanProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.wavelength_start = 100.0  # Below grating minimum (200)
        proc.wavelength_end = 500.0  # Within grating maximum (1100)
        proc.wavelength_step = 100.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()

        # Get limits for grating 1
        wl_min, wl_max = proc.spectrograph.get_wavelength_limits()

        proc.execute()

        # Center wavelengths should be within limits
        center_wls = set(r["Center_Wavelength"] for r in event_capture.results)
        for wl in center_wls:
            assert wl >= wl_min
            assert wl <= wl_max

        proc.shutdown()

    def test_execute_respects_should_stop(self, mock_sdk, event_capture):
        """Execute stops when should_stop returns True."""
        from andor_pymeasure.procedures.wavelength_scan import WavelengthScanProcedure

        proc = WavelengthScanProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.wavelength_start = 400.0
        proc.wavelength_end = 700.0
        proc.wavelength_step = 50.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: True

        proc.startup()
        proc.execute()

        # Should not emit any results
        assert len(event_capture.results) == 0

        proc.shutdown()


class TestWavelengthImageScanProcedure:
    """Tests for WavelengthImageScanProcedure."""

    def test_data_columns(self, mock_sdk):
        """DATA_COLUMNS includes Y_Position."""
        from andor_pymeasure.procedures.wavelength_scan import WavelengthImageScanProcedure

        assert WavelengthImageScanProcedure.DATA_COLUMNS == [
            "Center_Wavelength",
            "Pixel_Wavelength",
            "Y_Position",
            "Intensity",
        ]

    def test_execute_emits_4_columns(self, mock_sdk, event_capture):
        """Execute emits results with 4 columns."""
        from andor_pymeasure.procedures.wavelength_scan import WavelengthImageScanProcedure

        proc = WavelengthImageScanProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.wavelength_start = 500.0
        proc.wavelength_end = 500.0  # Single position
        proc.wavelength_step = 50.0
        proc.hbin = 4
        proc.vbin = 4
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        for result in event_capture.results:
            assert "Center_Wavelength" in result
            assert "Pixel_Wavelength" in result
            assert "Y_Position" in result
            assert "Intensity" in result

        proc.shutdown()

    def test_execute_applies_binning(self, mock_sdk, event_capture):
        """Execute applies binning to reduce data points per image."""
        from andor_pymeasure.procedures.wavelength_scan import WavelengthImageScanProcedure

        proc = WavelengthImageScanProcedure()
        proc.cooler_enabled = False
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.wavelength_start = 500.0
        proc.wavelength_end = 510.0
        proc.wavelength_step = 100.0  # Only 500 position
        proc.hbin = 4
        proc.vbin = 4
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()

        expected_x = proc.camera.xpixels // 4
        expected_y = proc.camera.ypixels // 4

        proc.execute()

        # Check that Y_Position max is (ypixels // vbin) - 1
        y_positions = set(r["Y_Position"] for r in event_capture.results)
        assert max(y_positions) == expected_y - 1

        # Check that we have the correct number of unique wavelengths
        # (effective x pixels with binning)
        center_500_results = [r for r in event_capture.results if r["Center_Wavelength"] == 500.0]
        pixel_wls_at_500 = set(r["Pixel_Wavelength"] for r in center_500_results)
        assert len(pixel_wls_at_500) == expected_x

        proc.shutdown()
