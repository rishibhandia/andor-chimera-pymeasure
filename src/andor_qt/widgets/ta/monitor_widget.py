"""TAMonitorWidget — continuous acquisition at a fixed delay for signal optimization.

Provides position control, jog buttons, full camera settings, and start/stop.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from andor_qt.ta.scan_config import um_to_ps, ps_to_um
from andor_qt.widgets.hardware.camera_settings import CameraSettingsWidget

log = logging.getLogger(__name__)


class TAMonitorWidget(QGroupBox):
    """Monitor mode widget for optimizing TA signal at a fixed delay.

    Emits ``monitor_requested(dict)`` with config when Start is clicked.
    """

    monitor_requested = Signal(object)  # dict with settings
    stop_requested = Signal()

    def __init__(self, hw_manager=None, parent=None):
        super().__init__("Monitor Mode", parent)
        self._hw = hw_manager
        self._running = False
        self._jog_buttons = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)

        # --- Position + jog (always visible at top) ---
        pos_group = QGroupBox("Stage Position")
        pos_layout = QVBoxLayout(pos_group)
        pos_layout.setSpacing(4)

        pos_row = QHBoxLayout()
        self._pos_label = QLabel("-- \u00b5m  (-- ps)")
        self._pos_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        pos_row.addWidget(self._pos_label)
        pos_row.addStretch()
        pos_layout.addLayout(pos_row)

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

        # --- Two-column splitter: left = acq params, right = camera settings ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: acquisition parameters
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)

        acq_group = QGroupBox("Acquisition")
        acq_form = QFormLayout(acq_group)

        self._n_avg_spin = QSpinBox()
        self._n_avg_spin.setRange(1, 100000)
        self._n_avg_spin.setValue(100)
        acq_form.addRow("Averages:", self._n_avg_spin)

        self._acq_combo = QComboBox()
        self._acq_combo.addItems(["chopper_2x2", "shot_to_shot", "boxcar"])
        self._acq_combo.currentTextChanged.connect(self._on_acq_mode_changed)
        acq_form.addRow("Mode:", self._acq_combo)

        self._external_trigger_check = QCheckBox("External trigger (SDG)")
        acq_form.addRow("", self._external_trigger_check)

        left_layout.addWidget(acq_group)
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

    def _on_acq_mode_changed(self, mode: str) -> None:
        """Auto-configure camera when mode changes."""
        is_2x2 = mode == "chopper_2x2"
        is_s2s = mode == "shot_to_shot"
        self._external_trigger_check.setVisible(is_2x2)
        if is_2x2:
            self._camera_settings.exposure_spin.setValue(0.002)
            idx = self._camera_settings.trigger_mode_combo.findData("fast_external")
            if idx >= 0:
                self._camera_settings.trigger_mode_combo.setCurrentIndex(idx)
            self._camera_settings.vs_speed_combo.setCurrentIndex(0)
        elif is_s2s:
            self._camera_settings.exposure_spin.setValue(0.0003)
            idx = self._camera_settings.trigger_mode_combo.findData("fast_external")
            if idx >= 0:
                self._camera_settings.trigger_mode_combo.setCurrentIndex(idx)
            self._camera_settings.vs_speed_combo.setCurrentIndex(0)
            crop_idx = self._camera_settings.read_area_combo.findData("crop")
            if crop_idx >= 0:
                self._camera_settings.read_area_combo.setCurrentIndex(crop_idx)

    def _on_jog(self, delta_um: int) -> None:
        if self._hw is None or self._hw.motion_manager is None:
            return
        axis = self._hw.motion_manager.get_axis("delay")
        if axis is None:
            return
        new_mm = axis.position + delta_um / 1000.0
        new_mm = max(axis.position_min, min(new_mm, axis.position_max))
        log.info(f"Jog {delta_um:+d} \u00b5m \u2192 {new_mm:.3f} mm")
        self._hw.set_axis_position("delay", new_mm, units="mm")
        self._update_position()

    def _on_start(self) -> None:
        config = {
            "n_averages": self._n_avg_spin.value(),
            "acq_mode": self._acq_combo.currentText(),
            "external_trigger": self._external_trigger_check.isChecked(),
            "camera_settings": self._camera_settings.get_settings(),
        }
        self.monitor_requested.emit(config)

    def update_position(self) -> None:
        """Update position display from hardware."""
        self._update_position()

    def _update_position(self) -> None:
        if self._hw is None or self._hw.motion_manager is None:
            return
        axis = self._hw.motion_manager.get_axis("delay")
        if axis is None:
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
        self._acq_combo.setEnabled(not running)
        self._external_trigger_check.setEnabled(not running)
        self._camera_settings.setEnabled(not running)
        for btn in self._jog_buttons:
            btn.setEnabled(True)  # jog always enabled for optimization

    @property
    def camera_settings(self) -> dict:
        return self._camera_settings.get_settings()

    @property
    def camera_settings_widget(self) -> CameraSettingsWidget:
        return self._camera_settings
