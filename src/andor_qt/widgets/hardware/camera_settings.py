"""CameraSettingsWidget — shared camera acquisition settings panel.

Provides controls for:
- Vertical shift (VS) speed
- Horizontal shift (HS) speed
- Output amplifier (EM / Conventional)
- EM gain (enabled only for EM amplifier)
- Pre-amplifier gain
- Read area mode: Full CCD / Single Track / Crop Mode

Speed labels are hard-coded for the Andor DU970P Newton EMCCD.
Pre-amp gain options are populated at runtime via populate_from_camera().
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from andor_qt.utils.readout_time import VS_SPEEDS_US, HS_RATES_HZ, calculate_readout_time_ms

log = logging.getLogger(__name__)

# DU970P VS speed options: (index, label, µs/pixel)
_VS_SPEEDS = [
    (0, "4.9 µs  (fastest)"),
    (1, "9.8 µs  (recommended)"),
    (2, "19 µs"),
    (3, "38 µs"),
    (4, "57 µs  (slowest)"),
]

# DU970P HS speed options: same for both amplifier types
_HS_SPEEDS = [
    (0, "3 MHz  (fastest)"),
    (1, "1 MHz"),
    (2, "50 kHz  (lowest noise)"),
]


class CameraSettingsWidget(QGroupBox):
    """Shared camera acquisition settings panel for DU970P Newton EMCCD.

    Emits ``settings_changed`` whenever any control is modified.
    Call ``populate_from_camera(camera)`` after hardware init to set
    the correct pre-amp gain options and EM gain range.
    """

    settings_changed = Signal()

    # Actual VS speed values in µs; overwritten by populate_from_camera
    _vs_speeds_us: dict = VS_SPEEDS_US
    # Actual HS rates in Hz; overwritten by populate_from_camera
    _hs_rates_hz: dict = HS_RATES_HZ

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("Camera Settings", parent)
        self._setup_ui()
        self._connect_signals()
        self._on_amplifier_changed(1)       # apply initial enable/disable (default: Conventional)
        self._on_read_area_changed(0)        # show/hide initial groups
        self._update_readout_label()         # initialise readout time display

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # --- Readout speeds ---
        speed_group = QGroupBox("Readout Speeds")
        speed_form = QFormLayout(speed_group)
        speed_form.setSpacing(4)

        self.amplifier_combo = QComboBox()
        self.amplifier_combo.addItem("EM (EMCCD)", 0)
        self.amplifier_combo.addItem("Conventional CCD", 1)
        self.amplifier_combo.setCurrentIndex(1)  # default: Conventional (no EM gain)
        speed_form.addRow("Amplifier:", self.amplifier_combo)

        self.hs_speed_combo = QComboBox()
        self._populate_hs_speeds(amplifier_type=0)
        speed_form.addRow("HS Speed:", self.hs_speed_combo)

        self.vs_speed_combo = QComboBox()
        for idx, label in _VS_SPEEDS:
            self.vs_speed_combo.addItem(label, idx)
        self.vs_speed_combo.setCurrentIndex(1)  # default: 9.8 µs
        speed_form.addRow("VS Speed:", self.vs_speed_combo)

        layout.addWidget(speed_group)

        # --- Gain ---
        gain_group = QGroupBox("Gain")
        gain_form = QFormLayout(gain_group)
        gain_form.setSpacing(4)

        self.em_gain_spin = QSpinBox()
        self.em_gain_spin.setRange(1, 1000)
        self.em_gain_spin.setValue(1)
        self.em_gain_spin.setSuffix("×")
        gain_form.addRow("EM Gain:", self.em_gain_spin)

        self.preamp_gain_combo = QComboBox()
        self.preamp_gain_combo.addItem("1× (default)", 0)  # placeholder until populated
        gain_form.addRow("Pre-amp Gain:", self.preamp_gain_combo)

        layout.addWidget(gain_group)

        # --- Read area ---
        area_group = QGroupBox("Read Area")
        area_layout = QVBoxLayout(area_group)
        area_layout.setSpacing(4)

        self.read_area_combo = QComboBox()
        self.read_area_combo.addItem("Full CCD", "full")
        self.read_area_combo.addItem("Single Track", "single_track")
        self.read_area_combo.addItem("Crop Mode", "crop")
        area_layout.addWidget(self.read_area_combo)

        # Single track sub-controls
        self._single_track_group = QGroupBox("Single Track")
        st_form = QFormLayout(self._single_track_group)
        st_form.setSpacing(4)
        self._st_centre_spin = QSpinBox()
        self._st_centre_spin.setRange(1, 200)
        self._st_centre_spin.setValue(100)
        st_form.addRow("Centre row:", self._st_centre_spin)
        self._st_height_spin = QSpinBox()
        self._st_height_spin.setRange(1, 200)
        self._st_height_spin.setValue(10)
        st_form.addRow("Height (rows):", self._st_height_spin)
        area_layout.addWidget(self._single_track_group)

        # Crop mode sub-controls
        self._crop_mode_group = QGroupBox("Crop Mode")
        crop_form = QFormLayout(self._crop_mode_group)
        crop_form.setSpacing(4)

        # Newton DU970P: crop region is always anchored to bottom of sensor
        # (nearest readout register). Position cannot be changed (SetIsolatedCropModeEx
        # is iXon Ultra only). Light must not fall on excluded rows.
        crop_note = QLabel("⚠ Region anchored to bottom of sensor.\nNo light on excluded rows.")
        crop_note.setWordWrap(True)
        crop_note.setStyleSheet("color: gray; font-size: 10px;")
        crop_form.addRow(crop_note)

        self._crop_height_spin = QSpinBox()
        self._crop_height_spin.setRange(1, 200)
        self._crop_height_spin.setValue(16)
        crop_form.addRow("Crop height (rows):", self._crop_height_spin)
        self._crop_width_spin = QSpinBox()
        self._crop_width_spin.setRange(1, 1600)
        self._crop_width_spin.setValue(1600)
        crop_form.addRow("Crop width:", self._crop_width_spin)
        area_layout.addWidget(self._crop_mode_group)

        layout.addWidget(area_group)

        # --- Binning ---
        bin_group = QGroupBox("Binning")
        bin_form = QFormLayout(bin_group)
        bin_form.setSpacing(4)

        self.hbin_combo = QComboBox()
        for v in (1, 2, 4, 8):
            self.hbin_combo.addItem(f"{v}×", v)
        bin_form.addRow("H bin:", self.hbin_combo)

        self.vbin_spin = QSpinBox()
        self.vbin_spin.setRange(1, 200)
        self.vbin_spin.setValue(1)
        bin_form.addRow("V bin:", self.vbin_spin)

        layout.addWidget(bin_group)

        # --- Trigger mode ---
        trig_group = QGroupBox("Trigger")
        trig_form = QFormLayout(trig_group)
        trig_form.setSpacing(4)

        self.trigger_mode_combo = QComboBox()
        self.trigger_mode_combo.addItem("Internal (free-run)", "internal")
        self.trigger_mode_combo.addItem("External (laser sync)", "external")
        trig_form.addRow("Mode:", self.trigger_mode_combo)

        ext_note = QLabel("⚠ External: acquisition blocks\nuntil hardware trigger arrives.")
        ext_note.setWordWrap(True)
        ext_note.setStyleSheet("color: gray; font-size: 10px;")
        trig_form.addRow(ext_note)

        layout.addWidget(trig_group)

        # --- Readout time display ---
        self._readout_label = QLabel("Readout: -- ms")
        self._readout_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._readout_label)

    def _populate_hs_speeds(self, amplifier_type: int) -> None:
        """Repopulate HS speed combo for the selected amplifier type."""
        self.hs_speed_combo.blockSignals(True)
        current_idx = self.hs_speed_combo.currentIndex()
        self.hs_speed_combo.clear()
        for idx, label in _HS_SPEEDS:
            self.hs_speed_combo.addItem(label, idx)
        # restore selection if possible
        if 0 <= current_idx < self.hs_speed_combo.count():
            self.hs_speed_combo.setCurrentIndex(current_idx)
        self.hs_speed_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.amplifier_combo.currentIndexChanged.connect(self._on_amplifier_changed)
        self.read_area_combo.currentIndexChanged.connect(self._on_read_area_changed)
        self.hbin_combo.currentIndexChanged.connect(self._on_hbin_changed)
        self.vbin_spin.valueChanged.connect(self._on_vbin_changed)

        # Emit settings_changed for any control change
        for widget in (
            self.vs_speed_combo, self.hs_speed_combo, self.amplifier_combo,
            self.preamp_gain_combo, self.read_area_combo, self.trigger_mode_combo,
            self.hbin_combo,
        ):
            widget.currentIndexChanged.connect(self.settings_changed)
        for spinbox in (
            self.em_gain_spin, self.vbin_spin,
            self._st_centre_spin, self._st_height_spin,
            self._crop_height_spin, self._crop_width_spin,
        ):
            spinbox.valueChanged.connect(self.settings_changed)

        self.settings_changed.connect(self._update_readout_label)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_hbin_changed(self, _index: int) -> None:
        """Round crop width down to nearest multiple of hbin."""
        hbin = self.hbin_combo.currentData() or 1
        if hbin > 1:
            w = self._crop_width_spin.value()
            self._crop_width_spin.blockSignals(True)
            self._crop_width_spin.setValue(max(hbin, (w // hbin) * hbin))
            self._crop_width_spin.blockSignals(False)

    def _on_vbin_changed(self, _value: int) -> None:
        """Round crop height down to nearest multiple of vbin."""
        vbin = self.vbin_spin.value()
        if vbin > 1:
            h = self._crop_height_spin.value()
            self._crop_height_spin.blockSignals(True)
            self._crop_height_spin.setValue(max(vbin, (h // vbin) * vbin))
            self._crop_height_spin.blockSignals(False)

    def _update_readout_label(self) -> None:
        """Recompute and display the estimated readout time."""
        vs_idx = self.vs_speed_combo.currentData()
        hs_idx = self.hs_speed_combo.currentData()
        if vs_idx is None or hs_idx is None:
            return
        hbin = self.hbin_combo.currentData() or 1
        vbin = self.vbin_spin.value()
        mode = self.read_area_combo.currentData() or "full"

        if mode == "crop":
            n_rows = self._crop_height_spin.value()
            n_px = self._crop_width_spin.value()
            calc_mode = "crop"
        elif mode == "single_track":
            n_rows = self._st_height_spin.value()
            n_px = 1600
            calc_mode = "single_track"
        else:
            # full CCD — show FVB time (worst-case for TA/spectroscopy)
            n_rows = 200
            n_px = 1600
            calc_mode = "fvb"

        t_ms = calculate_readout_time_ms(calc_mode, n_rows, n_px, vs_idx, hs_idx, hbin, vbin)

        color = "red" if t_ms > 1.0 else "green" if t_ms < 0.8 else "orange"
        self._readout_label.setText(
            f"<span style='color:{color}'>Readout: {t_ms:.2f} ms</span>"
            + (" ⚠ &gt;1 ms" if t_ms > 1.0 else "")
        )
        self._readout_label.setTextFormat(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.TextFormat.RichText
        )

    def _on_amplifier_changed(self, index: int) -> None:
        amplifier_type = self.amplifier_combo.itemData(index) if index >= 0 else 0
        self.em_gain_spin.setEnabled(amplifier_type == 0)
        self._populate_hs_speeds(amplifier_type)

    def _on_read_area_changed(self, index: int) -> None:
        mode = self.read_area_combo.itemData(index) if index >= 0 else "full"
        self._single_track_group.setVisible(mode == "single_track")
        self._crop_mode_group.setVisible(mode == "crop")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate_from_camera(self, camera) -> None:
        """Populate speed, gain, and EM range options from live camera.

        Call this after hardware initialization so the widget reflects
        the actual camera capabilities and shows SDK-accurate speed labels.

        Args:
            camera: AndorCamera instance (must be initialized).
        """
        # VS speeds — query actual µs values from SDK
        try:
            vs_speeds = camera.get_vs_speeds()
            saved_vs = self.vs_speed_combo.currentIndex()
            self.vs_speed_combo.blockSignals(True)
            self.vs_speed_combo.clear()
            for idx, us in vs_speeds:
                label = f"{us:.4g} µs"
                if idx == 1:
                    label += "  (recommended)"
                elif idx == 0:
                    label += "  (fastest)"
                elif idx == len(vs_speeds) - 1:
                    label += "  (slowest)"
                self.vs_speed_combo.addItem(label, idx)
            restore = saved_vs if 0 <= saved_vs < self.vs_speed_combo.count() else 1
            self.vs_speed_combo.setCurrentIndex(restore)
            self.vs_speed_combo.blockSignals(False)
        except Exception as e:
            log.warning(f"Could not populate VS speeds: {e}")

        # HS speeds — query actual MHz values from SDK for current amplifier
        try:
            amp_type = self.amplifier_combo.itemData(self.amplifier_combo.currentIndex()) or 0
            hs_speeds = camera.get_hs_speeds(amp_type)
            saved_hs = self.hs_speed_combo.currentIndex()
            self.hs_speed_combo.blockSignals(True)
            self.hs_speed_combo.clear()
            for idx, mhz in hs_speeds:
                if mhz >= 1.0:
                    label = f"{mhz:.4g} MHz"
                else:
                    label = f"{mhz * 1000:.4g} kHz"
                if idx == 0:
                    label += "  (fastest)"
                elif idx == len(hs_speeds) - 1:
                    label += "  (lowest noise)"
                self.hs_speed_combo.addItem(label, idx)
            restore = saved_hs if 0 <= saved_hs < self.hs_speed_combo.count() else 0
            self.hs_speed_combo.setCurrentIndex(restore)
            self.hs_speed_combo.blockSignals(False)
        except Exception as e:
            log.warning(f"Could not populate HS speeds: {e}")

        # Pre-amp gains
        try:
            gains = camera.get_preamp_gains()
            self.preamp_gain_combo.blockSignals(True)
            self.preamp_gain_combo.clear()
            for idx, gain in gains:
                self.preamp_gain_combo.addItem(f"{gain:.4g}×", idx)
            self.preamp_gain_combo.blockSignals(False)
        except Exception as e:
            log.warning(f"Could not populate pre-amp gains: {e}")

        # EM gain range
        try:
            em_low, em_high = camera.info.em_gain_range
            self.em_gain_spin.setRange(em_low, em_high)
        except Exception as e:
            log.warning(f"Could not set EM gain range: {e}")

    def get_settings(self) -> dict:
        """Return current settings as a dict suitable for apply_camera_settings().

        Returns:
            Dict with keys: vs_speed_index, hs_speed_index, amplifier_type,
            em_gain, preamp_gain_index, read_area_mode, and (conditionally)
            single_track_centre, single_track_height, crop_height, crop_width.
        """
        amp_idx = self.amplifier_combo.currentIndex()
        amplifier_type = self.amplifier_combo.itemData(amp_idx) if amp_idx >= 0 else 0

        vs_idx = self.vs_speed_combo.currentIndex()
        hs_idx = self.hs_speed_combo.currentIndex()
        pa_idx = self.preamp_gain_combo.currentIndex()

        mode = self.read_area_combo.itemData(self.read_area_combo.currentIndex()) or "full"

        trig_idx = self.trigger_mode_combo.currentIndex()
        trigger_mode = self.trigger_mode_combo.itemData(trig_idx) if trig_idx >= 0 else "internal"

        settings: dict = {
            "vs_speed_index": self.vs_speed_combo.itemData(vs_idx) if vs_idx >= 0 else 1,
            "hs_speed_index": self.hs_speed_combo.itemData(hs_idx) if hs_idx >= 0 else 0,
            "amplifier_type": amplifier_type,
            "em_gain": self.em_gain_spin.value(),
            "preamp_gain_index": self.preamp_gain_combo.itemData(pa_idx) if pa_idx >= 0 else 0,
            "read_area_mode": mode,
            "hbin": self.hbin_combo.currentData() or 1,
            "vbin": self.vbin_spin.value(),
            "trigger_mode": trigger_mode,
        }

        if mode == "single_track":
            settings["single_track_centre"] = self._st_centre_spin.value()
            settings["single_track_height"] = self._st_height_spin.value()
        elif mode == "crop":
            settings["crop_height"] = self._crop_height_spin.value()
            settings["crop_width"] = self._crop_width_spin.value()

        return settings
