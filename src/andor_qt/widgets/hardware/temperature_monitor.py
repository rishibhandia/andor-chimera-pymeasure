"""Enhanced temperature monitoring widget.

Displays current temperature, target temperature, and a color-coded
status indicator for quick visual feedback.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


# Status color mapping
_STATUS_COLORS = {
    "STABILIZED": ("green", "Temperature stabilized"),
    "NOT_REACHED": ("orange", "Cooling in progress"),
    "NOT_STABILIZED": ("orange", "Temperature not yet stable"),
    "DRIFT": ("orange", "Temperature drifting"),
    "OFF": ("gray", "Cooler off"),
}


class TemperatureMonitorWidget(QGroupBox):
    """Widget showing current temperature with status indicator.

    Provides visual feedback through color-coded status labels.

    Layout:
        ┌──────────────────────────────┐
        │ Temperature Monitor          │
        │ Current:  -60.1 °C           │
        │ Target:   -60 °C             │
        │ Status:   ● STABILIZED       │
        └──────────────────────────────┘
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Temperature Monitor", parent)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)

        # Current temperature
        current_row = QHBoxLayout()
        current_row.addWidget(QLabel("Current:"))
        self._current_temp_label = QLabel("-- °C")
        current_row.addWidget(self._current_temp_label)
        current_row.addStretch()
        layout.addLayout(current_row)

        # Target temperature
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Target:"))
        self._target_temp_label = QLabel("-- °C")
        target_row.addWidget(self._target_temp_label)
        target_row.addStretch()
        layout.addLayout(target_row)

        # Status indicator
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self._status_label = QLabel("OFF")
        self._update_status_color("OFF")
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

    def set_temperature(self, temp: float, status: str) -> None:
        """Update current temperature and status.

        Args:
            temp: Current temperature in °C.
            status: Temperature status string.
        """
        self._current_temp_label.setText(f"{temp:.1f} °C")
        self._status_label.setText(status)
        self._update_status_color(status)

    def set_target(self, target: int) -> None:
        """Update target temperature display.

        Args:
            target: Target temperature in °C.
        """
        self._target_temp_label.setText(f"{target} °C")

    def _update_status_color(self, status: str) -> None:
        """Update the status label color based on status.

        Args:
            status: Temperature status string.
        """
        color, tooltip = _STATUS_COLORS.get(status, ("gray", "Unknown status"))
        self._status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        self._status_label.setToolTip(tooltip)
