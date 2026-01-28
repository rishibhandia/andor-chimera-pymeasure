"""1D spectrum plot widget using pyqtgraph.

This widget displays FVB spectrum data with wavelength axis.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

log = logging.getLogger(__name__)


class SpectrumPlotWidget(QWidget):
    """Widget for displaying 1D spectrum data.

    Features:
    - Wavelength axis (if calibration provided) or pixel axis
    - Auto-scaling
    - Interactive zoom/pan
    - Crosshair cursor with readout
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._wavelengths: Optional[np.ndarray] = None
        self._intensities: Optional[np.ndarray] = None

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

        # Create plot item
        self._plot_item = self._plot_widget.plot(
            pen=pg.mkPen(color="b", width=1),
            name="Spectrum",
        )

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

    def set_data(
        self,
        wavelengths: Optional[np.ndarray],
        intensities: np.ndarray,
    ) -> None:
        """Set spectrum data to display.

        Args:
            wavelengths: Wavelength array (or None for pixel axis).
            intensities: Intensity values.
        """
        self._wavelengths = wavelengths
        self._intensities = intensities

        if wavelengths is not None:
            self._plot_item.setData(wavelengths, intensities)
            self._plot_widget.setLabel("bottom", "Wavelength", units="nm")
        else:
            # Use pixel index as x-axis
            pixels = np.arange(len(intensities))
            self._plot_item.setData(pixels, intensities)
            self._plot_widget.setLabel("bottom", "Pixel")

        # Auto-range
        self._plot_widget.autoRange()

    def clear(self) -> None:
        """Clear the plot."""
        self._plot_item.setData([], [])
        self._wavelengths = None
        self._intensities = None

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
