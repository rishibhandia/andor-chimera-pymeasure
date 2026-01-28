"""Spectrograph control widget for grating and wavelength.

This widget provides immediate control over the spectrograph settings -
changes are applied in background threads without blocking the UI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from andor_qt.core.signals import get_hardware_signals

if TYPE_CHECKING:
    from andor_pymeasure.instruments.andor_spectrograph import GratingInfo

    from andor_qt.core.hardware_manager import HardwareManager

log = logging.getLogger(__name__)


class SpectrographControlWidget(QGroupBox):
    """Widget for controlling spectrograph grating and wavelength.

    Features:
    - Grating selection combobox with immediate change
    - Wavelength spinbox with "Go" button
    - Moving indicator (indeterminate progress bar)
    - Current wavelength display
    """

    def __init__(
        self,
        hardware_manager: "HardwareManager",
        parent: QWidget | None = None,
    ):
        super().__init__("Spectrograph Control", parent)
        self._hw = hardware_manager
        self._signals = get_hardware_signals()
        self._gratings: List["GratingInfo"] = []
        self._is_moving = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Grating row
        grating_row = QHBoxLayout()

        grating_row.addWidget(QLabel("Grating:"))

        self._grating_combo = QComboBox()
        self._grating_combo.setMinimumWidth(200)
        self._grating_combo.setToolTip("Select grating (changes immediately)")
        grating_row.addWidget(self._grating_combo)

        grating_row.addStretch()
        layout.addLayout(grating_row)

        # Wavelength row
        wavelength_row = QHBoxLayout()

        wavelength_row.addWidget(QLabel("Wavelength:"))

        self._wavelength_spin = QDoubleSpinBox()
        self._wavelength_spin.setRange(0.0, 2000.0)
        self._wavelength_spin.setValue(500.0)
        self._wavelength_spin.setSuffix(" nm")
        self._wavelength_spin.setDecimals(1)
        self._wavelength_spin.setToolTip("Target center wavelength")
        wavelength_row.addWidget(self._wavelength_spin)

        self._go_button = QPushButton("Go")
        self._go_button.setToolTip("Move to target wavelength")
        self._go_button.setFixedWidth(50)
        wavelength_row.addWidget(self._go_button)

        wavelength_row.addStretch()
        layout.addLayout(wavelength_row)

        # Current wavelength display
        current_row = QHBoxLayout()

        current_row.addWidget(QLabel("Current:"))

        self._current_wl_label = QLabel("-- nm")
        self._current_wl_label.setStyleSheet("font-weight: bold;")
        current_row.addWidget(self._current_wl_label)

        current_row.addStretch()
        layout.addLayout(current_row)

        # Moving indicator
        self._moving_bar = QProgressBar()
        self._moving_bar.setRange(0, 0)  # Indeterminate
        self._moving_bar.setTextVisible(False)
        self._moving_bar.setFixedHeight(8)
        self._moving_bar.hide()
        layout.addWidget(self._moving_bar)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        # UI signals
        self._grating_combo.currentIndexChanged.connect(self._on_grating_changed)
        self._go_button.clicked.connect(self._on_go_clicked)
        self._wavelength_spin.editingFinished.connect(self._on_wavelength_editing_finished)

        # Hardware signals
        self._signals.spectrograph_initialized.connect(self._on_spectrograph_initialized)
        self._signals.grating_changing.connect(self._on_grating_changing)
        self._signals.grating_changed.connect(self._on_grating_moved)
        self._signals.wavelength_changing.connect(self._on_wavelength_changing)
        self._signals.wavelength_changed.connect(self._on_wavelength_moved)

    def populate_gratings(self, gratings: List["GratingInfo"]) -> None:
        """Populate grating combobox with available gratings.

        Args:
            gratings: List of GratingInfo objects.
        """
        self._gratings = gratings
        self._grating_combo.blockSignals(True)
        self._grating_combo.clear()

        for g in gratings:
            text = f"{g.index}: {g.lines_per_mm:.0f} l/mm, {g.blaze}"
            self._grating_combo.addItem(text, g.index)

        self._grating_combo.blockSignals(False)

    @Slot(dict)
    def _on_spectrograph_initialized(self, info: dict) -> None:
        """Handle spectrograph initialization."""
        if self._hw.spectrograph and self._hw.spectrograph.info:
            self.populate_gratings(list(self._hw.spectrograph.info.gratings))

            # Set current values
            current_grating = self._hw.spectrograph.grating
            current_wavelength = self._hw.spectrograph.wavelength

            # Find index in combo
            for i in range(self._grating_combo.count()):
                if self._grating_combo.itemData(i) == current_grating:
                    self._grating_combo.blockSignals(True)
                    self._grating_combo.setCurrentIndex(i)
                    self._grating_combo.blockSignals(False)
                    break

            self._wavelength_spin.setValue(current_wavelength)
            self._current_wl_label.setText(f"{current_wavelength:.1f} nm")

            # Update wavelength limits for current grating
            self._update_wavelength_limits()

    @Slot(int)
    def _on_grating_changed(self, index: int) -> None:
        """Handle grating combobox change."""
        if index < 0:
            return

        grating = self._grating_combo.itemData(index)
        log.info(f"Grating changed to {grating}")
        self._hw.set_grating(grating)

    @Slot()
    def _on_go_clicked(self) -> None:
        """Handle Go button click."""
        wavelength = self._wavelength_spin.value()
        log.info(f"Going to wavelength {wavelength}nm")
        self._hw.set_wavelength(wavelength)

    @Slot()
    def _on_wavelength_editing_finished(self) -> None:
        """Handle wavelength spinbox editing finished (Enter pressed)."""
        # Could optionally auto-move on Enter
        pass

    @Slot(int)
    def _on_grating_changing(self, target: int) -> None:
        """Handle grating movement starting."""
        self._set_moving(True)

    @Slot(int)
    def _on_grating_moved(self, grating: int) -> None:
        """Handle grating movement complete."""
        self._set_moving(False)

        # Update combo to reflect new grating
        for i in range(self._grating_combo.count()):
            if self._grating_combo.itemData(i) == grating:
                self._grating_combo.blockSignals(True)
                self._grating_combo.setCurrentIndex(i)
                self._grating_combo.blockSignals(False)
                break

        # Update wavelength limits for new grating
        self._update_wavelength_limits()

    @Slot(float)
    def _on_wavelength_changing(self, target: float) -> None:
        """Handle wavelength movement starting."""
        self._set_moving(True)

    @Slot(float)
    def _on_wavelength_moved(self, wavelength: float) -> None:
        """Handle wavelength movement complete."""
        self._set_moving(False)
        self._current_wl_label.setText(f"{wavelength:.1f} nm")
        self._wavelength_spin.setValue(wavelength)

    def _update_wavelength_limits(self) -> None:
        """Update wavelength spinbox limits based on current grating."""
        if not self._hw.spectrograph:
            return

        wl_min, wl_max = self._hw.spectrograph.get_wavelength_limits()
        self._wavelength_spin.setRange(wl_min, wl_max)
        self._wavelength_spin.setToolTip(f"Range: {wl_min:.0f} - {wl_max:.0f} nm")

    def _set_moving(self, moving: bool) -> None:
        """Update UI to show moving state."""
        self._is_moving = moving

        if moving:
            self._moving_bar.show()
            self._grating_combo.setEnabled(False)
            self._go_button.setEnabled(False)
        else:
            self._moving_bar.hide()
            self._grating_combo.setEnabled(True)
            self._go_button.setEnabled(True)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the widget."""
        if enabled and self._is_moving:
            # Keep controls disabled while moving
            return

        self._grating_combo.setEnabled(enabled)
        self._wavelength_spin.setEnabled(enabled)
        self._go_button.setEnabled(enabled)
