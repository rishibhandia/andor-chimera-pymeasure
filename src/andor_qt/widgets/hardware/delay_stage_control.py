"""Delay stage control widget for motion controller.

This widget provides control over delay stage positions with support
for multiple axes and unit selection (mm/ps).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
    from andor_qt.core.hardware_manager import HardwareManager

log = logging.getLogger(__name__)


class DelayStageControlWidget(QGroupBox):
    """Widget for controlling delay stage positions.

    Features:
    - Axis selector dropdown (shows all available axes)
    - Position spinbox with unit selection (mm/ps)
    - Go button to move to target position
    - Home button to home the selected axis
    - Current position display
    - Moving indicator (indeterminate progress bar)
    """

    def __init__(
        self,
        hardware_manager: "HardwareManager",
        parent: QWidget | None = None,
    ):
        super().__init__("Delay Stage Control", parent)
        self._hw = hardware_manager
        self._signals = get_hardware_signals()
        self._is_moving = False
        self._current_units = "ps"  # Default to picoseconds

        self._setup_ui()
        self._connect_signals()
        self._populate_axes()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Axis selector row
        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("Axis:"))

        self._axis_combo = QComboBox()
        self._axis_combo.setMinimumWidth(120)
        self._axis_combo.setToolTip("Select motion axis")
        axis_row.addWidget(self._axis_combo)

        axis_row.addStretch()
        layout.addLayout(axis_row)

        # Position row
        position_row = QHBoxLayout()
        position_row.addWidget(QLabel("Position:"))

        self._position_spin = QDoubleSpinBox()
        self._position_spin.setRange(-10000.0, 10000.0)
        self._position_spin.setValue(0.0)
        self._position_spin.setDecimals(3)
        self._position_spin.setToolTip("Target position")
        position_row.addWidget(self._position_spin)

        # Unit selector
        self._unit_combo = QComboBox()
        self._unit_combo.addItems(["ps", "mm"])
        self._unit_combo.setCurrentText("ps")
        self._unit_combo.setToolTip("Position units")
        self._unit_combo.setFixedWidth(50)
        position_row.addWidget(self._unit_combo)

        self._go_button = QPushButton("Go")
        self._go_button.setToolTip("Move to target position")
        self._go_button.setFixedWidth(50)
        position_row.addWidget(self._go_button)

        position_row.addStretch()
        layout.addLayout(position_row)

        # Current position and home row
        current_row = QHBoxLayout()
        current_row.addWidget(QLabel("Current:"))

        self._current_pos_label = QLabel("-- ps")
        self._current_pos_label.setStyleSheet("font-weight: bold;")
        current_row.addWidget(self._current_pos_label)

        current_row.addStretch()

        self._home_button = QPushButton("Home")
        self._home_button.setToolTip("Home the selected axis")
        self._home_button.setFixedWidth(60)
        current_row.addWidget(self._home_button)

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
        self._axis_combo.currentIndexChanged.connect(self._on_axis_changed)
        self._unit_combo.currentTextChanged.connect(self._on_unit_changed)
        self._go_button.clicked.connect(self._on_go_clicked)
        self._home_button.clicked.connect(self._on_home_clicked)

        # Hardware signals
        self._signals.motion_initialized.connect(self._on_motion_initialized)
        self._signals.axis_position_changed.connect(self._on_axis_position_changed)
        self._signals.axis_moving.connect(self._on_axis_moving)

    def _populate_axes(self) -> None:
        """Populate axis selector from motion manager."""
        self._axis_combo.blockSignals(True)
        self._axis_combo.clear()

        if self._hw.motion_manager:
            for name, axis in self._hw.motion_manager.all_axes.items():
                self._axis_combo.addItem(name, name)

        self._axis_combo.blockSignals(False)

        # Update display for first axis
        if self._axis_combo.count() > 0:
            self._update_position_display()

    def _get_current_axis(self):
        """Get the currently selected axis."""
        if not self._hw.motion_manager:
            return None

        axis_name = self._axis_combo.currentData()
        if axis_name:
            return self._hw.motion_manager.get_axis(axis_name)
        return None

    def _update_position_display(self) -> None:
        """Update the current position display."""
        axis = self._get_current_axis()
        if axis is None:
            self._current_pos_label.setText("-- ps")
            return

        if self._current_units == "ps":
            self._current_pos_label.setText(f"{axis.position_ps:.3f} ps")
        else:
            self._current_pos_label.setText(f"{axis.position:.3f} mm")

    def _update_position_range(self) -> None:
        """Update position spinbox range based on selected axis and units."""
        axis = self._get_current_axis()
        if axis is None:
            return

        if self._current_units == "ps":
            min_ps, max_ps = axis.delay_range_ps
            self._position_spin.setRange(min_ps, max_ps)
            self._position_spin.setSuffix(" ps")
        else:
            self._position_spin.setRange(axis.position_min, axis.position_max)
            self._position_spin.setSuffix(" mm")

    @Slot(int)
    def _on_axis_changed(self, index: int) -> None:
        """Handle axis selection change."""
        self._update_position_display()
        self._update_position_range()

    @Slot(str)
    def _on_unit_changed(self, unit: str) -> None:
        """Handle unit selection change."""
        self._current_units = unit
        self._update_position_display()
        self._update_position_range()

    @Slot()
    def _on_go_clicked(self) -> None:
        """Handle Go button click."""
        axis_name = self._axis_combo.currentData()
        if not axis_name:
            return

        position = self._position_spin.value()
        log.info(f"Moving {axis_name} to {position} {self._current_units}")
        self._hw.set_axis_position(axis_name, position, units=self._current_units)

    @Slot()
    def _on_home_clicked(self) -> None:
        """Handle Home button click."""
        axis = self._get_current_axis()
        if axis is None:
            return

        axis_name = self._axis_combo.currentData()
        log.info(f"Homing axis {axis_name}")

        # Home by moving to position 0
        self._hw.set_axis_position(axis_name, 0.0, units="mm")

    @Slot(dict)
    def _on_motion_initialized(self, axis_info: dict) -> None:
        """Handle motion system initialization."""
        log.info(f"Motion initialized with axes: {list(axis_info.keys())}")
        self._populate_axes()

    @Slot(str, float)
    def _on_axis_position_changed(self, axis_name: str, position: float) -> None:
        """Handle axis position change."""
        current_axis_name = self._axis_combo.currentData()
        if axis_name == current_axis_name:
            self._update_position_display()

    @Slot(str, bool)
    def _on_axis_moving(self, axis_name: str, is_moving: bool) -> None:
        """Handle axis moving state change."""
        current_axis_name = self._axis_combo.currentData()
        if axis_name == current_axis_name:
            self._set_moving(is_moving)

    def _set_moving(self, moving: bool) -> None:
        """Update UI to show moving state."""
        self._is_moving = moving

        if moving:
            self._moving_bar.show()
            self._go_button.setEnabled(False)
            self._home_button.setEnabled(False)
            self._axis_combo.setEnabled(False)
        else:
            self._moving_bar.hide()
            self._go_button.setEnabled(True)
            self._home_button.setEnabled(True)
            self._axis_combo.setEnabled(True)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the widget.

        Args:
            enabled: True to enable, False to disable.
        """
        if enabled and self._is_moving:
            # Keep controls disabled while moving
            return

        self._axis_combo.setEnabled(enabled)
        self._position_spin.setEnabled(enabled)
        self._unit_combo.setEnabled(enabled)
        self._go_button.setEnabled(enabled)
        self._home_button.setEnabled(enabled)
