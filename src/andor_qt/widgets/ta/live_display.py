"""TALiveDisplayWidget — real-time ΔOD visualization panel.

Three pyqtgraph panes:
1. ΔOD spectrum — current delay point, with std shading
2. Kinetic trace — ΔOD vs. delay at a selected probe wavelength
3. 2-D heatmap — full delay × wavelength ΔOD matrix

Slots (called from the engine via signals):
- ``on_delta_od_updated(delay_ps, wavelengths, delta_od)``
- ``on_kinetic_updated(delays, kinetic)``
- ``on_map_updated(delays, wavelengths, od_matrix)``
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class TALiveDisplayWidget(QGroupBox):
    """Real-time ΔOD display with spectrum, kinetic, and 2-D heatmap panes.

    Args:
        parent: Optional parent widget.
    """

    def __init__(self, parent=None):
        super().__init__("TA Live Display", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- ΔOD spectrum plot ---
        self._delta_od_plot = pg.PlotWidget(title="ΔOD Spectrum")
        self._delta_od_plot.setLabel("left", "ΔOD")
        self._delta_od_plot.setLabel("bottom", "Wavelength (nm)")
        self._od_curve = self._delta_od_plot.plot(pen="y")
        root.addWidget(self._delta_od_plot)

        # --- Kinetic trace plot ---
        self._kinetic_plot = pg.PlotWidget(title="Kinetic Trace")
        self._kinetic_plot.setLabel("left", "ΔOD")
        self._kinetic_plot.setLabel("bottom", "Delay (ps)")
        self._kinetic_curve = self._kinetic_plot.plot(pen="c", symbol="o", symbolSize=4)
        root.addWidget(self._kinetic_plot)

        # --- 2-D heatmap ---
        self._heatmap_plot = pg.PlotWidget(title="ΔOD Map")
        self._heatmap_plot.setLabel("left", "Delay (ps)")
        self._heatmap_plot.setLabel("bottom", "Wavelength (nm)")
        self._image_item = pg.ImageItem()
        self._heatmap_plot.addItem(self._image_item)
        self._colorbar = pg.ColorBarItem(
            values=(-0.01, 0.01), colorMap="CET-D1"
        )
        self._colorbar.setImageItem(self._image_item)
        root.addWidget(self._heatmap_plot)

    # -- public API --------------------------------------------------------

    @property
    def delta_od_plot(self) -> pg.PlotWidget:
        return self._delta_od_plot

    @property
    def kinetic_plot(self) -> pg.PlotWidget:
        return self._kinetic_plot

    @property
    def heatmap_plot(self) -> pg.PlotWidget:
        return self._heatmap_plot

    @Slot(float, object, object)
    def on_delta_od_updated(
        self,
        delay_ps: float,
        wavelengths: np.ndarray,
        delta_od: np.ndarray,
    ) -> None:
        """Update the ΔOD spectrum pane.

        Args:
            delay_ps: Current time delay in ps.
            wavelengths: Wavelength array in nm.
            delta_od: ΔOD spectrum values.
        """
        wl = np.asarray(wavelengths)
        od = np.asarray(delta_od)
        self._od_curve.setData(wl, od)
        self._delta_od_plot.setTitle(f"ΔOD Spectrum  (t = {delay_ps:.2f} ps)")

    @Slot(object, object)
    def on_kinetic_updated(
        self,
        delays: np.ndarray,
        kinetic: np.ndarray,
    ) -> None:
        """Update the kinetic trace pane.

        Args:
            delays: Delay array in ps.
            kinetic: ΔOD values at the probe wavelength.
        """
        d = np.asarray(delays)
        k = np.asarray(kinetic)
        self._kinetic_curve.setData(d, k)

    @Slot(object, object, object)
    def on_map_updated(
        self,
        delays: np.ndarray,
        wavelengths: np.ndarray,
        od_matrix: np.ndarray,
    ) -> None:
        """Update the 2-D heatmap.

        Args:
            delays: Delay array in ps (rows of od_matrix).
            wavelengths: Wavelength array in nm (columns of od_matrix).
            od_matrix: ΔOD matrix of shape (n_delays, n_wavelengths).
        """
        d = np.asarray(delays)
        wl = np.asarray(wavelengths)
        mat = np.asarray(od_matrix)

        if mat.ndim != 2 or len(d) == 0 or len(wl) == 0:
            return

        # setImage expects (x, y) = (wavelengths, delays) → transpose
        self._image_item.setImage(mat.T)

        if len(wl) > 1 and len(d) > 1:
            self._image_item.setRect(
                float(wl[0]), float(d[0]),
                float(wl[-1] - wl[0]), float(d[-1] - d[0]),
            )

        # Update colorbar scale
        vmax = float(np.nanmax(np.abs(mat))) or 0.01
        self._colorbar.setLevels((-vmax, vmax))

    def clear(self) -> None:
        """Reset all plots to empty state."""
        self._od_curve.setData([], [])
        self._kinetic_curve.setData([], [])
        self._image_item.setImage(np.zeros((1, 1)))
        self._delta_od_plot.setTitle("ΔOD Spectrum")
