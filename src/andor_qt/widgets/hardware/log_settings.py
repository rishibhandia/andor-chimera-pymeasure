"""Log settings widget for configuring session log directory.

Provides a QGroupBox with a directory picker (QLineEdit + browse button)
that persists the log directory via QSettings.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

log = logging.getLogger(__name__)

_SETTINGS_ORG = "AndorSpectrometer"
_SETTINGS_APP = "Logging"
_SETTINGS_KEY = "log_directory"
_DEFAULT_LOG_DIR = str(Path.home() / "andor_logs")


class LogSettingsWidget(QGroupBox):
    """Widget for configuring the session log directory.

    Persists the chosen directory via QSettings so it survives across
    application restarts.

    Signals:
        directory_changed: Emitted when the log directory changes.
    """

    directory_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Logging", parent)

        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QHBoxLayout(self)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Log directory:"))

        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("Select log directory...")

        # Load persisted directory or use default
        saved_dir = self._settings.value(_SETTINGS_KEY, _DEFAULT_LOG_DIR)
        self._dir_edit.setText(saved_dir)
        layout.addWidget(self._dir_edit)

        self._browse_button = QPushButton("...")
        self._browse_button.setFixedWidth(30)
        self._browse_button.setToolTip("Browse for log directory")
        layout.addWidget(self._browse_button)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._browse_button.clicked.connect(self._on_browse)
        self._dir_edit.textChanged.connect(self._on_directory_changed)

    @Slot()
    def _on_browse(self) -> None:
        """Handle browse button click."""
        current = self._dir_edit.text() or str(Path.home())

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Log Directory",
            current,
        )

        if directory:
            self._dir_edit.setText(directory)

    @Slot(str)
    def _on_directory_changed(self, path: str) -> None:
        """Handle directory text change — persist to QSettings."""
        self._settings.setValue(_SETTINGS_KEY, path)
        self._settings.sync()
        self.directory_changed.emit(path)

    @property
    def log_directory(self) -> str:
        """Get the configured log directory path."""
        return self._dir_edit.text()

    @log_directory.setter
    def log_directory(self, path: str) -> None:
        """Set the log directory path."""
        self._dir_edit.setText(path)
