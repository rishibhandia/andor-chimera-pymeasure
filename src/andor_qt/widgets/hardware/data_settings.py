"""Data settings widget for save directory and filename configuration.

This widget provides controls for configuring data save settings.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class DataSettingsWidget(QGroupBox):
    """Widget for configuring data save settings.

    Features:
    - Directory browser
    - Base filename entry
    - Counter vs timestamp naming
    - Auto-save checkbox
    - Session metadata (sample ID, operator)

    Signals:
        settings_changed: Emitted when any setting changes
    """

    settings_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Data Settings", parent)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Directory row
        dir_row = QHBoxLayout()

        dir_row.addWidget(QLabel("Directory:"))

        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("Select save directory...")
        self._dir_edit.setText(str(Path.home() / "AndorData"))
        dir_row.addWidget(self._dir_edit)

        self._browse_button = QPushButton("...")
        self._browse_button.setFixedWidth(30)
        self._browse_button.setToolTip("Browse for directory")
        dir_row.addWidget(self._browse_button)

        layout.addLayout(dir_row)

        # Filename row
        name_row = QHBoxLayout()

        name_row.addWidget(QLabel("Base Name:"))

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("spectrum")
        self._name_edit.setText("spectrum")
        self._name_edit.setToolTip("Base filename for saved data")
        name_row.addWidget(self._name_edit)

        layout.addLayout(name_row)

        # Naming mode row
        mode_row = QHBoxLayout()

        mode_row.addWidget(QLabel("Naming:"))

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Counter (001, 002, ...)", "counter")
        self._mode_combo.addItem("Timestamp", "timestamp")
        self._mode_combo.setToolTip("File naming mode")
        mode_row.addWidget(self._mode_combo)

        self._counter_spin = QSpinBox()
        self._counter_spin.setRange(1, 99999)
        self._counter_spin.setValue(1)
        self._counter_spin.setToolTip("Starting counter value")
        mode_row.addWidget(self._counter_spin)

        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Auto-save row
        save_row = QHBoxLayout()

        self._autosave_check = QCheckBox("Auto-save after acquisition")
        self._autosave_check.setChecked(True)
        save_row.addWidget(self._autosave_check)

        save_row.addStretch()
        layout.addLayout(save_row)

        # Metadata rows
        meta_row1 = QHBoxLayout()

        meta_row1.addWidget(QLabel("Sample ID:"))

        self._sample_edit = QLineEdit()
        self._sample_edit.setPlaceholderText("Optional")
        meta_row1.addWidget(self._sample_edit)

        layout.addLayout(meta_row1)

        meta_row2 = QHBoxLayout()

        meta_row2.addWidget(QLabel("Operator:"))

        self._operator_edit = QLineEdit()
        self._operator_edit.setPlaceholderText("Optional")
        meta_row2.addWidget(self._operator_edit)

        layout.addLayout(meta_row2)

        # Calibration source row
        cal_row = QHBoxLayout()

        cal_row.addWidget(QLabel("Calibration:"))

        self._cal_combo = QComboBox()
        self._cal_combo.addItem("From SDK", "sdk")
        self._cal_combo.addItem("From File", "file")
        self._cal_combo.setToolTip("Wavelength calibration source")
        cal_row.addWidget(self._cal_combo)

        layout.addLayout(cal_row)

        # Calibration file row (hidden by default)
        cal_file_row = QHBoxLayout()

        self._cal_file_edit = QLineEdit()
        self._cal_file_edit.setPlaceholderText("Select calibration file...")
        self._cal_file_edit.setEnabled(False)
        cal_file_row.addWidget(self._cal_file_edit)

        self._cal_browse_button = QPushButton("...")
        self._cal_browse_button.setFixedWidth(30)
        self._cal_browse_button.setToolTip("Browse for calibration file")
        self._cal_browse_button.setEnabled(False)
        cal_file_row.addWidget(self._cal_browse_button)

        layout.addLayout(cal_file_row)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._browse_button.clicked.connect(self._on_browse)
        self._dir_edit.textChanged.connect(self._emit_settings_changed)
        self._name_edit.textChanged.connect(self._emit_settings_changed)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._counter_spin.valueChanged.connect(self._emit_settings_changed)
        self._autosave_check.stateChanged.connect(self._emit_settings_changed)
        self._sample_edit.textChanged.connect(self._emit_settings_changed)
        self._operator_edit.textChanged.connect(self._emit_settings_changed)
        self._cal_combo.currentIndexChanged.connect(self._on_cal_mode_changed)
        self._cal_browse_button.clicked.connect(self._on_cal_browse)
        self._cal_file_edit.textChanged.connect(self._emit_settings_changed)

    @Slot()
    def _on_browse(self) -> None:
        """Handle browse button click."""
        current = self._dir_edit.text() or str(Path.home())

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Save Directory",
            current,
        )

        if directory:
            self._dir_edit.setText(directory)

    @Slot(int)
    def _on_mode_changed(self, index: int) -> None:
        """Handle naming mode change."""
        mode = self._mode_combo.itemData(index)
        self._counter_spin.setEnabled(mode == "counter")
        self._emit_settings_changed()

    @Slot(int)
    def _on_cal_mode_changed(self, index: int) -> None:
        """Handle calibration mode change."""
        mode = self._cal_combo.itemData(index)
        use_file = mode == "file"
        self._cal_file_edit.setEnabled(use_file)
        self._cal_browse_button.setEnabled(use_file)
        self._emit_settings_changed()

    @Slot()
    def _on_cal_browse(self) -> None:
        """Handle calibration file browse button click."""
        current = self._cal_file_edit.text() or str(Path.home())

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Calibration File",
            current,
            "Calibration Files (*.csv *.txt *.cal);;All Files (*)",
        )

        if filepath:
            self._cal_file_edit.setText(filepath)

    @Slot()
    def _emit_settings_changed(self) -> None:
        """Emit settings_changed signal."""
        self.settings_changed.emit()

    @property
    def directory(self) -> str:
        """Get save directory path."""
        return self._dir_edit.text()

    @directory.setter
    def directory(self, path: str) -> None:
        """Set save directory path."""
        self._dir_edit.setText(path)

    @property
    def base_name(self) -> str:
        """Get base filename."""
        return self._name_edit.text() or "spectrum"

    @base_name.setter
    def base_name(self, name: str) -> None:
        """Set base filename."""
        self._name_edit.setText(name)

    @property
    def naming_mode(self) -> str:
        """Get naming mode ('counter' or 'timestamp')."""
        return self._mode_combo.currentData()

    @property
    def counter(self) -> int:
        """Get current counter value."""
        return self._counter_spin.value()

    @counter.setter
    def counter(self, value: int) -> None:
        """Set counter value."""
        self._counter_spin.setValue(value)

    @property
    def auto_save(self) -> bool:
        """Get auto-save setting."""
        return self._autosave_check.isChecked()

    @auto_save.setter
    def auto_save(self, enabled: bool) -> None:
        """Set auto-save setting."""
        self._autosave_check.setChecked(enabled)

    @property
    def sample_id(self) -> str:
        """Get sample ID."""
        return self._sample_edit.text()

    @sample_id.setter
    def sample_id(self, value: str) -> None:
        """Set sample ID."""
        self._sample_edit.setText(value)

    @property
    def operator(self) -> str:
        """Get operator name."""
        return self._operator_edit.text()

    @operator.setter
    def operator(self, value: str) -> None:
        """Set operator name."""
        self._operator_edit.setText(value)

    @property
    def calibration_source(self) -> str:
        """Get calibration source ('sdk' or 'file')."""
        return self._cal_combo.currentData()

    @calibration_source.setter
    def calibration_source(self, source: str) -> None:
        """Set calibration source."""
        index = self._cal_combo.findData(source)
        if index >= 0:
            self._cal_combo.setCurrentIndex(index)

    @property
    def calibration_file(self) -> Optional[str]:
        """Get calibration file path."""
        path = self._cal_file_edit.text()
        return path if path else None

    @calibration_file.setter
    def calibration_file(self, path: str) -> None:
        """Set calibration file path."""
        self._cal_file_edit.setText(path or "")

    def get_next_filepath(self, extension: str = ".csv") -> Path:
        """Generate the next filepath based on current settings.

        Args:
            extension: File extension (default: .csv).

        Returns:
            Path object for the next file.
        """
        # Ensure directory exists
        directory = Path(self.directory)
        directory.mkdir(parents=True, exist_ok=True)

        if self.naming_mode == "counter":
            # Counter-based naming: basename_001.csv
            while True:
                filename = f"{self.base_name}_{self.counter:03d}{extension}"
                filepath = directory / filename

                if not filepath.exists():
                    # Increment counter for next time
                    self._counter_spin.setValue(self.counter + 1)
                    return filepath

                # File exists, try next counter
                self._counter_spin.setValue(self.counter + 1)
        else:
            # Timestamp-based naming: basename_20240115_143022.csv
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.base_name}_{timestamp}{extension}"
            return directory / filename

    def get_metadata(self) -> dict:
        """Get current metadata as a dictionary.

        Returns:
            Dictionary with metadata fields.
        """
        return {
            "sample_id": self.sample_id,
            "operator": self.operator,
            "timestamp": datetime.now().isoformat(),
        }
