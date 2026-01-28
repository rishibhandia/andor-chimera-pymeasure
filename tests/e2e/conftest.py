"""Pytest fixtures for end-to-end integration tests.

These fixtures provide a full application environment with mock hardware
for testing complete workflows.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from unittest.mock import patch

import pytest

# Force mock mode for all tests
os.environ["ANDOR_MOCK"] = "1"


@pytest.fixture(scope="module")
def qt_app():
    """Create a QApplication instance for Qt tests."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(scope="function")
def reset_singletons(qt_app):
    """Reset all singleton instances before and after each test."""
    from andor_qt.core.event_bus import EventBus
    from andor_qt.core.hardware_manager import HardwareManager

    HardwareManager.reset_instance()
    EventBus.reset_instance()

    yield

    HardwareManager.reset_instance()
    EventBus.reset_instance()


def wait_for_condition(
    condition_fn,
    timeout: float = 5.0,
    poll_interval: float = 0.05,
) -> bool:
    """Wait for a condition to become true, processing Qt events.

    This is essential for receiving Qt signals emitted from background
    threads, which use queued connections and require event loop processing.
    """
    from PySide6.QtWidgets import QApplication

    start = time.time()
    while time.time() - start < timeout:
        QApplication.processEvents()
        if condition_fn():
            return True
        time.sleep(poll_interval)
    return False


@pytest.fixture
def wait_for():
    """Fixture providing the wait_for_condition function."""
    return wait_for_condition
