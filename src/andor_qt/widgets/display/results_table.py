"""Results table widget for experiment queue.

This widget displays the experiment queue with status information.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


@dataclass
class ExperimentEntry:
    """Entry in the experiment queue."""

    id: int
    procedure_type: str
    parameters: Dict[str, any]
    status: str  # 'queued', 'running', 'completed', 'failed', 'aborted'
    progress: float
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None


class ResultsTableWidget(QWidget):
    """Widget displaying experiment queue and results.

    Features:
    - Shows queued and completed experiments
    - Status indicators (queued, running, completed, failed)
    - Progress display for running experiments
    - Double-click to view results

    Signals:
        experiment_selected: Emitted when an experiment is selected (id)
        experiment_double_clicked: Emitted on double-click (id)
    """

    experiment_selected = Signal(int)
    experiment_double_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._experiments: List[ExperimentEntry] = []
        self._next_id = 1

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "ID",
            "Type",
            "Parameters",
            "Status",
            "Progress",
        ])

        # Configure table
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)

        # Set column widths
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Parameters
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Status
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Progress

        layout.addWidget(self._table)

    def _connect_signals(self) -> None:
        """Connect table signals."""
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(self._on_double_clicked)

    @Slot()
    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        selected = self._table.selectedItems()
        if selected:
            row = selected[0].row()
            if row < len(self._experiments):
                self.experiment_selected.emit(self._experiments[row].id)

    @Slot(QTableWidgetItem)
    def _on_double_clicked(self, item: QTableWidgetItem) -> None:
        """Handle double-click."""
        row = item.row()
        if row < len(self._experiments):
            self.experiment_double_clicked.emit(self._experiments[row].id)

    def add_experiment(
        self,
        procedure_type: str,
        parameters: Dict[str, any],
    ) -> int:
        """Add a new experiment to the queue.

        Args:
            procedure_type: Type of procedure ('FVB', 'Image', etc.)
            parameters: Dictionary of procedure parameters.

        Returns:
            Experiment ID.
        """
        exp_id = self._next_id
        self._next_id += 1

        entry = ExperimentEntry(
            id=exp_id,
            procedure_type=procedure_type,
            parameters=parameters,
            status="queued",
            progress=0.0,
        )
        self._experiments.append(entry)

        self._update_table()
        return exp_id

    def update_status(
        self,
        exp_id: int,
        status: str,
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update experiment status.

        Args:
            exp_id: Experiment ID.
            status: New status.
            progress: Progress percentage (0-100).
            error_message: Error message if failed.
        """
        for entry in self._experiments:
            if entry.id == exp_id:
                entry.status = status
                if progress is not None:
                    entry.progress = progress

                if status == "running" and entry.start_time is None:
                    entry.start_time = datetime.now()
                elif status in ("completed", "failed", "aborted"):
                    entry.end_time = datetime.now()

                if error_message:
                    entry.error_message = error_message

                break

        self._update_table()

    def _update_table(self) -> None:
        """Update table display from internal data."""
        self._table.setRowCount(len(self._experiments))

        for row, entry in enumerate(self._experiments):
            # ID
            id_item = QTableWidgetItem(str(entry.id))
            id_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 0, id_item)

            # Type
            type_item = QTableWidgetItem(entry.procedure_type)
            self._table.setItem(row, 1, type_item)

            # Parameters (summary)
            params_str = self._format_parameters(entry.parameters)
            params_item = QTableWidgetItem(params_str)
            self._table.setItem(row, 2, params_item)

            # Status with color
            status_item = QTableWidgetItem(entry.status.upper())
            status_item.setTextAlignment(Qt.AlignCenter)
            status_colors = {
                "queued": QColor(200, 200, 200),
                "running": QColor(255, 230, 150),
                "completed": QColor(150, 255, 150),
                "failed": QColor(255, 150, 150),
                "aborted": QColor(255, 200, 150),
            }
            status_item.setBackground(status_colors.get(entry.status, QColor(255, 255, 255)))
            self._table.setItem(row, 3, status_item)

            # Progress
            if entry.status == "running":
                progress_str = f"{entry.progress:.0f}%"
            elif entry.status == "completed":
                progress_str = "100%"
            else:
                progress_str = "--"
            progress_item = QTableWidgetItem(progress_str)
            progress_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 4, progress_item)

    def _format_parameters(self, params: Dict[str, any]) -> str:
        """Format parameters for display.

        Args:
            params: Parameter dictionary.

        Returns:
            Formatted string summary.
        """
        parts = []
        if "exposure_time" in params:
            parts.append(f"exp={params['exposure_time']:.2f}s")
        if "center_wavelength" in params:
            parts.append(f"λ={params['center_wavelength']:.0f}nm")
        if "grating" in params:
            parts.append(f"g={params['grating']}")
        if "hbin" in params and params["hbin"] > 1:
            parts.append(f"hbin={params['hbin']}")
        if "vbin" in params and params["vbin"] > 1:
            parts.append(f"vbin={params['vbin']}")

        return ", ".join(parts) if parts else str(params)

    def get_experiment(self, exp_id: int) -> Optional[ExperimentEntry]:
        """Get experiment by ID.

        Args:
            exp_id: Experiment ID.

        Returns:
            ExperimentEntry or None if not found.
        """
        for entry in self._experiments:
            if entry.id == exp_id:
                return entry
        return None

    def clear(self) -> None:
        """Clear all experiments from the table."""
        self._experiments.clear()
        self._table.setRowCount(0)

    def clear_completed(self) -> None:
        """Remove completed/failed/aborted experiments."""
        self._experiments = [
            e for e in self._experiments
            if e.status not in ("completed", "failed", "aborted")
        ]
        self._update_table()
