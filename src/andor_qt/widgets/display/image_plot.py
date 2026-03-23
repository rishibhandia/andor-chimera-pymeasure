"""2D image plot widget using pyqtgraph.

This widget displays CCD image data with colorbar.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

log = logging.getLogger(__name__)


class ImagePlotWidget(QWidget):
    """Widget for displaying 2D image data.

    Features:
    - Colormap display with histogram/level control
    - Wavelength axis (if calibration provided)
    - Interactive cursor readout (X, Y, Intensity)
    - Auto-contrast adjustment
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._wavelengths: Optional[np.ndarray] = None
        self._image_data: Optional[np.ndarray] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Use ImageView with an explicit PlotItem so axis ticks/labels are shown.
        # Without this, ImageView uses a plain ViewBox which has no labeled axes.
        self._image_view = pg.ImageView(view=pg.PlotItem())
        self._image_view.ui.roiBtn.hide()  # Hide ROI button
        self._image_view.ui.menuBtn.hide()  # Hide menu button

        # Set colormap
        self._image_view.setColorMap(pg.colormap.get("viridis"))

        # Label the axes
        view = self._image_view.getView()
        if hasattr(view, "setLabel"):
            view.setLabel("bottom", "Wavelength (nm)")
            view.setLabel("left", "Row")

        layout.addWidget(self._image_view)

        # Cursor readout
        self._cursor_label = QLabel("Position: --, Intensity: --")
        self._cursor_label.setStyleSheet("font-family: monospace;")
        layout.addWidget(self._cursor_label)

        # Connect mouse movement on the image
        self._image_view.getView().scene().sigMouseMoved.connect(self._on_mouse_moved)

    @Slot(object)
    def _on_mouse_moved(self, pos) -> None:
        """Update cursor readout on mouse move."""
        if self._image_data is None:
            return

        # Map position to view coordinates (wavelength units when calibrated)
        view_box = self._image_view.getView()
        if view_box.sceneBoundingRect().contains(pos):
            mouse_point = view_box.mapSceneToView(pos)
            n_rows, n_cols = self._image_data.shape

            if self._wavelengths is not None:
                wl = mouse_point.x()
                y = int(mouse_point.y())
                # Find nearest pixel column from wavelength
                x = int(np.searchsorted(self._wavelengths, wl))
                x = max(0, min(x, n_cols - 1))
                if 0 <= y < n_rows:
                    intensity = self._image_data[y, x]
                    self._cursor_label.setText(
                        f"λ: {wl:.1f} nm, Y: {y}, Intensity: {intensity:.0f}"
                    )
            else:
                x, y = int(mouse_point.x()), int(mouse_point.y())
                if 0 <= x < n_cols and 0 <= y < n_rows:
                    intensity = self._image_data[y, x]
                    self._cursor_label.setText(
                        f"X: {x}, Y: {y}, Intensity: {intensity:.0f}"
                    )

    def set_data(
        self,
        image: np.ndarray,
        wavelengths: Optional[np.ndarray] = None,
    ) -> None:
        """Set image data to display.

        Args:
            image: 2D numpy array (rows=Y, cols=X/wavelength).
            wavelengths: Optional wavelength array for X axis.
        """
        self._image_data = image
        self._wavelengths = wavelengths

        # Set image (ImageView expects [x, y] so we transpose).
        # When wavelengths are provided, map the x-axis to wavelength units so
        # the axis ticks show nm rather than pixel indices.
        if wavelengths is not None and len(wavelengths) >= 2:
            wl_start = float(wavelengths[0])
            wl_scale = float(wavelengths[-1] - wavelengths[0]) / (image.shape[1] - 1)
            self._image_view.setImage(
                image.T,
                autoLevels=True,
                autoRange=True,
                pos=(wl_start, 0),
                scale=(wl_scale, 1),
            )
        else:
            self._image_view.setImage(image.T, autoLevels=True, autoRange=True)

    def clear(self) -> None:
        """Clear the image."""
        self._image_view.clear()
        self._image_data = None
        self._wavelengths = None
        self._cursor_label.setText("Position: --, Intensity: --")

    def set_colormap(self, name: str) -> None:
        """Set the colormap.

        Args:
            name: Colormap name (e.g., 'viridis', 'plasma', 'inferno').
        """
        try:
            cmap = pg.colormap.get(name)
            self._image_view.setColorMap(cmap)
        except Exception as e:
            log.error(f"Failed to set colormap '{name}': {e}")

    def set_levels(self, vmin: float, vmax: float) -> None:
        """Set color levels manually.

        Args:
            vmin: Minimum value.
            vmax: Maximum value.
        """
        self._image_view.setLevels(vmin, vmax)

    def auto_levels(self) -> None:
        """Auto-adjust levels based on current data."""
        if self._image_data is not None:
            vmin, vmax = np.percentile(self._image_data, [1, 99])
            self.set_levels(vmin, vmax)

    @property
    def image_data(self) -> Optional[np.ndarray]:
        """Get current image data."""
        return self._image_data

    @property
    def wavelengths(self) -> Optional[np.ndarray]:
        """Get current wavelength data."""
        return self._wavelengths
