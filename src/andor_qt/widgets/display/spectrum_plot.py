"""1D spectrum plot widget using pyqtgraph with multi-trace overlay.

This widget displays FVB spectrum data with wavelength axis and supports
overlaying multiple traces with individual visibility control.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

log = logging.getLogger(__name__)


@dataclass
class TraceData:
    """Data for a single spectrum trace on the plot."""

    id: int
    label: str
    wavelengths: Optional[np.ndarray]
    intensities: np.ndarray
    color: str
    visible: bool = True
    plot_item: Optional[pg.PlotCurveItem] = field(default=None, repr=False)


class SpectrumPlotWidget(QWidget):
    """Widget for displaying 1D spectrum data with multi-trace overlay.

    Features:
    - Wavelength axis (if calibration provided) or pixel axis
    - Multiple overlaid traces with distinct colors
    - Per-trace visibility toggle
    - Auto-scaling
    - Interactive zoom/pan
    - Crosshair cursor with readout
    """

    COLOR_CYCLE = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]
    MAX_TRACES = 20

    # Signals for trace management
    trace_added = Signal(int, str, str)   # (id, label, color)
    trace_removed = Signal(int)           # (id,)
    traces_cleared = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._wavelengths: Optional[np.ndarray] = None
        self._intensities: Optional[np.ndarray] = None

        self._traces: Dict[int, TraceData] = {}
        self._trace_order: List[int] = []  # Maintains insertion order
        self._next_trace_id: int = 1
        self._color_index: int = 0
        self._live_trace_id: Optional[int] = None  # ID of the "live" trace for set_data()

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")

        # Configure plot
        self._plot_widget.setLabel("left", "Intensity", units="counts")
        self._plot_widget.setLabel("bottom", "Wavelength", units="nm")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Add crosshair
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen="g")
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen="g")
        self._plot_widget.addItem(self._vline, ignoreBounds=True)
        self._plot_widget.addItem(self._hline, ignoreBounds=True)

        # Connect mouse movement
        self._plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

        # Add cursor readout label
        self._cursor_label = pg.TextItem(text="", anchor=(0, 1))
        self._cursor_label.setPos(0, 0)
        self._plot_widget.addItem(self._cursor_label)

        layout.addWidget(self._plot_widget)

    @Slot(object)
    def _on_mouse_moved(self, pos) -> None:
        """Update crosshair and readout on mouse move."""
        if self._plot_widget.sceneBoundingRect().contains(pos):
            mouse_point = self._plot_widget.getPlotItem().vb.mapSceneToView(pos)
            x, y = mouse_point.x(), mouse_point.y()

            self._vline.setPos(x)
            self._hline.setPos(y)

            # Update cursor readout
            if self._wavelengths is not None and len(self._wavelengths) > 0:
                self._cursor_label.setText(f"λ: {x:.1f} nm, I: {y:.0f}")
            else:
                self._cursor_label.setText(f"Pixel: {x:.0f}, I: {y:.0f}")

    def _next_color(self) -> str:
        """Get the next color from the cycle."""
        color = self.COLOR_CYCLE[self._color_index % len(self.COLOR_CYCLE)]
        self._color_index += 1
        return color

    def _update_pen_widths(self) -> None:
        """Make the most recent trace thicker, older traces thinner."""
        for trace_id in self._trace_order:
            trace = self._traces[trace_id]
            if trace.plot_item is not None:
                is_latest = (trace_id == self._trace_order[-1])
                width = 2 if is_latest else 1
                trace.plot_item.setPen(pg.mkPen(color=trace.color, width=width))

    def add_trace(
        self,
        wavelengths: Optional[np.ndarray],
        intensities: np.ndarray,
        label: Optional[str] = None,
    ) -> int:
        """Add a new trace to the plot.

        Args:
            wavelengths: Wavelength array (or None for pixel axis).
            intensities: Intensity values.
            label: Display label for the trace. Auto-generated if None.

        Returns:
            Integer trace ID for later reference.
        """
        # Enforce max traces by removing oldest
        while len(self._traces) >= self.MAX_TRACES:
            oldest_id = self._trace_order[0]
            self._remove_trace_internal(oldest_id)

        trace_id = self._next_trace_id
        self._next_trace_id += 1

        if label is None:
            label = f"Trace {trace_id}"

        color = self._next_color()

        # Create the plot curve
        if wavelengths is not None:
            x_data = wavelengths
        else:
            x_data = np.arange(len(intensities))

        plot_item = self._plot_widget.plot(
            x_data, intensities,
            pen=pg.mkPen(color=color, width=2),
        )

        trace = TraceData(
            id=trace_id,
            label=label,
            wavelengths=wavelengths,
            intensities=intensities,
            color=color,
            visible=True,
            plot_item=plot_item,
        )

        self._traces[trace_id] = trace
        self._trace_order.append(trace_id)

        # Update wavelengths for cursor readout (use latest trace's data)
        self._wavelengths = wavelengths
        self._intensities = intensities

        # Update pen widths so latest is thicker
        self._update_pen_widths()

        # Auto-range
        self._plot_widget.autoRange()

        self.trace_added.emit(trace_id, label, color)
        return trace_id

    def _remove_trace_internal(self, trace_id: int) -> None:
        """Remove a trace without emitting signals."""
        if trace_id not in self._traces:
            return

        trace = self._traces[trace_id]
        if trace.plot_item is not None:
            self._plot_widget.removeItem(trace.plot_item)

        del self._traces[trace_id]
        self._trace_order.remove(trace_id)

        if self._live_trace_id == trace_id:
            self._live_trace_id = None

    def remove_trace(self, trace_id: int) -> None:
        """Remove a trace from the plot.

        Args:
            trace_id: ID of the trace to remove.
        """
        if trace_id not in self._traces:
            return

        self._remove_trace_internal(trace_id)

        # Update pen widths
        if self._trace_order:
            self._update_pen_widths()

        self.trace_removed.emit(trace_id)

    def set_trace_visible(self, trace_id: int, visible: bool) -> None:
        """Show or hide a trace on the plot.

        Args:
            trace_id: ID of the trace to toggle.
            visible: Whether the trace should be visible.
        """
        if trace_id not in self._traces:
            return

        trace = self._traces[trace_id]
        trace.visible = visible
        if trace.plot_item is not None:
            trace.plot_item.setVisible(visible)

    def clear_traces(self) -> None:
        """Remove all traces from the plot."""
        for trace_id in list(self._trace_order):
            self._remove_trace_internal(trace_id)

        self._wavelengths = None
        self._intensities = None
        self._live_trace_id = None

        self.traces_cleared.emit()

    def get_traces(self) -> List[TraceData]:
        """Get all traces in insertion order.

        Returns:
            List of TraceData objects.
        """
        return [self._traces[tid] for tid in self._trace_order]

    def set_data(
        self,
        wavelengths: Optional[np.ndarray],
        intensities: np.ndarray,
    ) -> None:
        """Set spectrum data to display (backward-compatible).

        Replaces the current "live" trace with the new data.
        If no live trace exists, creates one.

        Args:
            wavelengths: Wavelength array (or None for pixel axis).
            intensities: Intensity values.
        """
        # Remove previous live trace if it exists
        if self._live_trace_id is not None and self._live_trace_id in self._traces:
            self._remove_trace_internal(self._live_trace_id)

        self._live_trace_id = self.add_trace(wavelengths, intensities, label="Live")

        if wavelengths is not None:
            self._plot_widget.setLabel("bottom", "Wavelength", units="nm")
        else:
            self._plot_widget.setLabel("bottom", "Pixel")

    def clear(self) -> None:
        """Clear the plot (backward-compatible)."""
        self.clear_traces()

    def set_title(self, title: str) -> None:
        """Set plot title."""
        self._plot_widget.setTitle(title)

    @property
    def wavelengths(self) -> Optional[np.ndarray]:
        """Get current wavelength data."""
        return self._wavelengths

    @property
    def intensities(self) -> Optional[np.ndarray]:
        """Get current intensity data."""
        return self._intensities
