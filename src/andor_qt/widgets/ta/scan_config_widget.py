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
    SPEED_OF_LIGHT_MM_PS,
    TAScanConfig,
    linear_delays_um,
    log_delays_um,
    parse_manual_um,
    ps_to_um,
    stage_delays_ps,
    um_to_ps,
)
from andor_qt.widgets.hardware.camera_settings import CameraSettingsWidget

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class TAScanConfigWidget(QGroupBox):
    """Scan configuration widget for transient absorption measurements.

    Emits ``scan_requested(TAScanConfig)`` when the Start Scan button is clicked.
    """

    scan_requested = Signal(object)  # TAScanConfig
    abort_requested = Signal()

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
        self._tabs.addTab(self._build_stage_tab(), "Stage")
        self._tabs.addTab(self._build_linear_tab(), "Linear")
        self._tabs.addTab(self._build_log_tab(), "Log")
        self._tabs.addTab(self._build_manual_tab(), "Manual")
        self._tabs.setCurrentIndex(0)  # default to Stage tab
        self._tabs.currentChanged.connect(self._update_preview)
        left_layout.addWidget(self._tabs)

        # Common parameters
        common_group = QGroupBox("Scan Parameters")
        form = QFormLayout(common_group)

        self._stage_axis_spin = QSpinBox()
        self._stage_axis_spin.setRange(1, 3)
        self._stage_axis_spin.setValue(2)
        form.addRow("ESP302 axis:", self._stage_axis_spin)

        self._n_averages_spin = QSpinBox()
        self._n_averages_spin.setRange(1, 10000)
        self._n_averages_spin.setValue(100)
        form.addRow("Averages per point:", self._n_averages_spin)

        self._n_scans_spin = QSpinBox()
        self._n_scans_spin.setRange(1, 1000)
        self._n_scans_spin.setValue(1)
        form.addRow("Number of scans:", self._n_scans_spin)

        self._acq_mode_combo = QComboBox()
        self._acq_mode_combo.addItems(["boxcar", "shot_to_shot", "chopper_2x2"])
        self._acq_mode_combo.setCurrentIndex(2)  # default to chopper_2x2
        self._acq_mode_combo.currentTextChanged.connect(self._on_acq_mode_changed)
        form.addRow("Acquisition mode:", self._acq_mode_combo)

        self._external_trigger_check = QCheckBox("External camera trigger (DG535/SDG)")
        self._external_trigger_check.setToolTip(
            "Camera trigger is supplied by an external instrument (e.g. DG535).\n"
            "NIDAQChopper500Hz will NOT be started — the NI DAQ is used only for\n"
            "phase reading (P0.0)."
        )
        form.addRow("", self._external_trigger_check)

        self._scan_dir_combo = QComboBox()
        self._scan_dir_combo.addItems(["forward", "alternating"])
        form.addRow("Scan direction:", self._scan_dir_combo)

        self._sample_name_edit = QLineEdit()
        self._sample_name_edit.setPlaceholderText("sample_name")
        form.addRow("Sample name:", self._sample_name_edit)

        # HDF5 save directory
        self._save_hdf5_check = QCheckBox("Save HDF5 data file")
        hdf5_dir_row = QHBoxLayout()
        self._save_hdf5_dir_edit = QLineEdit()
        self._save_hdf5_dir_edit.setPlaceholderText("HDF5 output directory…")
        self._save_hdf5_dir_edit.setEnabled(False)
        self._save_hdf5_dir_btn = QPushButton("…")
        self._save_hdf5_dir_btn.setFixedWidth(28)
        self._save_hdf5_dir_btn.setEnabled(False)
        hdf5_dir_row.addWidget(self._save_hdf5_dir_edit)
        hdf5_dir_row.addWidget(self._save_hdf5_dir_btn)
        form.addRow(self._save_hdf5_check)
        form.addRow("HDF5 directory:", hdf5_dir_row)

        self._save_hdf5_check.toggled.connect(self._save_hdf5_dir_edit.setEnabled)
        self._save_hdf5_check.toggled.connect(self._save_hdf5_dir_btn.setEnabled)
        self._save_hdf5_dir_btn.clicked.connect(self._on_choose_hdf5_dir)

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

        # ---- Right column: camera + spectrograph settings in a scroll area ----
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._camera_settings = CameraSettingsWidget()
        right_layout.addWidget(self._camera_settings)

        # Placeholder for spectrograph control (added when hardware is ready)
        self._spectrograph_placeholder = right_layout
        self._spectrograph_widget = None

        right_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right_widget)
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
        self._abort_btn = QPushButton("Abort Scan")
        self._abort_btn.setEnabled(False)

        self._save_btn.clicked.connect(self._on_save)
        self._load_btn.clicked.connect(self._on_load)
        self._scan_btn.clicked.connect(self._on_start_scan)
        self._abort_btn.clicked.connect(self.abort_requested)

        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._load_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._scan_btn)
        btn_row.addWidget(self._abort_btn)
        root.addLayout(btn_row)

        # Apply defaults for the initial acquisition mode
        self._on_acq_mode_changed(self._acq_mode_combo.currentText())

    def _build_stage_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._stg_start = QDoubleSpinBox()
        self._stg_start.setRange(-200000.0, 200000.0)
        self._stg_start.setDecimals(1)
        self._stg_start.setValue(-57000.0)
        self._stg_start.setSuffix(" \u00b5m")
        form.addRow("Start position:", self._stg_start)

        self._stg_step = QDoubleSpinBox()
        self._stg_step.setRange(0.1, 100000.0)
        self._stg_step.setDecimals(2)
        self._stg_step.setValue(3.0)
        self._stg_step.setSuffix(" \u00b5m")
        form.addRow("Step size:", self._stg_step)

        self._stg_n_steps = QSpinBox()
        self._stg_n_steps.setRange(1, 100000)
        self._stg_n_steps.setValue(400)
        form.addRow("Number of steps:", self._stg_n_steps)

        self._stg_info_label = QLabel()
        self._stg_info_label.setStyleSheet("color: gray; font-size: 10px;")
        self._stg_info_label.setWordWrap(True)
        form.addRow("", self._stg_info_label)

        for spin in (self._stg_start, self._stg_step, self._stg_n_steps):
            spin.valueChanged.connect(self._update_preview)
            spin.valueChanged.connect(self._update_stage_info)
        self._update_stage_info()

        return w

    def _update_stage_info(self) -> None:
        start_um = self._stg_start.value()
        step_um = self._stg_step.value()
        n_steps = self._stg_n_steps.value()
        end_um = start_um + (n_steps - 1) * step_um

        step_ps = um_to_ps(step_um)
        start_ps = um_to_ps(start_um)
        end_ps = um_to_ps(end_um)
        total_ps = end_ps - start_ps

        if abs(step_ps) < 1.0:
            step_str = f"{step_ps * 1000:.2f} fs"
        else:
            step_str = f"{step_ps:.3f} ps"

        self._stg_info_label.setText(
            f"End: {end_um:.1f} \u00b5m\n"
            f"Step: {step_str}  |  "
            f"Range: {start_ps:.2f} to {end_ps:.2f} ps  |  "
            f"Total: {total_ps:.2f} ps"
        )

    def _build_linear_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._lin_start = QDoubleSpinBox()
        self._lin_start.setRange(-200000.0, 200000.0)
        self._lin_start.setDecimals(1)
        self._lin_start.setValue(-57000.0)
        self._lin_start.setSuffix(" \u00b5m")
        form.addRow("Start position:", self._lin_start)

        self._lin_end = QDoubleSpinBox()
        self._lin_end.setRange(-200000.0, 200000.0)
        self._lin_end.setDecimals(1)
        self._lin_end.setValue(-55800.0)
        self._lin_end.setSuffix(" \u00b5m")
        form.addRow("End position:", self._lin_end)

        self._lin_step = QDoubleSpinBox()
        self._lin_step.setRange(0.1, 100000.0)
        self._lin_step.setDecimals(2)
        self._lin_step.setValue(3.0)
        self._lin_step.setSuffix(" \u00b5m")
        form.addRow("Step size:", self._lin_step)

        self._lin_equiv_label = QLabel()
        self._lin_equiv_label.setStyleSheet("color: gray; font-size: 10px;")
        form.addRow("", self._lin_equiv_label)

        for spin in (self._lin_start, self._lin_end, self._lin_step):
            spin.valueChanged.connect(self._update_preview)
            spin.valueChanged.connect(self._update_linear_equiv)
        self._update_linear_equiv()

        return w

    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._log_start = QDoubleSpinBox()
        self._log_start.setRange(0.1, 200000.0)
        self._log_start.setDecimals(1)
        self._log_start.setValue(15.0)
        self._log_start.setSuffix(" \u00b5m")
        form.addRow("Start position:", self._log_start)

        self._log_end = QDoubleSpinBox()
        self._log_end.setRange(0.1, 200000.0)
        self._log_end.setDecimals(1)
        self._log_end.setValue(15000.0)
        self._log_end.setSuffix(" \u00b5m")
        form.addRow("End position:", self._log_end)

        self._log_ppd = QSpinBox()
        self._log_ppd.setRange(1, 100)
        self._log_ppd.setValue(5)
        form.addRow("Points/decade:", self._log_ppd)

        self._log_equiv_label = QLabel()
        self._log_equiv_label.setStyleSheet("color: gray; font-size: 10px;")
        form.addRow("", self._log_equiv_label)

        self._log_warn_label = QLabel()
        self._log_warn_label.setStyleSheet("color: red; font-size: 10px;")
        self._log_warn_label.hide()
        form.addRow("", self._log_warn_label)

        for spin in (self._log_start, self._log_end, self._log_ppd):
            spin.valueChanged.connect(self._update_preview)
            spin.valueChanged.connect(self._update_log_equiv)
        self._update_log_equiv()

        return w

    def _build_manual_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel(
            "Enter stage positions (\u00b5m). Supports range(start, stop, step):"
        ))
        self._manual_text = QTextEdit()
        self._manual_text.setPlaceholderText(
            "range(-57000, -56000, 3)\n"
            "range(-56000, -50000, 10)\n"
            "-49000, -48000\n"
            "# comment lines are ignored"
        )
        self._manual_text.textChanged.connect(self._update_preview)
        layout.addWidget(self._manual_text)
        self._manual_equiv_label = QLabel()
        self._manual_equiv_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self._manual_equiv_label)
        return w

    def _update_linear_equiv(self) -> None:
        start_ps = um_to_ps(self._lin_start.value())
        end_ps = um_to_ps(self._lin_end.value())
        step_ps = um_to_ps(self._lin_step.value())
        if abs(step_ps) < 1.0:
            step_str = f"{step_ps * 1000:.2f} fs"
        else:
            step_str = f"{step_ps:.3f} ps"
        self._lin_equiv_label.setText(
            f"\u2261 {start_ps:.2f} to {end_ps:.2f} ps, step {step_str}"
        )

    def _update_log_equiv(self) -> None:
        start_ps = um_to_ps(self._log_start.value())
        end_ps = um_to_ps(self._log_end.value())
        self._log_equiv_label.setText(
            f"\u2261 {start_ps:.3f} to {end_ps:.2f} ps"
        )
        if start_ps <= 0 or end_ps <= 0:
            self._log_warn_label.setText("Log spacing requires positive ps values")
            self._log_warn_label.show()
        else:
            self._log_warn_label.hide()

    def _on_acq_mode_changed(self, mode: str) -> None:
        """Auto-configure camera when chopper_2x2 mode is selected."""
        is_2x2 = mode == "chopper_2x2"
        self._external_trigger_check.setVisible(is_2x2)
        if is_2x2:
            self._camera_settings.exposure_spin.setValue(0.002)
            idx = self._camera_settings.trigger_mode_combo.findData("fast_external")
            if idx >= 0:
                self._camera_settings.trigger_mode_combo.setCurrentIndex(idx)
            self._camera_settings.vs_speed_combo.setCurrentIndex(0)  # 4.68 µs — fastest, required for 500 Hz

    def _on_choose_hdf5_dir(self) -> None:
        start_dir = self._save_hdf5_dir_edit.text().strip() or ""
        path = QFileDialog.getExistingDirectory(self, "Select HDF5 output directory", start_dir)
        if path:
            self._save_hdf5_dir_edit.setText(path)

    def _on_choose_spectra_dir(self) -> None:
        # Start from last used directory if available
        start_dir = self._save_spectra_dir_edit.text().strip() or ""
        path = QFileDialog.getExistingDirectory(self, "Select spectra output directory", start_dir)
        if path:
            self._save_spectra_dir_edit.setText(path)

    def _get_delay_list(self) -> List[float]:
        tab = self._tabs.currentIndex()
        try:
            if tab == 0:  # Stage (start/step/n_steps in µm)
                return stage_delays_ps(
                    self._stg_start.value(),
                    self._stg_step.value(),
                    self._stg_n_steps.value(),
                )
            elif tab == 1:  # Linear (µm)
                return linear_delays_um(
                    self._lin_start.value(),
                    self._lin_end.value(),
                    self._lin_step.value(),
                )
            elif tab == 2:  # Log (µm)
                return log_delays_um(
                    self._log_start.value(),
                    self._log_end.value(),
                    self._log_ppd.value(),
                )
            elif tab == 3:  # Manual (µm with range syntax)
                text = self._manual_text.toPlainText()
                positions_um = parse_manual_um(text)
                return [um_to_ps(v) for v in positions_um]
        except Exception as exc:
            log.warning(f"Delay list error: {exc}")
            return []
        return []

    def _update_preview(self) -> None:
        delays = self._get_delay_list()
        n = len(delays)
        if n > 1:
            start_um = ps_to_um(delays[0])
            end_um = ps_to_um(delays[-1])
            self._preview_label.setText(
                f"{n} delay points ({start_um:.0f} to {end_um:.0f} \u00b5m)"
            )
        elif n == 1:
            self._preview_label.setText(f"1 delay point ({ps_to_um(delays[0]):.0f} \u00b5m)")
        else:
            self._preview_label.setText("0 delay points")
        # Update manual equiv label if on manual tab
        if self._tabs.currentIndex() == 3 and n > 0:
            self._manual_equiv_label.setText(
                f"{n} positions, {ps_to_um(delays[0]):.0f} to {ps_to_um(delays[-1]):.0f} \u00b5m"
            )
        elif self._tabs.currentIndex() == 3:
            self._manual_equiv_label.setText("")

    def _build_config(self) -> TAScanConfig:
        save_hdf5_dir = None
        if self._save_hdf5_check.isChecked():
            d = self._save_hdf5_dir_edit.text().strip()
            save_hdf5_dir = d if d else None
        save_dir = None
        if self._save_spectra_check.isChecked():
            d = self._save_spectra_dir_edit.text().strip()
            save_dir = d if d else None
        delays = self._get_delay_list()
        # Derive stage fields from delay list for engine/HDF5 metadata
        if delays:
            stage_start = ps_to_um(delays[0])
            stage_step = ps_to_um(delays[1]) - ps_to_um(delays[0]) if len(delays) > 1 else 0.0
            stage_n = len(delays)
        else:
            stage_start = 0.0
            stage_step = 0.0
            stage_n = 0
        return TAScanConfig(
            delay_list=delays,
            n_averages=self._n_averages_spin.value(),
            n_scans=self._n_scans_spin.value(),
            acquisition_mode=self._acq_mode_combo.currentText(),
            external_trigger=self._external_trigger_check.isChecked(),
            scan_direction=self._scan_dir_combo.currentText(),
            sample_name=self._sample_name_edit.text(),
            stage_start_um=stage_start,
            stage_step_um=stage_step,
            stage_n_steps=stage_n,
            stage_axis=self._stage_axis_spin.value(),
            save_hdf5_dir=save_hdf5_dir,
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
        self._external_trigger_check.setChecked(config.external_trigger)
        idx = self._scan_dir_combo.findText(config.scan_direction)
        if idx >= 0:
            self._scan_dir_combo.setCurrentIndex(idx)
        self._sample_name_edit.setText(config.sample_name or "")
        self._stage_axis_spin.setValue(config.stage_axis)
        # Populate Stage tab from config fields
        self._stg_start.setValue(config.stage_start_um)
        self._stg_step.setValue(abs(config.stage_step_um) if config.stage_step_um else 3.0)
        self._stg_n_steps.setValue(config.stage_n_steps)
        self._tabs.setCurrentIndex(0)
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
    def lin_start_spin(self) -> QDoubleSpinBox:
        return self._lin_start

    @property
    def lin_end_spin(self) -> QDoubleSpinBox:
        return self._lin_end

    @property
    def lin_step_spin(self) -> QDoubleSpinBox:
        return self._lin_step

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

    def set_hardware_manager(self, hw_manager) -> None:
        """Add spectrograph control widget once hardware is available.

        The spectrograph widget is synced to the main tab via shared
        hardware signals — changing grating/wavelength in either place
        updates both.
        """
        if self._spectrograph_widget is not None:
            return  # already added
        self._hw_manager = hw_manager
        # Defer creation until spectrograph is actually initialized
        from andor_qt.core.signals import get_hardware_signals
        signals = get_hardware_signals()
        signals.spectrograph_initialized.connect(self._add_spectrograph_widget)

    def _add_spectrograph_widget(self, _info) -> None:
        """Create and insert spectrograph control widget."""
        if self._spectrograph_widget is not None:
            return
        from andor_qt.widgets.hardware.spectrograph_control import SpectrographControlWidget
        self._spectrograph_widget = SpectrographControlWidget(self._hw_manager)
        self._spectrograph_placeholder.insertWidget(
            self._spectrograph_placeholder.count() - 1,
            self._spectrograph_widget,
        )

    def set_scan_running(self, running: bool) -> None:
        """Freeze/unfreeze all inputs during scan."""
        self._scan_btn.setEnabled(not running)
        self._abort_btn.setEnabled(running)
        # Freeze all inputs during acquisition
        self._tabs.setEnabled(not running)
        self._n_averages_spin.setEnabled(not running)
        self._n_scans_spin.setEnabled(not running)
        self._acq_mode_combo.setEnabled(not running)
        self._external_trigger_check.setEnabled(not running)
        self._scan_dir_combo.setEnabled(not running)
        self._sample_name_edit.setEnabled(not running)
        self._save_hdf5_check.setEnabled(not running)
        self._save_spectra_check.setEnabled(not running)
        self._save_btn.setEnabled(not running)
        self._load_btn.setEnabled(not running)
        self._camera_settings.setEnabled(not running)
