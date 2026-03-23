"""TAScanConfigWidget — delay list builder and scan configuration panel.

Provides a QTabWidget with four delay modes:
- Linear: start, end, step
- Log: start, end, points/decade
- Custom: multi-segment table (linear or log segments)
- Manual: free-text list of delays

Common fields: n_averages, n_scans, acquisition_mode, scan_direction, sample_name.
A preview label shows the total number of delay points.
Save/load config via YAML using ``TAScanConfig.to_yaml`` / ``from_yaml``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from andor_qt.ta.scan_config import (
    TAScanConfig,
    custom_delays,
    linear_delays,
    log_delays,
    manual_delays,
)
from andor_qt.widgets.hardware.camera_settings import CameraSettingsWidget

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class TAScanConfigWidget(QGroupBox):
    """Scan configuration widget for transient absorption measurements.

    Emits ``scan_requested(TAScanConfig)`` when the Start Scan button is clicked.
    """

    scan_requested = Signal(object)  # TAScanConfig

    def __init__(self, parent=None):
        super().__init__("TA Scan Configuration", parent)
        self._build_ui()
        self._update_preview()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- Delay list tab widget ---
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_linear_tab(), "Linear")
        self._tabs.addTab(self._build_log_tab(), "Log")
        self._tabs.addTab(self._build_manual_tab(), "Manual")
        self._tabs.currentChanged.connect(self._update_preview)
        root.addWidget(self._tabs)

        # --- Common parameters ---
        common_group = QGroupBox("Scan Parameters")
        form = QFormLayout(common_group)

        self._n_averages_spin = QSpinBox()
        self._n_averages_spin.setRange(1, 1000)
        self._n_averages_spin.setValue(3)
        form.addRow("Averages per point:", self._n_averages_spin)

        self._n_scans_spin = QSpinBox()
        self._n_scans_spin.setRange(1, 1000)
        self._n_scans_spin.setValue(1)
        form.addRow("Number of scans:", self._n_scans_spin)

        self._acq_mode_combo = QComboBox()
        self._acq_mode_combo.addItems(["boxcar", "shot_to_shot"])
        form.addRow("Acquisition mode:", self._acq_mode_combo)

        self._scan_dir_combo = QComboBox()
        self._scan_dir_combo.addItems(["forward", "alternating"])
        form.addRow("Scan direction:", self._scan_dir_combo)

        self._sample_name_edit = QLineEdit()
        self._sample_name_edit.setPlaceholderText("sample_name")
        form.addRow("Sample name:", self._sample_name_edit)

        root.addWidget(common_group)

        # --- Camera settings ---
        self._camera_settings = CameraSettingsWidget()
        root.addWidget(self._camera_settings)

        # --- Preview label ---
        self._preview_label = QLabel("0 delay points")
        root.addWidget(self._preview_label)

        # --- Action buttons ---
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save Config")
        self._load_btn = QPushButton("Load Config")
        self._scan_btn = QPushButton("Start Scan")

        self._save_btn.clicked.connect(self._on_save)
        self._load_btn.clicked.connect(self._on_load)
        self._scan_btn.clicked.connect(self._on_start_scan)

        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._load_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._scan_btn)
        root.addLayout(btn_row)

    def _build_linear_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._lin_start = QDoubleSpinBox()
        self._lin_start.setRange(-1e6, 1e6)
        self._lin_start.setValue(0.0)
        form.addRow("Start (ps):", self._lin_start)

        self._lin_end = QDoubleSpinBox()
        self._lin_end.setRange(-1e6, 1e6)
        self._lin_end.setValue(100.0)
        form.addRow("End (ps):", self._lin_end)

        self._lin_step = QDoubleSpinBox()
        self._lin_step.setRange(0.001, 1e5)
        self._lin_step.setValue(1.0)
        form.addRow("Step (ps):", self._lin_step)

        for spin in (self._lin_start, self._lin_end, self._lin_step):
            spin.valueChanged.connect(self._update_preview)

        return w

    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._log_start = QDoubleSpinBox()
        self._log_start.setRange(0.001, 1e6)
        self._log_start.setValue(0.1)
        form.addRow("Start (ps):", self._log_start)

        self._log_end = QDoubleSpinBox()
        self._log_end.setRange(0.001, 1e6)
        self._log_end.setValue(1000.0)
        form.addRow("End (ps):", self._log_end)

        self._log_ppd = QSpinBox()
        self._log_ppd.setRange(1, 100)
        self._log_ppd.setValue(5)
        form.addRow("Points/decade:", self._log_ppd)

        for spin in (self._log_start, self._log_end, self._log_ppd):
            spin.valueChanged.connect(self._update_preview)

        return w

    def _build_manual_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Enter delays (ps), one per line or comma-separated:"))
        self._manual_text = QTextEdit()
        self._manual_text.setPlaceholderText("0\n1\n5\n10\n50\n100")
        self._manual_text.textChanged.connect(self._update_preview)
        layout.addWidget(self._manual_text)
        return w

    def _get_delay_list(self) -> List[float]:
        tab = self._tabs.currentIndex()
        try:
            if tab == 0:  # Linear
                return linear_delays(
                    self._lin_start.value(),
                    self._lin_end.value(),
                    self._lin_step.value(),
                )
            elif tab == 1:  # Log
                return log_delays(
                    self._log_start.value(),
                    self._log_end.value(),
                    self._log_ppd.value(),
                )
            else:  # Manual
                text = self._manual_text.toPlainText()
                values = []
                for part in text.replace(",", "\n").split("\n"):
                    part = part.strip()
                    if part:
                        values.append(float(part))
                return manual_delays(values)
        except Exception as exc:
            log.warning(f"Delay list error: {exc}")
            return []

    def _update_preview(self) -> None:
        delays = self._get_delay_list()
        self._preview_label.setText(f"{len(delays)} delay points")

    def _build_config(self) -> TAScanConfig:
        return TAScanConfig(
            delay_list=self._get_delay_list(),
            n_averages=self._n_averages_spin.value(),
            n_scans=self._n_scans_spin.value(),
            acquisition_mode=self._acq_mode_combo.currentText(),
            scan_direction=self._scan_dir_combo.currentText(),
            sample_name=self._sample_name_edit.text(),
        )

    def _on_start_scan(self) -> None:
        config = self._build_config()
        self.scan_requested.emit(config)

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Config", "", "YAML files (*.yaml *.yml)"
        )
        if path:
            self.save_config(path)

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Config", "", "YAML files (*.yaml *.yml)"
        )
        if path:
            self.load_config(path)

    def save_config(self, path: str) -> None:
        """Save current configuration to YAML file."""
        self._build_config().to_yaml(path)

    def load_config(self, path: str) -> None:
        """Load configuration from YAML file and update UI."""
        config = TAScanConfig.from_yaml(path)
        self._n_averages_spin.setValue(config.n_averages)
        self._n_scans_spin.setValue(config.n_scans)
        idx = self._acq_mode_combo.findText(config.acquisition_mode)
        if idx >= 0:
            self._acq_mode_combo.setCurrentIndex(idx)
        idx = self._scan_dir_combo.findText(config.scan_direction)
        if idx >= 0:
            self._scan_dir_combo.setCurrentIndex(idx)
        self._sample_name_edit.setText(config.sample_name or "")
        self._update_preview()

    # -- properties for test access ----------------------------------------

    @property
    def n_averages_spin(self) -> QSpinBox:
        return self._n_averages_spin

    @property
    def n_scans_spin(self) -> QSpinBox:
        return self._n_scans_spin

    @property
    def sample_name_edit(self) -> QLineEdit:
        return self._sample_name_edit

    @property
    def preview_label(self) -> QLabel:
        return self._preview_label

    @property
    def scan_button(self) -> QPushButton:
        return self._scan_btn

    @property
    def camera_settings_widget(self) -> CameraSettingsWidget:
        """Get the embedded CameraSettingsWidget."""
        return self._camera_settings

    @property
    def camera_settings(self) -> dict:
        """Get current camera settings as a dict for apply_camera_settings()."""
        return self._camera_settings.get_settings()

    def populate_from_camera(self, camera) -> None:
        """Populate camera-specific options from a live camera instance."""
        self._camera_settings.populate_from_camera(camera)
