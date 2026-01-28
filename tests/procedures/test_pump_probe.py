"""Tests for PumpProbeProcedure and PumpProbeImageProcedure.

These tests verify pump-probe scanning procedures using mock hardware.
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


class TestPumpProbeProcedureParameters:
    """Tests for PumpProbeProcedure parameters."""

    def test_parameters_defined(self, mock_sdk):
        """All required parameters are defined."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        proc = PumpProbeProcedure()

        assert hasattr(proc, "delay_start")
        assert hasattr(proc, "delay_end")
        assert hasattr(proc, "delay_step")
        assert hasattr(proc, "center_wavelength")
        assert hasattr(proc, "grating")
        assert hasattr(proc, "exposure_time")
        assert hasattr(proc, "num_accumulations")
        assert hasattr(proc, "use_mock_stage")

    def test_data_columns(self, mock_sdk):
        """DATA_COLUMNS is correctly defined."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        assert PumpProbeProcedure.DATA_COLUMNS == ["Delay", "Wavelength", "Intensity"]


class TestPumpProbeProcedureStartup:
    """Tests for PumpProbeProcedure.startup()."""

    def test_startup_initializes_delay_stage(self, mock_sdk):
        """Startup initializes delay stage."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        proc = PumpProbeProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True

        proc.startup()

        assert hasattr(proc, "delay_stage")
        assert proc.delay_stage._initialized

        proc.shutdown()

    def test_startup_uses_mock_stage_when_configured(self, mock_sdk):
        """Startup uses MockDelayStage when use_mock_stage is True."""
        from andor_pymeasure.instruments.delay_stage import MockDelayStage
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        proc = PumpProbeProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True

        proc.startup()

        assert isinstance(proc.delay_stage, MockDelayStage)

        proc.shutdown()


class TestPumpProbeProcedureExecute:
    """Tests for PumpProbeProcedure.execute()."""

    def test_execute_scans_delays(self, mock_sdk, event_capture):
        """Execute scans across delay positions."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        proc = PumpProbeProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.num_accumulations = 1
        proc.delay_start = 0.0
        proc.delay_end = 2.0
        proc.delay_step = 1.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        # Should scan: 0, 1, 2 = 3 positions
        expected_positions = 3
        assert len(event_capture.progress) == expected_positions

        proc.shutdown()

    def test_execute_emits_delay_in_results(self, mock_sdk, event_capture):
        """Execute includes delay in results."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        proc = PumpProbeProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.num_accumulations = 1
        proc.delay_start = 5.0
        proc.delay_end = 5.0  # Single position
        proc.delay_step = 1.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        for result in event_capture.results:
            assert "Delay" in result
            assert result["Delay"] == 5.0

        proc.shutdown()

    def test_execute_moves_delay_stage(self, mock_sdk, event_capture):
        """Execute moves delay stage to each position."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        proc = PumpProbeProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.num_accumulations = 1
        proc.delay_start = 10.0
        proc.delay_end = 10.0
        proc.delay_step = 1.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        # After execution, delay stage should be at 10ps
        assert abs(proc.delay_stage.position_ps - 10.0) < 0.1

        proc.shutdown()

    def test_execute_accumulates_when_configured(self, mock_sdk, event_capture):
        """Execute accumulates multiple scans when num_accumulations > 1."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        proc = PumpProbeProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.num_accumulations = 3  # Accumulate 3 scans
        proc.delay_start = 0.0
        proc.delay_end = 0.0  # Single position
        proc.delay_step = 1.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        # Still emits same number of results (averaged)
        assert len(event_capture.results) == proc.camera.xpixels

        proc.shutdown()

    def test_execute_respects_should_stop(self, mock_sdk, event_capture):
        """Execute stops when should_stop returns True."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        proc = PumpProbeProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.num_accumulations = 1
        proc.delay_start = 0.0
        proc.delay_end = 100.0
        proc.delay_step = 1.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: True

        proc.startup()
        proc.execute()

        assert len(event_capture.results) == 0

        proc.shutdown()


class TestPumpProbeProcedureShutdown:
    """Tests for PumpProbeProcedure.shutdown()."""

    def test_shutdown_closes_delay_stage(self, mock_sdk):
        """Shutdown closes delay stage."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeProcedure

        proc = PumpProbeProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True

        proc.startup()
        assert proc.delay_stage._initialized

        proc.shutdown()
        assert not proc.delay_stage._initialized


class TestPumpProbeImageProcedure:
    """Tests for PumpProbeImageProcedure."""

    def test_data_columns(self, mock_sdk):
        """DATA_COLUMNS includes Y_Position."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeImageProcedure

        assert PumpProbeImageProcedure.DATA_COLUMNS == [
            "Delay",
            "Wavelength",
            "Y_Position",
            "Intensity",
        ]

    def test_execute_emits_4_columns(self, mock_sdk, event_capture):
        """Execute emits results with 4 columns."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeImageProcedure

        proc = PumpProbeImageProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.hbin = 4
        proc.vbin = 4
        proc.delay_start = 0.0
        proc.delay_end = 0.0
        proc.delay_step = 1.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()
        proc.execute()

        for result in event_capture.results:
            assert "Delay" in result
            assert "Wavelength" in result
            assert "Y_Position" in result
            assert "Intensity" in result

        proc.shutdown()

    def test_execute_applies_binning(self, mock_sdk, event_capture):
        """Execute applies binning to reduce data points."""
        from andor_pymeasure.procedures.pump_probe import PumpProbeImageProcedure

        proc = PumpProbeImageProcedure()
        proc.cooler_enabled = False
        proc.use_mock_stage = True
        proc.grating = 1
        proc.exposure_time = 0.01
        proc.center_wavelength = 500.0
        proc.hbin = 4
        proc.vbin = 4
        proc.delay_start = 0.0
        proc.delay_end = 0.0
        proc.delay_step = 1.0
        proc.emit = event_capture.emit
        proc.should_stop = lambda: False

        proc.startup()

        expected_x = proc.camera.xpixels // 4
        expected_y = proc.camera.ypixels // 4
        expected_points = expected_x * expected_y

        proc.execute()

        assert len(event_capture.results) == expected_points

        proc.shutdown()
