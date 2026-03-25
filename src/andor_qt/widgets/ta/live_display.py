"""TALiveDisplayWidget — real-time ΔI/I₀ visualization panel.

Three pyqtgraph panes:
1. ΔI/I₀ spectrum — current delay point
2. Kinetic trace — ΔI/I₀ vs. delay at a user-selected probe wavelength
3. 2-D heatmap — full delay × wavelength ΔI/I₀ matrix

Slots (called from the engine via signals):
- ``on_signal_updated(delay_ps, wavelengths, delta_signal)``
- ``on_map_updated(delays, wavelengths, signal_matrix)``

The kinetic trace is computed internally from accumulated ``on_signal_updated``
calls. Use the probe wavelength spinbox to select which wavelength to track.
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class TALiveDisplayWidget(QGroupBox):
    """Real-time ΔI/I₀ display with spectrum, kinetic, and 2-D heatmap panes.

    Args:
        parent: Optional parent widget.
    """

    def __init__(self, parent=None):
        super().__init__("TA Live Display", parent)
        # Kinetic trace buffers — accumulated across signal_updated calls
        self._kinetic_delays: list = []
        self._kinetic_signals: list = []   # list of 1-D delta_signal arrays
        self._wavelengths: np.ndarray = np.array([])
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- ΔI/I₀ spectrum plot ---
        self._signal_plot = pg.PlotWidget(title="ΔI/I₀ Spectrum")
        self._signal_plot.setLabel("left", "ΔI/I₀")
        self._signal_plot.setLabel("bottom", "Wavelength (nm)")
        self._signal_curve = self._signal_plot.plot(pen="y")
        root.addWidget(self._signal_plot)

        # --- Kinetic trace plot + wavelength selector ---
        self._kinetic_plot = pg.PlotWidget(title="Kinetic Trace")
        self._kinetic_plot.setLabel("left", "ΔI/I₀")
        self._kinetic_plot.setLabel("bottom", "Delay (ps)")
        self._kinetic_curve = self._kinetic_plot.plot(pen="c", symbol="o", symbolSize=4)

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Probe λ (nm):"))
        self._probe_wl_spin = QDoubleSpinBox()
        self._probe_wl_spin.setRange(0.0, 10000.0)
        self._probe_wl_spin.setDecimals(1)
        self._probe_wl_spin.setSingleStep(1.0)
        self._probe_wl_spin.setValue(600.0)
        self._probe_wl_spin.valueChanged.connect(self._update_kinetic_curve)
        selector_row.addWidget(self._probe_wl_spin)
        selector_row.addStretch()

        kinetic_container = QGroupBox("Kinetic Trace")
        kinetic_layout = QVBoxLayout(kinetic_container)
        kinetic_layout.addLayout(selector_row)
        kinetic_layout.addWidget(self._kinetic_plot)
        root.addWidget(kinetic_container)

        # --- 2-D heatmap ---
        self._heatmap_plot = pg.PlotWidget(title="ΔI/I₀ Map")
        self._heatmap_plot.setLabel("left", "Wavelength (nm)")
        self._heatmap_plot.setLabel("bottom", "Delay (ps)")
        self._image_item = pg.ImageItem()
        self._heatmap_plot.addItem(self._image_item)
        self._colorbar = pg.ColorBarItem(
            values=(-0.01, 0.01), colorMap="CET-D1"
        )
        self._colorbar.setImageItem(self._image_item)
        root.addWidget(self._heatmap_plot)

    # -- public API --------------------------------------------------------

    @property
    def signal_plot(self) -> pg.PlotWidget:
        return self._signal_plot

    @property
    def kinetic_plot(self) -> pg.PlotWidget:
        return self._kinetic_plot

    @property
    def heatmap_plot(self) -> pg.PlotWidget:
        return self._heatmap_plot

    @property
    def probe_wavelength(self) -> float:
        """Currently selected probe wavelength in nm."""
        return self._probe_wl_spin.value()

    @probe_wavelength.setter
    def probe_wavelength(self, value: float) -> None:
        self._probe_wl_spin.setValue(value)

    # -- slots -------------------------------------------------------------

    @Slot(float, object, object)
    def on_signal_updated(
        self,
        delay_ps: float,
        wavelengths: np.ndarray,
        delta_signal: np.ndarray,
    ) -> None:
        """Update the ΔI/I₀ spectrum pane and accumulate kinetic data.

        Args:
            delay_ps: Current time delay in ps.
            wavelengths: Wavelength array in nm.
            delta_signal: ΔI/I₀ spectrum values.
        """
        wl = np.asarray(wavelengths)
        sig = np.asarray(delta_signal)

        # Update spectrum pane
        self._signal_curve.setData(wl, sig)
        self._signal_plot.setTitle(f"ΔI/I₀ Spectrum  (t = {delay_ps:.1f} ps)")

        # Initialise wavelength axis and selector range on first call
        if len(wl) > 0 and len(self._wavelengths) == 0:
            self._wavelengths = wl
            self._probe_wl_spin.setRange(float(wl[0]), float(wl[-1]))
            # Default to centre wavelength
            self._probe_wl_spin.setValue(float(wl[len(wl) // 2]))

        # Accumulate for kinetic trace
        self._kinetic_delays.append(delay_ps)
        self._kinetic_signals.append(sig)
        self._update_kinetic_curve()

    @Slot(object, object, object)
    def on_map_updated(
        self,
        delays: np.ndarray,
        wavelengths: np.ndarray,
        signal_matrix: np.ndarray,
    ) -> None:
        """Update the 2-D heatmap.

        Args:
            delays: Delay array in ps (rows of signal_matrix).
            wavelengths: Wavelength array in nm (columns of signal_matrix).
            signal_matrix: ΔI/I₀ matrix of shape (n_delays, n_wavelengths).
        """
        d = np.asarray(delays)
        wl = np.asarray(wavelengths)
        mat = np.asarray(signal_matrix)

        if mat.ndim != 2 or len(d) == 0 or len(wl) == 0:
            return

        # setImage expects (x, y): x = delay (columns), y = wavelength (rows)
        # mat shape is (n_delays, n_wavelengths) so no transpose needed
        self._image_item.setImage(mat)

        if len(wl) > 1 and len(d) > 1:
            self._image_item.setRect(
                float(d[0]), float(wl[0]),
                float(d[-1] - d[0]), float(wl[-1] - wl[0]),
            )

        vmax = float(np.nanmax(np.abs(mat))) or 0.01
        self._colorbar.setLevels((-vmax, vmax))

    def _update_kinetic_curve(self) -> None:
        """Recompute kinetic trace at current probe wavelength and redraw."""
        if not self._kinetic_signals:
            return

        probe_nm = self._probe_wl_spin.value()

        if len(self._wavelengths) > 0:
            idx = int(np.argmin(np.abs(self._wavelengths - probe_nm)))
        else:
            idx = 0

        kinetic = np.array([s[idx] for s in self._kinetic_signals if len(s) > idx])
        delays = np.array(self._kinetic_delays[:len(kinetic)])
        self._kinetic_curve.setData(delays, kinetic)
        self._kinetic_plot.setTitle(f"Kinetic Trace  (λ = {probe_nm:.1f} nm)")

    def clear(self) -> None:
        """Reset all plots and kinetic buffers to empty state."""
        self._kinetic_delays.clear()
        self._kinetic_signals.clear()
        self._wavelengths = np.array([])
        self._signal_curve.setData([], [])
        self._kinetic_curve.setData([], [])
        self._image_item.setImage(np.zeros((1, 1)))
        self._signal_plot.setTitle("ΔI/I₀ Spectrum")
        self._kinetic_plot.setTitle("Kinetic Trace")
