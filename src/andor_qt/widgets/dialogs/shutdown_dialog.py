"""Shutdown dialog with temperature warmup progress.

Shows the camera warmup temperature progress and allows
the user to force-quit if needed.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class ShutdownDialog(QDialog):
    """Dialog showing shutdown/warmup progress.

    Displays current temperature, a progress bar, and a
    force-quit button for emergencies.

    Signals:
        force_quit_requested: Emitted when user clicks Force Quit.
    """

    force_quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Shutting Down...")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(200)

        self._start_temp = 0.0
        self._target_temp = -20.0

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Status label
        self._status_label = QLabel("Preparing shutdown...")
        layout.addWidget(self._status_label)

        # Temperature label
        self._temp_label = QLabel("Temperature: -- °C")
        layout.addWidget(self._temp_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        # Force quit button
        self._force_quit_btn = QPushButton("Force Quit")
        self._force_quit_btn.clicked.connect(self.force_quit_requested.emit)
        layout.addWidget(self._force_quit_btn)

    def set_temperature_range(self, start_temp: float, target_temp: float) -> None:
        """Set the temperature range for progress calculation.

        Args:
            start_temp: Starting temperature (°C).
            target_temp: Target temperature (°C).
        """
        self._start_temp = start_temp
        self._target_temp = target_temp

    def update_temperature(self, temperature: float, status: str) -> None:
        """Update the temperature display and progress.

        Args:
            temperature: Current temperature (°C).
            status: Temperature status string.
        """
        self._temp_label.setText(f"Temperature: {temperature:.1f} °C ({status})")

        # Calculate progress
        temp_range = self._target_temp - self._start_temp
        if abs(temp_range) > 0.1:
            progress = (temperature - self._start_temp) / temp_range * 100
            progress = max(0, min(100, int(progress)))
        else:
            progress = 100

        self._progress_bar.setValue(progress)

    def set_status(self, message: str) -> None:
        """Update the status label.

        Args:
            message: Status message to display.
        """
        self._status_label.setText(message)

    def on_shutdown_complete(self) -> None:
        """Handle shutdown completion."""
        self._progress_bar.setValue(100)
        self._status_label.setText("Shutdown complete")
        self._force_quit_btn.setEnabled(False)
