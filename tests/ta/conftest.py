"""Pytest fixtures for TA module tests."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def qt_app():
    """Create a QApplication instance for Qt-based TA tests."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
