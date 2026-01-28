"""Direct acquisition control widget.

Provides Acquire and Abort buttons for immediate (non-queued)
single acquisitions.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class AcquireControlWidget(QWidget):
    """Widget with Acquire and Abort buttons.

    Signals:
        acquire_requested: Emitted when Acquire button is clicked.
        abort_requested: Emitted when Abort button is clicked.
    """

    acquire_requested = Signal()
    abort_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._acquire_btn = QPushButton("Acquire")
        self._acquire_btn.clicked.connect(self.acquire_requested.emit)
        layout.addWidget(self._acquire_btn)

        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self.abort_requested.emit)
        layout.addWidget(self._abort_btn)

    def set_acquiring(self, acquiring: bool) -> None:
        """Update button states based on acquisition status.

        Args:
            acquiring: True if acquisition is in progress.
        """
        self._acquire_btn.setEnabled(not acquiring)
        self._abort_btn.setEnabled(acquiring)
