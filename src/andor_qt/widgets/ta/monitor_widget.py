"""TAMonitorWidget — continuous acquisition at a fixed delay for signal optimization.

Provides position control, jog buttons, full camera settings, and start/stop.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSettings, Qt, Signal
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
    QVBoxLayout,
    QWidget,
)

from andor_qt.ta.scan_config import TAScanConfig, um_to_ps, ps_to_um
from andor_qt.widgets.hardware.camera_settings import CameraSettingsWidget

log = logging.getLogger(__name__)


class TAMonitorWidget(QGroupBox):
    """Monitor mode widget for optimizing TA signal at a fixed delay.

    Emits ``monitor_requested(TAScanConfig)`` when Start is clicked.
    Emits ``static_acquire_requested(str, TAScanConfig)`` for static ON/OFF.
    """

    monitor_requested = Signal(object)  # TAScanConfig
    static_acquire_requested = Signal(str, object)  # (phase, TAScanConfig)
    stop_requested = Signal()
    dark_requested = Signal(object)  # TAScanConfig
    dark_cleared = Signal()

    def __init__(self, hw_manager=None, parent=None):
        super().__init__("Monitor Mode", parent)
        self._hw = hw_manager
        self._running = False
        self._jog_buttons = []
        self._build_ui()
        self._load_settings()
        self._connect_autosave()

    def _connect_autosave(self) -> None:
        """Auto-save settings whenever any control changes."""
        self._acq_combo.currentIndexChanged.connect(self._save_settings)
        self._shots_per_frame_spin.valueChanged.connect(self._save_settings)
        self._avg_mode_combo.currentIndexChanged.connect(self._save_settings)
        self._n_avg_spin.valueChanged.connect(self._save_settings)
        self._avg_time_spin.valueChanged.connect(self._save_settings)
        self._save_dir_edit.textChanged.connect(self._save_settings)
        self._save_prefix_edit.textChanged.connect(self._save_settings)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)

        # --- Position + jog (always visible at top) ---
        pos_group = QGroupBox("Stage Position")
        pos_layout = QVBoxLayout(pos_group)
        pos_layout.setSpacing(4)

        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("Axis:"))
        self._axis_combo = QComboBox()
        self._axis_combo.setMinimumWidth(100)
        self._axis_combo.currentIndexChanged.connect(lambda: self._update_position())
        axis_row.addWidget(self._axis_combo)
        axis_row.addStretch()
        self._pos_label = QLabel("-- \u00b5m  (-- ps)")
        self._pos_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        axis_row.addWidget(self._pos_label)

        self._refresh_btn = QPushButton("\u21bb")  # ↻ refresh symbol
        self._refresh_btn.setFixedWidth(28)
        self._refresh_btn.setToolTip("Refresh position from hardware")
        self._refresh_btn.clicked.connect(self._update_position)
        axis_row.addWidget(self._refresh_btn)

        pos_layout.addLayout(axis_row)

        jog_row = QHBoxLayout()
        jog_row.addWidget(QLabel("Jog:"))
        for delta_um in [-100, -10, -1, 1, 10, 100]:
            sign = "+" if delta_um > 0 else ""
            btn = QPushButton(f"{sign}{delta_um}")
            btn.setFixedWidth(45)
            btn.clicked.connect(lambda checked, d=delta_um: self._on_jog(d))
            jog_row.addWidget(btn)
            self._jog_buttons.append(btn)
        jog_row.addWidget(QLabel("\u00b5m"))
        jog_row.addStretch()
        pos_layout.addLayout(jog_row)

        root.addWidget(pos_group)

        # Populate axes if hardware is available
        self._populate_axes()
        # Connect to hardware signals for live position updates
        if self._hw:
            from andor_qt.core.signals import get_hardware_signals
            signals = get_hardware_signals()
            signals.motion_initialized.connect(lambda _: self._populate_axes())
            signals.axis_position_changed.connect(self._on_axis_position_changed)

        # --- Two-column splitter: left = acq params, right = camera settings ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: acquisition parameters
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)

        acq_group = QGroupBox("Acquisition")
        acq_form = QFormLayout(acq_group)

        self._acq_combo = QComboBox()
        self._acq_combo.addItems(["chopper_2x2", "shot_to_shot", "boxcar", "static_onoff"])
        self._acq_combo.currentTextChanged.connect(self._on_acq_mode_changed)
        acq_form.addRow("Mode:", self._acq_combo)

        self._shots_per_frame_spin = QSpinBox()
        self._shots_per_frame_spin.setRange(1, 10)
        self._shots_per_frame_spin.setValue(2)
        self._shots_per_frame_spin.setToolTip("Laser shots per camera frame (2=500Hz, 4=250Hz)")
        acq_form.addRow("Shots/frame:", self._shots_per_frame_spin)

        self._external_trigger_check = QCheckBox("External trigger (SDG)")
        acq_form.addRow("", self._external_trigger_check)

        # Averaging: by count or by time
        self._avg_mode_combo = QComboBox()
        self._avg_mode_combo.addItems(["By count", "By time"])
        self._avg_mode_combo.currentIndexChanged.connect(self._on_avg_mode_changed)
        acq_form.addRow("Averaging:", self._avg_mode_combo)

        self._n_avg_spin = QSpinBox()
        self._n_avg_spin.setRange(1, 10000000)
        self._n_avg_spin.setValue(100)
        self._n_avg_row_label = QLabel("Pairs:")
        acq_form.addRow(self._n_avg_row_label, self._n_avg_spin)

        self._avg_time_spin = QDoubleSpinBox()
        self._avg_time_spin.setRange(0.1, 600.0)
        self._avg_time_spin.setValue(10.0)
        self._avg_time_spin.setSuffix(" s")
        self._avg_time_spin.setDecimals(1)
        self._avg_time_label = QLabel("Duration:")
        acq_form.addRow(self._avg_time_label, self._avg_time_spin)

        self._avg_info_label = QLabel()
        self._avg_info_label.setStyleSheet("color: gray; font-size: 10px;")
        acq_form.addRow("", self._avg_info_label)

        self._n_avg_spin.valueChanged.connect(self._update_avg_info)
        self._avg_time_spin.valueChanged.connect(self._update_avg_info)
        self._on_avg_mode_changed(0)  # init visibility

        left_layout.addWidget(acq_group)

        # --- Static ON/OFF buttons ---
        self._static_group = QGroupBox("Static ON/OFF")
        static_layout = QVBoxLayout(self._static_group)

        static_btn_row = QHBoxLayout()
        self._acq_pump_btn = QPushButton("Acquire Pump ON (pump+probe)")
        self._acq_ref_btn = QPushButton("Acquire Pump OFF (probe only)")
        self._acq_pump_btn.clicked.connect(lambda: self._on_static_acquire("pump"))
        self._acq_ref_btn.clicked.connect(lambda: self._on_static_acquire("ref"))
        static_btn_row.addWidget(self._acq_pump_btn)
        static_btn_row.addWidget(self._acq_ref_btn)
        static_layout.addLayout(static_btn_row)

        self._static_status = QLabel("No data collected")
        self._static_status.setStyleSheet("color: gray; font-size: 10px;")
        static_layout.addWidget(self._static_status)

        left_layout.addWidget(self._static_group)
        self._static_group.setVisible(False)  # shown only for static_onoff mode

        # --- Dark Frame ---
        dark_group = QGroupBox("Dark Frame")
        dark_layout = QVBoxLayout(dark_group)
        dark_btn_row = QHBoxLayout()
        self._acquire_dark_btn = QPushButton("Acquire Dark")
        self._acquire_dark_btn.setToolTip("Acquire dark baseline (shutter closed)")
        self._acquire_dark_btn.clicked.connect(self._on_acquire_dark)
        dark_btn_row.addWidget(self._acquire_dark_btn)
        self._clear_dark_btn = QPushButton("Clear Dark")
        self._clear_dark_btn.setToolTip("Remove stored dark frame")
        self._clear_dark_btn.clicked.connect(self._on_clear_dark)
        self._clear_dark_btn.setEnabled(False)
        dark_btn_row.addWidget(self._clear_dark_btn)
        dark_layout.addLayout(dark_btn_row)
        self._dark_status_label = QLabel("No dark frame")
        self._dark_status_label.setStyleSheet("color: gray; font-size: 10px;")
        dark_layout.addWidget(self._dark_status_label)
        left_layout.addWidget(dark_group)

        left_layout.addStretch()
        splitter.addWidget(left)

        # Right: camera settings in scroll area
        self._camera_settings = CameraSettingsWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._camera_settings)
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        # --- Save directory + spectrum buttons ---
        save_group = QGroupBox("Save Spectra")
        save_layout = QVBoxLayout(save_group)
        save_layout.setSpacing(4)

        dir_row = QHBoxLayout()
        self._save_dir_edit = QLineEdit()
        self._save_dir_edit.setPlaceholderText("Output directory...")
        self._save_dir_btn = QPushButton("\u2026")
        self._save_dir_btn.setFixedWidth(28)
        self._save_dir_btn.clicked.connect(self._on_choose_save_dir)
        dir_row.addWidget(self._save_dir_edit)
        dir_row.addWidget(self._save_dir_btn)
        save_layout.addLayout(dir_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Prefix:"))
        self._save_prefix_edit = QLineEdit()
        self._save_prefix_edit.setPlaceholderText("sample_name")
        self._save_prefix_edit.setText("monitor")
        name_row.addWidget(self._save_prefix_edit)
        save_layout.addLayout(name_row)

        btn_row2 = QHBoxLayout()
        self._save_pump_btn = QPushButton("Pump ON")
        self._save_ref_btn = QPushButton("Pump OFF")
        self._save_diff_btn = QPushButton("Diff (ON\u2212OFF)")
        self._save_delta_btn = QPushButton("\u0394I/I\u2080")
        for btn in (self._save_pump_btn, self._save_ref_btn, self._save_diff_btn, self._save_delta_btn):
            btn.setFixedWidth(90)
        self._save_pump_btn.clicked.connect(lambda: self._on_save_spectrum("pump"))
        self._save_ref_btn.clicked.connect(lambda: self._on_save_spectrum("ref"))
        self._save_diff_btn.clicked.connect(lambda: self._on_save_spectrum("diff"))
        self._save_delta_btn.clicked.connect(lambda: self._on_save_spectrum("delta"))
        btn_row2.addWidget(self._save_pump_btn)
        btn_row2.addWidget(self._save_ref_btn)
        btn_row2.addWidget(self._save_diff_btn)
        btn_row2.addWidget(self._save_delta_btn)
        btn_row2.addStretch()
        save_layout.addLayout(btn_row2)

        root.addWidget(save_group)

        # --- Start/Stop ---
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("Start Monitor")
        self._stop_btn = QPushButton("Stop Monitor")
        self._stop_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._on_start)
        self._stop_btn.clicked.connect(self.stop_requested)
        btn_row.addStretch()
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)
        root.addLayout(btn_row)

        # Set initial mode
        self._on_acq_mode_changed(self._acq_combo.currentText())

    def _on_avg_mode_changed(self, index: int) -> None:
        """Toggle between count-based and time-based averaging."""
        by_time = index == 1
        self._n_avg_spin.setVisible(not by_time)
        self._n_avg_row_label.setVisible(not by_time)
        self._avg_time_spin.setVisible(by_time)
        self._avg_time_label.setVisible(by_time)
        self._update_avg_info()

    def _update_avg_info(self) -> None:
        """Show estimated duration or pair count based on camera settings."""
        from andor_qt.ta.acquisition import _compute_frame_period_s

        if not hasattr(self, "_camera_settings"):
            return  # widget still being built
        camera_settings = self._camera_settings.get_settings()
        frame_period = _compute_frame_period_s(camera_settings)
        mode = self._acq_combo.currentText()
        is_static = mode == "static_onoff"

        # Static: 1 frame per sample; alternating: 2 frames per pair
        frames_per_avg = 1 if is_static else 2

        if self._avg_mode_combo.currentIndex() == 0:
            # By count → show estimated duration
            n = self._n_avg_spin.value()
            t = n * frames_per_avg * frame_period
            if t < 60:
                self._avg_info_label.setText(f"\u2248 {t:.1f} s")
            else:
                self._avg_info_label.setText(f"\u2248 {t/60:.1f} min")
        else:
            # By time → show estimated pairs/frames
            t = self._avg_time_spin.value()
            n = int(t / (frames_per_avg * frame_period))
            label = "frames" if is_static else "pairs"
            self._avg_info_label.setText(f"\u2248 {n:,} {label}")

    def _get_n_averages(self) -> int:
        """Get effective n_averages from either count or time mode."""
        if self._avg_mode_combo.currentIndex() == 0:
            return self._n_avg_spin.value()
        else:
            from andor_qt.ta.acquisition import _compute_frame_period_s
            camera_settings = self._camera_settings.get_settings()
            frame_period = _compute_frame_period_s(camera_settings)
            mode = self._acq_combo.currentText()
            frames_per_avg = 1 if mode == "static_onoff" else 2
            t = self._avg_time_spin.value()
            return max(1, int(t / (frames_per_avg * frame_period)))

    def _on_static_acquire(self, phase: str) -> None:
        config = TAScanConfig(
            delay_list=[0.0],
            n_averages=self._get_n_averages(),
            acquisition_mode="static_onoff",
            scan_direction="forward",
            sample_name=f"static_{phase}",
            external_trigger=self._external_trigger_check.isChecked(),
        )
        self.static_acquire_requested.emit(phase, config)

    def update_static_status(self, pump_done: bool, ref_done: bool,
                             pump_time: str = "", ref_time: str = "") -> None:
        """Update the static ON/OFF status label with collection timestamps."""
        parts = []
        if pump_done:
            parts.append(f"Pump ON: collected {pump_time}")
        else:
            parts.append("Pump ON: --")
        if ref_done:
            parts.append(f"Pump OFF: collected {ref_time}")
        else:
            parts.append("Pump OFF: --")
        self._static_status.setText("  |  ".join(parts))

    def _on_acq_mode_changed(self, mode: str) -> None:
        """Auto-configure camera when mode changes."""
        is_static = mode == "static_onoff"
        self._external_trigger_check.setVisible(mode == "chopper_2x2")
        if mode != "chopper_2x2":
            self._external_trigger_check.setChecked(False)
        self._static_group.setVisible(is_static)
        self._start_btn.setVisible(not is_static)
        self._stop_btn.setVisible(True)
        self._update_avg_info()
        if mode in ("chopper_2x2", "shot_to_shot", "static_onoff"):
            self._camera_settings.apply_mode_preset(mode)
        if is_static:
            self._avg_mode_combo.setCurrentIndex(1)  # By time
            self._avg_time_spin.setValue(300.0)  # 5 min

    def _populate_axes(self) -> None:
        """Populate axis selector from motion manager."""
        self._axis_combo.blockSignals(True)
        self._axis_combo.clear()
        if self._hw and self._hw.motion_manager:
            for name in self._hw.motion_manager.all_axes:
                self._axis_combo.addItem(name, name)
        self._axis_combo.blockSignals(False)
        self._update_position()

    def _get_selected_axis_name(self) -> str:
        return self._axis_combo.currentData() or "delay"

    def _get_selected_axis(self):
        if self._hw is None or self._hw.motion_manager is None:
            return None
        return self._hw.motion_manager.get_axis(self._get_selected_axis_name())

    def _on_axis_position_changed(self, axis_name: str, position: float) -> None:
        if axis_name == self._get_selected_axis_name():
            self._update_position()

    def _on_jog(self, delta_um: int) -> None:
        axis = self._get_selected_axis()
        if axis is None:
            return
        axis_name = self._get_selected_axis_name()
        new_mm = axis.position + delta_um / 1000.0
        new_mm = max(axis.position_min, min(new_mm, axis.position_max))
        log.info(f"Jog {axis_name} {delta_um:+d} \u00b5m \u2192 {new_mm:.3f} mm")
        self._hw.set_axis_position(axis_name, new_mm, units="mm")
        self._update_position()

    def _on_start(self) -> None:
        self._save_settings()
        camera_settings = self._camera_settings.get_settings()
        crop_height = (
            camera_settings.get("crop_height", 50)
            if camera_settings.get("read_area_mode") == "crop"
            else 50
        )
        config = TAScanConfig(
            delay_list=[0.0],
            n_averages=self._get_n_averages(),
            acquisition_mode=self._acq_combo.currentText(),
            scan_direction="forward",
            sample_name="monitor",
            shots_per_frame=self._shots_per_frame_spin.value(),
            external_trigger=self._external_trigger_check.isChecked(),
            crop_height=crop_height,
        )
        self.monitor_requested.emit(config)

    def _on_acquire_dark(self) -> None:
        """Emit dark_requested with a TAScanConfig for dark frame acquisition."""
        config = TAScanConfig(
            delay_list=[0.0],
            n_averages=self._get_n_averages(),
            acquisition_mode=self._acq_combo.currentText(),
            scan_direction="forward",
            sample_name="dark",
            external_trigger=self._external_trigger_check.isChecked(),
        )
        self.dark_requested.emit(config)

    def _on_clear_dark(self) -> None:
        """Emit dark_cleared signal."""
        self._dark_status_label.setText("No dark frame")
        self._clear_dark_btn.setEnabled(False)
        self.dark_cleared.emit()

    def set_dark_status(self, text: str) -> None:
        """Update the dark frame status label."""
        self._dark_status_label.setText(text)
        self._clear_dark_btn.setEnabled(True)

    def cache_raw_data(
        self,
        pump: "np.ndarray",
        ref: "np.ndarray",
        n_on: int = 0,
        n_off: int = 0,
        wavelengths: "np.ndarray | None" = None,
    ) -> None:
        """Store raw pump/ref spectra for save buttons.

        Args:
            pump: Averaged pump-ON spectrum.
            ref: Averaged pump-OFF spectrum.
            n_on: Number of pump-ON frames.
            n_off: Number of pump-OFF frames.
            wavelengths: Wavelength calibration array (or None for pixel mode).
        """
        import numpy as np
        from datetime import datetime
        self._last_pump = np.asarray(pump).copy()
        self._last_ref = np.asarray(ref).copy()
        self._last_n_on = n_on
        self._last_n_off = n_off
        self._last_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._last_wavelengths = np.asarray(wavelengths) if wavelengths is not None else None

    # -- Persistent settings (QSettings) -------------------------------------

    def _save_settings(self) -> None:
        """Persist current widget values to QSettings."""
        s = QSettings("AndorSpectrometer", "TAMonitor")
        s.setValue("acq_mode", self._acq_combo.currentText())
        s.setValue("shots_per_frame", self._shots_per_frame_spin.value())
        # external_trigger NOT persisted — defaults to unchecked each session
        s.setValue("avg_mode", self._avg_mode_combo.currentIndex())
        s.setValue("n_averages", self._n_avg_spin.value())
        s.setValue("avg_time", self._avg_time_spin.value())
        s.setValue("save_dir", self._save_dir_edit.text())
        s.setValue("save_prefix", self._save_prefix_edit.text())

    def _load_settings(self) -> None:
        """Restore widget values from QSettings (if any)."""
        s = QSettings("AndorSpectrometer", "TAMonitor")
        acq = s.value("acq_mode")
        if acq is not None:
            idx = self._acq_combo.findText(str(acq))
            if idx >= 0:
                self._acq_combo.setCurrentIndex(idx)
        spf = s.value("shots_per_frame")
        if spf is not None:
            self._shots_per_frame_spin.setValue(int(spf))
        # external_trigger is NOT restored from QSettings — it defaults to
        # unchecked each session to prevent accidental NIDAQChopper500Hz bypass
        avg_mode = s.value("avg_mode")
        if avg_mode is not None:
            self._avg_mode_combo.setCurrentIndex(int(avg_mode))
        n_avg = s.value("n_averages")
        if n_avg is not None:
            self._n_avg_spin.setValue(int(n_avg))
        avg_time = s.value("avg_time")
        if avg_time is not None:
            self._avg_time_spin.setValue(float(avg_time))
        save_dir = s.value("save_dir")
        if save_dir:
            self._save_dir_edit.setText(str(save_dir))
        prefix = s.value("save_prefix")
        if prefix:
            self._save_prefix_edit.setText(str(prefix))

    def update_position(self) -> None:
        """Update position display from hardware."""
        self._update_position()

    def _update_position(self) -> None:
        axis = self._get_selected_axis()
        if axis is None:
            self._pos_label.setText("-- \u00b5m  (-- ps)")
            return
        pos_um = axis.position * 1000
        pos_ps = getattr(axis, "position_ps", 0.0)
        self._pos_label.setText(f"{pos_um:.1f} \u00b5m  ({pos_ps:.2f} ps)")

    def populate_from_camera(self, camera) -> None:
        """Populate camera-specific options from a live camera instance."""
        self._camera_settings.populate_from_camera(camera)

    def set_monitor_running(self, running: bool) -> None:
        self._running = running
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._n_avg_spin.setEnabled(not running)
        self._avg_time_spin.setEnabled(not running)
        self._avg_mode_combo.setEnabled(not running)
        self._acq_combo.setEnabled(not running)
        self._external_trigger_check.setEnabled(not running)
        self._camera_settings.setEnabled(not running)
        for btn in self._jog_buttons:
            btn.setEnabled(True)  # jog always enabled for optimization

    def _on_choose_save_dir(self) -> None:
        start_dir = self._save_dir_edit.text().strip() or ""
        path = QFileDialog.getExistingDirectory(self, "Select output directory", start_dir)
        if path:
            self._save_dir_edit.setText(path)

    def _on_save_spectrum(self, spec_type: str) -> None:
        """Save the last acquired spectrum to a text file in the output directory."""
        from pathlib import Path
        from datetime import datetime
        import numpy as _np

        pump = getattr(self, "_last_pump", None)
        ref = getattr(self, "_last_ref", None)
        n_on = getattr(self, "_last_n_on", 0)
        n_off = getattr(self, "_last_n_off", 0)

        if pump is None or ref is None:
            log.warning("No acquisition data to save — run monitor first")
            return

        if spec_type == "pump":
            data = pump
            label = "pump_ON"
        elif spec_type == "ref":
            data = ref
            label = "pump_OFF"
        elif spec_type == "diff":
            data = pump - ref
            label = "diff_ON-OFF"
        elif spec_type == "delta":
            ref_safe = _np.where(ref == 0, 1.0, ref)
            data = (pump - ref) / ref_safe
            label = "deltaI_I0"
        else:
            data = None
            label = spec_type

        if data is None:
            log.warning(f"No {spec_type} data available")
            return

        # Use cached wavelengths (matched to data length at acquisition time)
        wavelengths = getattr(self, "_last_wavelengths", None)
        if wavelengths is None or len(wavelengths) != len(data):
            log.warning("Wavelength calibration missing or mismatched — saving as pixel indices")

        # Determine save path with auto-increment
        save_dir = self._save_dir_edit.text().strip()
        prefix = self._save_prefix_edit.text().strip() or "monitor"
        if save_dir:
            save_path = Path(save_dir)
            save_path.mkdir(parents=True, exist_ok=True)
            # Auto-increment: find next available number
            idx = 1
            while True:
                filepath = save_path / f"{prefix}_{idx:04d}_{label}.txt"
                if not filepath.exists():
                    break
                idx += 1
        else:
            filepath, _ = QFileDialog.getSaveFileName(
                self, f"Save {label} spectrum", f"{prefix}_{label}.txt",
                "Text files (*.txt);;All files (*)"
            )
            if not filepath:
                return
            filepath = Path(filepath)

        lines = []
        if wavelengths is not None and len(wavelengths) == len(data):
            for wl, d in zip(wavelengths, data):
                lines.append(f"{float(wl):.4f}\t{float(d):.8e}")
        else:
            for i, d in enumerate(data):
                lines.append(f"{i}\t{float(d):.8e}")

        filepath.write_text("\n".join(lines), encoding="utf-8")
        log.info(f"Saved {label} spectrum to {filepath}")

        # Show confirmation to user
        collected_at = getattr(self, "_last_timestamp", "unknown")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "Spectrum Saved",
            f"Saved: {filepath.name}\n"
            f"Directory: {filepath.parent}\n"
            f"Data collected at: {collected_at}\n"
            f"Type: {label}  ({len(data)} points)"
        )

    @property
    def camera_settings(self) -> dict:
        return self._camera_settings.get_settings()

    @property
    def camera_settings_widget(self) -> CameraSettingsWidget:
        return self._camera_settings
