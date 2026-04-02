"""Tests for LogSettingsWidget and session file logging.

Verifies:
- LogSettingsWidget creates with default log directory
- Browse button exists and is functional
- QSettings persistence of log directory
- Log file is created in the configured directory
- Log entries are written to the file
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

os.environ["ANDOR_MOCK"] = "1"

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qt_app():
    """Create a QApplication instance for Qt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _flush_qt_deletions(qt_app):
    """Process pending deleteLater() calls after each test."""
    yield
    qt_app.processEvents()


@pytest.fixture
def clean_qsettings():
    """Clear QSettings for logging before and after each test."""
    settings = QSettings("AndorSpectrometer", "Logging")
    settings.clear()
    settings.sync()
    yield settings
    settings.clear()
    settings.sync()


class TestLogSettingsWidget:
    """Tests for LogSettingsWidget UI component."""

    def test_widget_creates_with_default_directory(self, qt_app, clean_qsettings):
        """Widget should initialize with default log directory."""
        from andor_qt.widgets.hardware.log_settings import LogSettingsWidget

        widget = LogSettingsWidget()
        default_dir = str(Path.home() / "andor_logs")
        assert widget.log_directory == default_dir

    def test_widget_has_browse_button(self, qt_app, clean_qsettings):
        """Widget should have a browse button."""
        from andor_qt.widgets.hardware.log_settings import LogSettingsWidget

        widget = LogSettingsWidget()
        assert widget._browse_button is not None
        assert widget._browse_button.text() == "..."

    def test_widget_has_line_edit(self, qt_app, clean_qsettings):
        """Widget should have a line edit for directory path."""
        from andor_qt.widgets.hardware.log_settings import LogSettingsWidget

        widget = LogSettingsWidget()
        assert widget._dir_edit is not None

    def test_set_log_directory(self, qt_app, clean_qsettings, tmp_path):
        """Setting log_directory should update the line edit."""
        from andor_qt.widgets.hardware.log_settings import LogSettingsWidget

        widget = LogSettingsWidget()
        new_dir = str(tmp_path / "custom_logs")
        widget.log_directory = new_dir
        assert widget.log_directory == new_dir

    def test_persists_directory_to_qsettings(self, qt_app, clean_qsettings, tmp_path):
        """Changing directory should persist to QSettings."""
        from andor_qt.widgets.hardware.log_settings import LogSettingsWidget

        widget = LogSettingsWidget()
        new_dir = str(tmp_path / "persisted_logs")
        widget.log_directory = new_dir

        # Read back from QSettings directly
        settings = QSettings("AndorSpectrometer", "Logging")
        assert settings.value("log_directory") == new_dir

    def test_loads_directory_from_qsettings(self, qt_app, tmp_path):
        """Widget should load previously saved directory from QSettings."""
        from andor_qt.widgets.hardware.log_settings import LogSettingsWidget

        saved_dir = str(tmp_path / "saved_logs")
        settings = QSettings("AndorSpectrometer", "Logging")
        settings.setValue("log_directory", saved_dir)
        settings.sync()

        widget = LogSettingsWidget()
        assert widget.log_directory == saved_dir

        # Cleanup
        settings.clear()
        settings.sync()


class TestSetupFileLogging:
    """Tests for setup_file_logging function."""

    def test_log_file_created_in_directory(self, tmp_path):
        """Log file should be created in the specified directory."""
        from andor_qt.app import setup_file_logging

        log_dir = tmp_path / "test_logs"
        handler = setup_file_logging(str(log_dir))
        try:
            assert log_dir.exists()
            log_files = list(log_dir.glob("*_andor.log"))
            assert len(log_files) == 1
        finally:
            # Remove handler to avoid leaking file handles
            logging.getLogger().removeHandler(handler)
            handler.close()

    def test_log_filename_is_timestamped(self, tmp_path):
        """Log filename should follow YYYYMMDD_HHMMSS_andor.log pattern."""
        import re

        from andor_qt.app import setup_file_logging

        log_dir = tmp_path / "ts_logs"
        handler = setup_file_logging(str(log_dir))
        try:
            log_files = list(log_dir.glob("*_andor.log"))
            assert len(log_files) == 1
            filename = log_files[0].name
            pattern = r"^\d{8}_\d{6}_andor\.log$"
            assert re.match(pattern, filename), f"Filename {filename} doesn't match pattern"
        finally:
            logging.getLogger().removeHandler(handler)
            handler.close()

    def test_log_entries_written_to_file(self, tmp_path):
        """Log messages should appear in the log file."""
        from andor_qt.app import setup_file_logging

        log_dir = tmp_path / "write_logs"
        handler = setup_file_logging(str(log_dir))
        try:
            test_logger = logging.getLogger("test.session_logging")
            test_logger.info("Test message for session logging")
            handler.flush()

            log_files = list(log_dir.glob("*_andor.log"))
            assert len(log_files) == 1
            content = log_files[0].read_text()
            assert "Test message for session logging" in content
        finally:
            logging.getLogger().removeHandler(handler)
            handler.close()

    def test_log_level_info_and_above(self, tmp_path):
        """File handler should capture INFO and above, not DEBUG."""
        from andor_qt.app import setup_file_logging

        log_dir = tmp_path / "level_logs"
        handler = setup_file_logging(str(log_dir))
        try:
            test_logger = logging.getLogger("test.level_check")
            test_logger.setLevel(logging.DEBUG)
            test_logger.debug("This is debug")
            test_logger.info("This is info")
            test_logger.warning("This is warning")
            handler.flush()

            log_files = list(log_dir.glob("*_andor.log"))
            content = log_files[0].read_text()
            assert "This is debug" not in content
            assert "This is info" in content
            assert "This is warning" in content
        finally:
            logging.getLogger().removeHandler(handler)
            handler.close()

    def test_handler_is_rotating(self, tmp_path):
        """Handler should be a RotatingFileHandler with correct limits."""
        from logging.handlers import RotatingFileHandler

        from andor_qt.app import setup_file_logging

        log_dir = tmp_path / "rotate_logs"
        handler = setup_file_logging(str(log_dir))
        try:
            assert isinstance(handler, RotatingFileHandler)
            assert handler.maxBytes == 10 * 1024 * 1024  # 10 MB
            assert handler.backupCount == 5
        finally:
            logging.getLogger().removeHandler(handler)
            handler.close()

    def test_creates_directory_if_not_exists(self, tmp_path):
        """Should create the log directory if it doesn't exist."""
        from andor_qt.app import setup_file_logging

        log_dir = tmp_path / "nested" / "deep" / "logs"
        assert not log_dir.exists()
        handler = setup_file_logging(str(log_dir))
        try:
            assert log_dir.exists()
        finally:
            logging.getLogger().removeHandler(handler)
            handler.close()
