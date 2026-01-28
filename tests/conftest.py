"""Pytest fixtures for andor-chimera-pymeasure tests.

This module provides centralized fixtures for testing camera, spectrograph,
delay stage, and procedure components using mock SDK implementations.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Force mock mode for all tests
os.environ["ANDOR_MOCK"] = "1"

from andor_pymeasure.instruments.mock import (
    ATSPECTROGRAPH_SUCCESS,
    DRV_SUCCESS,
    DRV_TEMPERATURE_NOT_REACHED,
    DRV_TEMPERATURE_OFF,
    DRV_TEMPERATURE_STABILIZED,
    MockATSpectrograph,
    MockAtmcd,
    MockAtmcdCodes,
    MockAtmcdErrors,
    create_mock_sdk_modules,
)


# =============================================================================
# Utility Functions
# =============================================================================


def make_handler(name: str = "test_handler"):
    """Create a mock handler with a proper __name__ attribute.

    Used for testing event handlers and callbacks.
    """
    mock = MagicMock()
    mock.__name__ = name
    return mock


@pytest.fixture
def handler_factory():
    """Fixture that returns the make_handler function for creating mock handlers."""
    return make_handler


# =============================================================================
# Mock SDK Fixtures
# =============================================================================


@pytest.fixture
def mock_sdk():
    """Patch SDK imports with mock implementations.

    This fixture patches sys.modules to use mock SDK classes instead of
    real hardware SDKs. Use this for all tests that need camera or spectrograph.
    """
    mock_modules = create_mock_sdk_modules()

    with patch.dict(sys.modules, mock_modules):
        yield mock_modules


@pytest.fixture
def mock_atmcd_instance():
    """Create a standalone MockAtmcd instance for direct testing."""
    return MockAtmcd("C:\\mock\\sdk")


@pytest.fixture
def mock_spectrograph_instance():
    """Create a standalone MockATSpectrograph instance for direct testing."""
    return MockATSpectrograph("C:\\mock\\sdk")


# =============================================================================
# Camera Fixtures
# =============================================================================


@pytest.fixture
def camera(mock_sdk):
    """Create a camera instance with mock SDK (not initialized)."""
    from andor_pymeasure.instruments.andor_camera import AndorCamera

    cam = AndorCamera(sdk_path="C:\\mock\\sdk")
    return cam


@pytest.fixture
def initialized_camera(camera):
    """Create and initialize a camera with proper cleanup.

    Yields an initialized camera and ensures proper shutdown after the test.
    """
    camera.initialize()
    yield camera
    if camera._initialized:
        camera.shutdown()


# =============================================================================
# Spectrograph Fixtures
# =============================================================================


@pytest.fixture
def spectrograph(mock_sdk):
    """Create a spectrograph instance with mock SDK (not initialized)."""
    from andor_pymeasure.instruments.andor_spectrograph import AndorSpectrograph

    spec = AndorSpectrograph(device_index=0, sdk_path="C:\\mock\\sdk")
    return spec


@pytest.fixture
def initialized_spectrograph(spectrograph):
    """Create and initialize a spectrograph with proper cleanup.

    Yields an initialized spectrograph and ensures proper shutdown after the test.
    """
    spectrograph.initialize()
    yield spectrograph
    if spectrograph._initialized:
        spectrograph.shutdown()


# =============================================================================
# Delay Stage Fixtures
# =============================================================================


@pytest.fixture
def mock_delay_stage():
    """Create a mock delay stage (not initialized)."""
    from andor_pymeasure.instruments.delay_stage import MockDelayStage

    stage = MockDelayStage(
        position_min=0.0,
        position_max=100.0,  # Smaller range for faster tests
        velocity=1000.0,  # Fast velocity for tests
    )
    return stage


@pytest.fixture
def initialized_delay_stage(mock_delay_stage):
    """Create and initialize a mock delay stage with proper cleanup."""
    mock_delay_stage.initialize()
    yield mock_delay_stage
    if mock_delay_stage._initialized:
        mock_delay_stage.shutdown()


# =============================================================================
# Combined Hardware Fixtures
# =============================================================================


@pytest.fixture
def hardware_pair(initialized_camera, initialized_spectrograph):
    """Provide both initialized camera and spectrograph.

    Returns a tuple of (camera, spectrograph) for integration tests.
    """
    return (initialized_camera, initialized_spectrograph)


@pytest.fixture
def full_hardware(initialized_camera, initialized_spectrograph, initialized_delay_stage):
    """Provide all hardware components for pump-probe tests.

    Returns a tuple of (camera, spectrograph, delay_stage).
    """
    return (initialized_camera, initialized_spectrograph, initialized_delay_stage)


# =============================================================================
# Procedure Testing Fixtures
# =============================================================================


class EventCapture:
    """Capture events emitted by procedures."""

    def __init__(self):
        self.results: list[dict[str, Any]] = []
        self.progress: list[float] = []
        self.logs: list[str] = []

    def on_results(self, data: dict[str, Any]) -> None:
        """Capture results event."""
        self.results.append(data)

    def on_progress(self, value: float) -> None:
        """Capture progress event."""
        self.progress.append(value)

    def on_log(self, message: str) -> None:
        """Capture log event."""
        self.logs.append(message)

    @property
    def wavelengths(self) -> list[float]:
        """Get all wavelength values from results."""
        return [r.get("Wavelength", 0.0) for r in self.results]

    @property
    def intensities(self) -> list[float]:
        """Get all intensity values from results."""
        return [r.get("Intensity", 0.0) for r in self.results]

    def clear(self) -> None:
        """Clear all captured events."""
        self.results.clear()
        self.progress.clear()
        self.logs.clear()


@pytest.fixture
def event_capture():
    """Create an EventCapture instance for capturing procedure events."""
    return EventCapture()


@pytest.fixture
def mock_procedure_emit(event_capture):
    """Create a mock emit function that routes to event_capture."""

    def mock_emit(name: str, data: Any) -> None:
        if name == "results":
            event_capture.on_results(data)
        elif name == "progress":
            event_capture.on_progress(data)
        elif name == "log":
            event_capture.on_log(data)

    return mock_emit


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================


@pytest.fixture
def data_dir(tmp_path):
    """Create a temporary data directory for test outputs."""
    data_path = tmp_path / "data"
    data_path.mkdir()
    return data_path


# =============================================================================
# NumPy Testing Utilities
# =============================================================================


@pytest.fixture
def assert_array_equal():
    """Fixture providing np.testing.assert_array_equal."""
    return np.testing.assert_array_equal


@pytest.fixture
def assert_array_almost_equal():
    """Fixture providing np.testing.assert_array_almost_equal."""
    return np.testing.assert_array_almost_equal


# =============================================================================
# Mock Serial Port Fixture (for NewportDelayStage)
# =============================================================================


@pytest.fixture
def mock_serial():
    """Create a mock serial port for testing NewportDelayStage."""
    mock = MagicMock()
    mock.write = MagicMock()
    mock.readline = MagicMock(return_value=b"1TP0.000\r\n")
    mock.close = MagicMock()

    with patch("serial.Serial", return_value=mock):
        yield mock
