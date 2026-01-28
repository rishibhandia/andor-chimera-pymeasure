"""Compact trace list widget for managing spectrum overlay visibility.

Provides checkboxes to toggle individual trace visibility, remove buttons,
and a Clear All button.
"""

from __future__ import annotations

import logging
from typing import Dict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class TraceListWidget(QWidget):
    """Compact list of spectrum traces with visibility checkboxes.

    Each row shows: [checkbox] [color swatch] [label] [x remove]
    A "Clear All" button is shown at the bottom.

    Signals:
        visibility_toggled: (trace_id, visible) - checkbox toggled
        trace_remove_requested: (trace_id,) - remove button clicked
        clear_all_requested: () - Clear All clicked
    """

    visibility_toggled = Signal(int, bool)
    trace_remove_requested = Signal(int)
    clear_all_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._rows: Dict[int, dict] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(2)

        # Header
        header = QLabel("Traces")
        header.setStyleSheet("font-weight: bold; font-size: 11px;")
        outer_layout.addWidget(header)

        # Scroll area for trace rows
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setMaximumHeight(120)

        self._scroll_content = QWidget()
        self._rows_layout = QVBoxLayout(self._scroll_content)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(1)
        self._rows_layout.addStretch()

        self._scroll_area.setWidget(self._scroll_content)
        outer_layout.addWidget(self._scroll_area)

        # Clear All button
        self._clear_btn = QPushButton("Clear All")
        self._clear_btn.setFixedHeight(22)
        self._clear_btn.setStyleSheet("font-size: 10px;")
        self._clear_btn.clicked.connect(self._request_clear_all)
        outer_layout.addWidget(self._clear_btn)

    def add_trace(self, trace_id: int, label: str, color: str) -> None:
        """Add a trace row to the list.

        Args:
            trace_id: Unique trace identifier.
            label: Display label for the trace.
            color: Hex color string (e.g., "#1f77b4").
        """
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(4)

        # Checkbox for visibility
        checkbox = QCheckBox()
        checkbox.setChecked(True)
        checkbox.setToolTip("Toggle visibility")
        checkbox.toggled.connect(lambda checked: self._toggle_visibility(trace_id, checked))
        row_layout.addWidget(checkbox)

        # Color swatch
        swatch = QLabel()
        swatch.setFixedSize(12, 12)
        swatch.setStyleSheet(
            f"background-color: {color}; border: 1px solid #999; border-radius: 2px;"
        )
        row_layout.addWidget(swatch)

        # Label
        label_widget = QLabel(label)
        label_widget.setStyleSheet("font-size: 10px;")
        row_layout.addWidget(label_widget, stretch=1)

        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setStyleSheet("font-size: 12px; border: none; color: #888;")
        remove_btn.setToolTip("Remove trace")
        remove_btn.clicked.connect(lambda: self._request_remove(trace_id))
        row_layout.addWidget(remove_btn)

        # Insert before the stretch
        insert_index = self._rows_layout.count() - 1  # Before stretch
        self._rows_layout.insertWidget(insert_index, row_widget)

        self._rows[trace_id] = {
            "widget": row_widget,
            "checkbox": checkbox,
            "swatch": swatch,
            "label": label_widget,
            "remove_btn": remove_btn,
        }

    def remove_trace(self, trace_id: int) -> None:
        """Remove a trace row from the list.

        Args:
            trace_id: ID of the trace to remove.
        """
        if trace_id not in self._rows:
            return

        row = self._rows.pop(trace_id)
        row["widget"].setParent(None)
        row["widget"].deleteLater()

    def clear(self) -> None:
        """Remove all trace rows."""
        for trace_id in list(self._rows.keys()):
            self.remove_trace(trace_id)

    def row_count(self) -> int:
        """Return the number of trace rows."""
        return len(self._rows)

    def _toggle_visibility(self, trace_id: int, visible: bool) -> None:
        """Handle checkbox toggle — emit signal."""
        self.visibility_toggled.emit(trace_id, visible)

    def _request_remove(self, trace_id: int) -> None:
        """Handle remove button click — emit signal."""
        self.trace_remove_requested.emit(trace_id)

    def _request_clear_all(self) -> None:
        """Handle Clear All button click — emit signal."""
        self.clear_all_requested.emit()
