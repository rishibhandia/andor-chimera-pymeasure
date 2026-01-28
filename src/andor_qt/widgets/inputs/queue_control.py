"""Queue control widget for experiment execution.

This widget provides controls for queuing and aborting procedures.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from pymeasure.experiment import Procedure

log = logging.getLogger(__name__)


class QueueControlWidget(QWidget):
    """Widget for controlling procedure queue and execution.

    Features:
    - Queue button to start acquisition
    - Abort button to stop running procedure
    - Progress bar showing current procedure progress

    Signals:
        queue_clicked: Emitted when Queue button is clicked
        abort_clicked: Emitted when Abort button is clicked
    """

    queue_clicked = Signal()
    abort_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._is_running = False
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        # Buttons row
        buttons_row = QHBoxLayout()

        self._queue_button = QPushButton("Queue")
        self._queue_button.setToolTip("Queue acquisition with current settings")
        self._queue_button.setMinimumHeight(40)
        self._queue_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        buttons_row.addWidget(self._queue_button)

        self._abort_button = QPushButton("Abort")
        self._abort_button.setToolTip("Abort running acquisition")
        self._abort_button.setMinimumHeight(40)
        self._abort_button.setEnabled(False)
        self._abort_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        buttons_row.addWidget(self._abort_button)

        layout.addLayout(buttons_row)

    def _connect_signals(self) -> None:
        """Connect button signals."""
        self._queue_button.clicked.connect(self._on_queue_clicked)
        self._abort_button.clicked.connect(self._on_abort_clicked)

    @Slot()
    def _on_queue_clicked(self) -> None:
        """Handle Queue button click."""
        log.info("Queue button clicked")
        self.queue_clicked.emit()

    @Slot()
    def _on_abort_clicked(self) -> None:
        """Handle Abort button click."""
        log.info("Abort button clicked")
        self.abort_clicked.emit()

    def set_running(self, running: bool) -> None:
        """Update UI for running state.

        Args:
            running: True if a procedure is running.
        """
        self._is_running = running

        if running:
            self._queue_button.setEnabled(False)
            self._abort_button.setEnabled(True)
            self._progress_bar.setValue(0)
        else:
            self._queue_button.setEnabled(True)
            self._abort_button.setEnabled(False)

    def set_progress(self, progress: float) -> None:
        """Update progress bar.

        Args:
            progress: Progress percentage (0-100).
        """
        self._progress_bar.setValue(int(progress))

    def reset(self) -> None:
        """Reset widget to initial state."""
        self._is_running = False
        self._queue_button.setEnabled(True)
        self._abort_button.setEnabled(False)
        self._progress_bar.setValue(0)

    @property
    def is_running(self) -> bool:
        """Check if a procedure is currently running."""
        return self._is_running
