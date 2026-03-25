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
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
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
    stage_delays_ps,
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

        # Two-column splitter: left = delay + scan params, right = camera settings
        from PySide6.QtCore import Qt
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---- Left column ----
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)

        # Delay list tab widget
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_linear_tab(), "Linear")
        self._tabs.addTab(self._build_log_tab(), "Log")
        self._tabs.addTab(self._build_manual_tab(), "Manual")
        self._tabs.addTab(self._build_stage_tab(), "Stage")
        self._tabs.currentChanged.connect(self._update_preview)
        left_layout.addWidget(self._tabs)

        # Common parameters
        common_group = QGroupBox("Scan Parameters")
        form = QFormLayout(common_group)

        self._n_averages_spin = QSpinBox()
        self._n_averages_spin.setRange(1, 10000)
        self._n_averages_spin.setValue(2000)
        form.addRow("Averages per point:", self._n_averages_spin)

        self._n_scans_spin = QSpinBox()
        self._n_scans_spin.setRange(1, 1000)
        self._n_scans_spin.setValue(1)
        form.addRow("Number of scans:", self._n_scans_spin)

        self._acq_mode_combo = QComboBox()
        self._acq_mode_combo.addItems(["boxcar", "shot_to_shot", "chopper_2x2"])
        self._acq_mode_combo.currentTextChanged.connect(self._on_acq_mode_changed)
        form.addRow("Acquisition mode:", self._acq_mode_combo)

        self._scan_dir_combo = QComboBox()
        self._scan_dir_combo.addItems(["forward", "alternating"])
        form.addRow("Scan direction:", self._scan_dir_combo)

        self._sample_name_edit = QLineEdit()
        self._sample_name_edit.setPlaceholderText("sample_name")
        form.addRow("Sample name:", self._sample_name_edit)

        # Save individual spectra option
        self._save_spectra_check = QCheckBox("Save individual spectra")
        save_dir_row = QHBoxLayout()
        self._save_spectra_dir_edit = QLineEdit()
        self._save_spectra_dir_edit.setPlaceholderText("Output directory…")
        self._save_spectra_dir_edit.setEnabled(False)
        self._save_spectra_dir_btn = QPushButton("…")
        self._save_spectra_dir_btn.setFixedWidth(28)
        self._save_spectra_dir_btn.setEnabled(False)
        save_dir_row.addWidget(self._save_spectra_dir_edit)
        save_dir_row.addWidget(self._save_spectra_dir_btn)
        form.addRow(self._save_spectra_check)
        form.addRow("Spectra directory:", save_dir_row)

        self._save_spectra_check.toggled.connect(self._save_spectra_dir_edit.setEnabled)
        self._save_spectra_check.toggled.connect(self._save_spectra_dir_btn.setEnabled)
        self._save_spectra_dir_btn.clicked.connect(self._on_choose_spectra_dir)

        left_layout.addWidget(common_group)
        left_layout.addStretch()
        splitter.addWidget(left_widget)

        # ---- Right column: camera settings in a scroll area ----
        self._camera_settings = CameraSettingsWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._camera_settings)
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

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

    def _build_stage_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._stage_axis_spin = QSpinBox()
        self._stage_axis_spin.setRange(1, 3)
        self._stage_axis_spin.setValue(2)
        form.addRow("ESP302 axis:", self._stage_axis_spin)

        self._stage_start_spin = QDoubleSpinBox()
        self._stage_start_spin.setRange(-200000.0, 200000.0)
        self._stage_start_spin.setDecimals(1)
        self._stage_start_spin.setValue(-57000.0)
        self._stage_start_spin.setSuffix(" µm")
        form.addRow("Start position:", self._stage_start_spin)

        self._stage_step_spin = QDoubleSpinBox()
        self._stage_step_spin.setRange(0.1, 10000.0)
        self._stage_step_spin.setDecimals(2)
        self._stage_step_spin.setValue(3.0)
        self._stage_step_spin.setSuffix(" µm")
        form.addRow("Step size:", self._stage_step_spin)

        self._stage_n_steps_spin = QSpinBox()
        self._stage_n_steps_spin.setRange(1, 10000)
        self._stage_n_steps_spin.setValue(400)
        form.addRow("Number of steps:", self._stage_n_steps_spin)

        for spin in (self._stage_start_spin, self._stage_step_spin, self._stage_n_steps_spin):
            spin.valueChanged.connect(self._update_preview)

        return w

    def _on_acq_mode_changed(self, mode: str) -> None:
        """Auto-configure camera when chopper_2x2 mode is selected."""
        if mode == "chopper_2x2":
            self._camera_settings.exposure_spin.setValue(0.002)
            idx = self._camera_settings.trigger_mode_combo.findData("fast_external")
            if idx >= 0:
                self._camera_settings.trigger_mode_combo.setCurrentIndex(idx)

    def _on_choose_spectra_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select spectra output directory")
        if path:
            self._save_spectra_dir_edit.setText(path)

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
            elif tab == 2:  # Manual
                text = self._manual_text.toPlainText()
                values = []
                for part in text.replace(",", "\n").split("\n"):
                    part = part.strip()
                    if part:
                        values.append(float(part))
                return manual_delays(values)
            else:  # Stage (tab == 3)
                return stage_delays_ps(
                    self._stage_start_spin.value(),
                    self._stage_step_spin.value(),
                    self._stage_n_steps_spin.value(),
                )
        except Exception as exc:
            log.warning(f"Delay list error: {exc}")
            return []

    def _update_preview(self) -> None:
        delays = self._get_delay_list()
        self._preview_label.setText(f"{len(delays)} delay points")

    def _build_config(self) -> TAScanConfig:
        save_dir = None
        if self._save_spectra_check.isChecked():
            d = self._save_spectra_dir_edit.text().strip()
            save_dir = d if d else None
        return TAScanConfig(
            delay_list=self._get_delay_list(),
            n_averages=self._n_averages_spin.value(),
            n_scans=self._n_scans_spin.value(),
            acquisition_mode=self._acq_mode_combo.currentText(),
            scan_direction=self._scan_dir_combo.currentText(),
            sample_name=self._sample_name_edit.text(),
            stage_start_um=self._stage_start_spin.value(),
            stage_step_um=self._stage_step_spin.value(),
            stage_n_steps=self._stage_n_steps_spin.value(),
            stage_axis=self._stage_axis_spin.value(),
            save_spectra_dir=save_dir,
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
    def stage_axis_spin(self) -> QSpinBox:
        return self._stage_axis_spin

    @property
    def stage_start_spin(self) -> QDoubleSpinBox:
        return self._stage_start_spin

    @property
    def stage_step_spin(self) -> QDoubleSpinBox:
        return self._stage_step_spin

    @property
    def stage_n_steps_spin(self) -> QSpinBox:
        return self._stage_n_steps_spin

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
