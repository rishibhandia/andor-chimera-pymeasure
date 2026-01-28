"""Pytest fixtures for Qt component tests.

This module provides fixtures for testing Qt-based components like
HardwareManager and widgets using mock SDK implementations.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

# Force mock mode for all tests
os.environ["ANDOR_MOCK"] = "1"


@pytest.fixture(scope="module")
def qt_app():
    """Create a QApplication instance for Qt tests.

    Qt requires a QApplication to exist before using most Qt classes.
    This is created once per test module.
    """
    from PySide6.QtWidgets import QApplication

    # Check if an app already exists
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    yield app

    # Don't delete the app, as it may be needed by other tests


@pytest.fixture(scope="function")
def reset_hardware_manager(mock_sdk, qt_app):
    """Reset HardwareManager singleton before and after each test.

    This ensures tests are isolated and don't share state.
    Requires mock_sdk to ensure proper import order.
    """
    from andor_qt.core.hardware_manager import HardwareManager

    # Reset before test
    HardwareManager.reset_instance()

    yield HardwareManager

    # Reset after test
    HardwareManager.reset_instance()


@pytest.fixture
def hardware_manager(reset_hardware_manager):
    """Create a fresh HardwareManager instance with mock SDK."""
    HardwareManager = reset_hardware_manager
    manager = HardwareManager.instance()
    return manager


@pytest.fixture
def mock_signals(qt_app):
    """Get the hardware signals instance."""
    from andor_qt.core.signals import get_hardware_signals
    return get_hardware_signals()


class SignalCapture:
    """Capture Qt signals for testing."""

    def __init__(self):
        self.camera_initialized: list[dict] = []
        self.spectrograph_initialized: list[dict] = []
        self.temperature_changed: list[tuple[float, str]] = []
        self.cooler_state_changed: list[tuple[bool, int]] = []
        self.grating_changing: list[int] = []
        self.grating_changed: list[int] = []
        self.wavelength_changing: list[float] = []
        self.wavelength_changed: list[float] = []
        self.calibration_updated: list[Any] = []
        self.errors: list[tuple[str, str]] = []

    def connect_all(self, signals):
        """Connect all signal handlers."""
        signals.camera_initialized.connect(
            lambda d: self.camera_initialized.append(d)
        )
        signals.spectrograph_initialized.connect(
            lambda d: self.spectrograph_initialized.append(d)
        )
        signals.temperature_changed.connect(
            lambda t, s: self.temperature_changed.append((t, s))
        )
        signals.cooler_state_changed.connect(
            lambda on, temp: self.cooler_state_changed.append((on, temp))
        )
        signals.grating_changing.connect(
            lambda g: self.grating_changing.append(g)
        )
        signals.grating_changed.connect(
            lambda g: self.grating_changed.append(g)
        )
        signals.wavelength_changing.connect(
            lambda w: self.wavelength_changing.append(w)
        )
        signals.wavelength_changed.connect(
            lambda w: self.wavelength_changed.append(w)
        )
        signals.calibration_updated.connect(
            lambda c: self.calibration_updated.append(c)
        )
        signals.error_occurred.connect(
            lambda src, msg: self.errors.append((src, msg))
        )

    def clear(self):
        """Clear all captured signals."""
        self.camera_initialized.clear()
        self.spectrograph_initialized.clear()
        self.temperature_changed.clear()
        self.cooler_state_changed.clear()
        self.grating_changing.clear()
        self.grating_changed.clear()
        self.wavelength_changing.clear()
        self.wavelength_changed.clear()
        self.calibration_updated.clear()
        self.errors.clear()


@pytest.fixture
def signal_capture():
    """Create a SignalCapture instance for testing Qt signals."""
    return SignalCapture()


def wait_for_condition(
    condition_fn,
    timeout: float = 5.0,
    poll_interval: float = 0.05,
) -> bool:
    """Wait for a condition to become true.

    Args:
        condition_fn: Function that returns True when condition is met.
        timeout: Maximum time to wait in seconds.
        poll_interval: Time between condition checks in seconds.

    Returns:
        True if condition was met, False if timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        if condition_fn():
            return True
        time.sleep(poll_interval)
    return False


@pytest.fixture
def wait_for():
    """Fixture providing the wait_for_condition function."""
    return wait_for_condition


def wait_for_threads(timeout: float = 2.0) -> None:
    """Wait for all non-main threads to complete.

    Args:
        timeout: Maximum time to wait in seconds.
    """
    start = time.time()
    while time.time() - start < timeout:
        active = [
            t for t in threading.enumerate()
            if t.name != "MainThread" and t.is_alive() and t.daemon
        ]
        if not active:
            return
        time.sleep(0.05)


@pytest.fixture
def wait_threads():
    """Fixture providing the wait_for_threads function."""
    return wait_for_threads
