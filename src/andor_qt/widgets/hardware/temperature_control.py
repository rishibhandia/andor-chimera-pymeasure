"""Temperature control widget for camera cooler.

This widget provides immediate control over the camera cooler - not queued
as a procedure parameter.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from andor_qt.core.signals import get_hardware_signals

if TYPE_CHECKING:
    from andor_qt.core.hardware_manager import HardwareManager

log = logging.getLogger(__name__)


class TemperatureControlWidget(QGroupBox):
    """Widget for controlling camera cooler and monitoring temperature.

    Features:
    - Cooler ON/OFF checkbox (immediate action)
    - Target temperature spinbox
    - Current temperature display (polled via HardwareManager)
    - Temperature status indicator
    """

    def __init__(
        self,
        hardware_manager: "HardwareManager",
        parent: QWidget | None = None,
    ):
        super().__init__("Temperature Control", parent)
        self._hw = hardware_manager
        self._signals = get_hardware_signals()

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Cooler control row
        cooler_row = QHBoxLayout()

        self._cooler_checkbox = QCheckBox("Cooler")
        self._cooler_checkbox.setToolTip("Turn cooler ON/OFF (immediate action)")
        cooler_row.addWidget(self._cooler_checkbox)

        cooler_row.addWidget(QLabel("Target:"))

        self._target_spin = QSpinBox()
        self._target_spin.setRange(-100, 20)
        self._target_spin.setValue(-60)
        self._target_spin.setSuffix(" °C")
        self._target_spin.setToolTip("Target temperature")
        cooler_row.addWidget(self._target_spin)

        cooler_row.addStretch()
        layout.addLayout(cooler_row)

        # Temperature display row
        temp_row = QHBoxLayout()

        temp_row.addWidget(QLabel("Current:"))

        self._temp_label = QLabel("-- °C")
        self._temp_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        temp_row.addWidget(self._temp_label)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-style: italic;")
        temp_row.addWidget(self._status_label)

        temp_row.addStretch()
        layout.addLayout(temp_row)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        # UI signals
        self._cooler_checkbox.stateChanged.connect(self._on_cooler_toggled)
        self._target_spin.valueChanged.connect(self._on_target_changed)

        # Hardware signals
        self._signals.temperature_changed.connect(self._on_temperature_changed)
        self._signals.cooler_state_changed.connect(self._on_cooler_state_changed)

    @Slot(int)
    def _on_cooler_toggled(self, state: int) -> None:
        """Handle cooler checkbox toggle."""
        on = state == Qt.CheckState.Checked.value
        target = self._target_spin.value()

        log.info(f"Cooler toggled: {'ON' if on else 'OFF'}, target={target}°C")
        self._hw.set_cooler(on=on, target_temp=target)

    @Slot(int)
    def _on_target_changed(self, value: int) -> None:
        """Handle target temperature change."""
        # Only update if cooler is already on
        if self._cooler_checkbox.isChecked():
            log.info(f"Target temperature changed to {value}°C")
            self._hw.set_cooler(on=True, target_temp=value)

    @Slot(float, str)
    def _on_temperature_changed(self, temperature: float, status: str) -> None:
        """Update temperature display from hardware signal."""
        self._temp_label.setText(f"{temperature:.1f} °C")

        # Update status label with color
        status_colors = {
            "STABILIZED": "color: green;",
            "NOT_REACHED": "color: orange;",
            "NOT_STABILIZED": "color: orange;",
            "DRIFTING": "color: orange;",
            "OFF": "color: gray;",
        }
        style = status_colors.get(status, "color: black;")
        self._status_label.setStyleSheet(f"font-style: italic; {style}")
        self._status_label.setText(f"({status})")

    @Slot(bool, int)
    def _on_cooler_state_changed(self, on: bool, target: int) -> None:
        """Update UI from hardware cooler state change."""
        # Block signals to avoid feedback loop
        self._cooler_checkbox.blockSignals(True)
        self._target_spin.blockSignals(True)

        self._cooler_checkbox.setChecked(on)
        self._target_spin.setValue(target)

        self._cooler_checkbox.blockSignals(False)
        self._target_spin.blockSignals(False)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the widget."""
        self._cooler_checkbox.setEnabled(enabled)
        self._target_spin.setEnabled(enabled)
