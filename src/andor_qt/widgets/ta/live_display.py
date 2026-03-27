"""TALiveDisplayWidget — real-time ΔI/I₀ visualization panel.

Panes:
1. Raw spectra — pump-ON / pump-OFF / difference (wavelength + pixel axes)
2. ΔI/I₀ spectrum — current delay point
3. Kinetic trace — ΔI/I₀ vs. delay at a user-selected probe wavelength
4. FFT of kinetic trace
5. 2-D heatmap — full delay × wavelength ΔI/I₀ matrix

Slots (called from the engine via signals):
- ``on_signal_updated(delay_ps, wavelengths, delta_signal)``
- ``on_map_updated(delays, wavelengths, signal_matrix)``
- ``on_raw_pair_updated(pumped, ref, n_matched, n_discarded, n_frames)``
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from andor_qt.ta.scan_config import ps_to_um, um_to_ps

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class _PsToUmAxis(pg.AxisItem):
    """Top axis that shows ps labels when the main (bottom) axis is in µm."""

    def tickStrings(self, values, scale, spacing):
        return [f"{um_to_ps(v):.2f}" for v in values]


class TALiveDisplayWidget(QGroupBox):
    """Real-time ΔI/I₀ display with spectrum, kinetic, FFT, and heatmap panes."""

    def __init__(self, parent=None):
        super().__init__("TA Live Display", parent)
        self._kinetic_delays: list = []
        self._kinetic_signals: list = []
        self._wavelengths: np.ndarray = np.array([])
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(2)

        # Use a vertical splitter so user can resize panes
        splitter = QSplitter(Qt.Orientation.Vertical)

        # --- 1. Raw spectra (ON / OFF / difference) ---
        raw_widget = QWidget()
        raw_layout = QVBoxLayout(raw_widget)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(0)

        self._raw_plot = pg.PlotWidget()
        self._raw_plot.setLabel("left", "Counts")
        self._raw_plot.setLabel("bottom", "Wavelength (nm)")
        self._raw_plot.setMinimumHeight(120)
        self._raw_curve_on = self._raw_plot.plot(
            pen=pg.mkPen("r", width=1.2), name="ON"
        )
        self._raw_curve_off = self._raw_plot.plot(
            pen=pg.mkPen("b", width=1.2), name="OFF"
        )
        self._raw_curve_diff = self._raw_plot.plot(
            pen=pg.mkPen("g", width=1.2), name="ON\u2212OFF"
        )
        self._raw_plot.addLegend(offset=(60, 5))
        raw_layout.addWidget(self._raw_plot)

        # Phase stats compact row
        self._phase_stats_label = QLabel("Waiting for data...")
        self._phase_stats_label.setStyleSheet("color: gray; font-size: 10px; padding: 0 4px;")
        raw_layout.addWidget(self._phase_stats_label)
        splitter.addWidget(raw_widget)

        # --- 2. ΔI/I₀ spectrum ---
        self._signal_plot = pg.PlotWidget()
        self._signal_plot.setLabel("left", "\u0394I/I\u2080")
        self._signal_plot.setLabel("bottom", "Wavelength (nm)")
        self._signal_plot.setMinimumHeight(100)
        self._signal_curve = self._signal_plot.plot(pen="y")
        splitter.addWidget(self._signal_plot)

        # --- 3. Kinetic trace + FFT ---
        kinetic_widget = QWidget()
        kinetic_layout = QVBoxLayout(kinetic_widget)
        kinetic_layout.setContentsMargins(0, 0, 0, 0)
        kinetic_layout.setSpacing(2)

        # Probe wavelength selector (compact)
        selector_row = QHBoxLayout()
        selector_row.setContentsMargins(4, 0, 4, 0)
        selector_row.addWidget(QLabel("Probe \u03bb:"))
        self._probe_wl_spin = QDoubleSpinBox()
        self._probe_wl_spin.setRange(0.0, 10000.0)
        self._probe_wl_spin.setDecimals(1)
        self._probe_wl_spin.setSingleStep(1.0)
        self._probe_wl_spin.setValue(600.0)
        self._probe_wl_spin.setSuffix(" nm")
        self._probe_wl_spin.setFixedWidth(100)
        self._probe_wl_spin.valueChanged.connect(self._update_kinetic_curve)
        selector_row.addWidget(self._probe_wl_spin)
        selector_row.addStretch()
        kinetic_layout.addLayout(selector_row)

        ps_top_axis = _PsToUmAxis(orientation="top")
        ps_top_axis.setLabel("Delay (ps)")
        self._kinetic_plot = pg.PlotWidget(axisItems={"top": ps_top_axis})
        self._kinetic_plot.setLabel("left", "\u0394I/I\u2080")
        self._kinetic_plot.setLabel("bottom", "Position (\u00b5m)")
        self._kinetic_plot.showAxis("top")
        self._kinetic_plot.setMinimumHeight(120)
        self._kinetic_curve = self._kinetic_plot.plot(pen="c", symbol="o", symbolSize=3)
        kinetic_layout.addWidget(self._kinetic_plot)

        self._fft_plot = pg.PlotWidget()
        self._fft_plot.setLabel("left", "Amplitude")
        self._fft_plot.setLabel("bottom", "Frequency (THz)")
        self._fft_plot.setMinimumHeight(80)
        self._fft_plot.showGrid(x=True, y=True, alpha=0.3)
        self._fft_curve = self._fft_plot.plot(pen="c")
        kinetic_layout.addWidget(self._fft_plot)

        splitter.addWidget(kinetic_widget)

        # --- 4. 2-D heatmap ---
        self._heatmap_gw = pg.GraphicsLayoutWidget()
        self._heatmap_gw.setMinimumHeight(120)
        heatmap_ps_axis = _PsToUmAxis(orientation="top")
        heatmap_ps_axis.setLabel("Delay (ps)")
        self._heatmap_plot = self._heatmap_gw.addPlot(
            title="\u0394I/I\u2080 Map",
            axisItems={"top": heatmap_ps_axis},
        )
        self._heatmap_plot.setLabel("left", "Wavelength (nm)")
        self._heatmap_plot.setLabel("bottom", "Position (\u00b5m)")
        self._heatmap_plot.showAxis("top")
        self._image_item = pg.ImageItem()
        self._heatmap_plot.addItem(self._image_item)
        self._colorbar = pg.ColorBarItem(values=(-0.01, 0.01), colorMap="CET-D1")
        self._colorbar.setImageItem(self._image_item, insert_in=self._heatmap_plot)
        splitter.addWidget(self._heatmap_gw)

        # Set initial proportions (raw:signal:kinetic+fft:heatmap)
        splitter.setSizes([150, 120, 250, 150])

        root.addWidget(splitter)

    # -- public API --------------------------------------------------------

    @property
    def signal_plot(self) -> pg.PlotWidget:
        return self._signal_plot

    @property
    def kinetic_plot(self) -> pg.PlotWidget:
        return self._kinetic_plot

    @property
    def heatmap_plot(self) -> pg.PlotItem:
        return self._heatmap_plot

    @property
    def probe_wavelength(self) -> float:
        return self._probe_wl_spin.value()

    @probe_wavelength.setter
    def probe_wavelength(self, value: float) -> None:
        self._probe_wl_spin.setValue(value)

    # -- slots -------------------------------------------------------------

    @Slot(object, object, int, int, int)
    def on_raw_pair_updated(
        self,
        pumped: np.ndarray,
        ref: np.ndarray,
        n_matched: int,
        n_discarded: int,
        n_frames: int,
    ) -> None:
        """Update raw spectra plot and phase match indicators."""
        # Use wavelength axis if available, otherwise pixel index
        if len(self._wavelengths) > 0 and len(self._wavelengths) == len(pumped):
            x = self._wavelengths
        else:
            x = np.arange(len(pumped))

        self._raw_curve_on.setData(x, pumped)
        self._raw_curve_off.setData(x, ref)
        self._raw_curve_diff.setData(x, pumped - ref)

        valid_pct = 100.0 * (2 * n_matched) / n_frames if n_frames > 0 else 0.0
        self._phase_stats_label.setText(
            f"Matched: {n_matched}  Discarded: {n_discarded}  "
            f"({valid_pct:.0f}% valid)  |  "
            f"ON mean: {pumped.mean():.0f}  OFF mean: {ref.mean():.0f}  "
            f"Diff mean: {(pumped - ref).mean():.1f}"
        )

    @Slot(float, object, object)
    def on_signal_updated(
        self,
        delay_ps: float,
        wavelengths: np.ndarray,
        delta_signal: np.ndarray,
    ) -> None:
        """Update the ΔI/I₀ spectrum pane and accumulate kinetic data."""
        wl = np.asarray(wavelengths)
        sig = np.asarray(delta_signal)

        self._signal_curve.setData(wl, sig)
        self._signal_plot.setTitle(
            f"\u0394I/I\u2080 Spectrum  (t = {delay_ps:.1f} ps)"
        )

        if len(wl) > 0 and len(self._wavelengths) == 0:
            self._wavelengths = wl
            self._probe_wl_spin.setRange(float(wl[0]), float(wl[-1]))
            self._probe_wl_spin.setValue(float(wl[len(wl) // 2]))

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
        """Update the 2-D heatmap."""
        d = np.asarray(delays)
        wl = np.asarray(wavelengths)
        mat = np.asarray(signal_matrix)

        if mat.ndim != 2 or len(d) == 0 or len(wl) == 0:
            return

        self._image_item.setImage(mat)

        if len(wl) > 1 and len(d) > 1:
            d_um = np.array([ps_to_um(v) for v in d])
            self._image_item.setRect(
                float(d_um[0]), float(wl[0]),
                float(d_um[-1] - d_um[0]), float(wl[-1] - wl[0]),
            )

        vmax = float(np.nanmax(np.abs(mat))) or 0.01
        self._colorbar.setLevels((-vmax, vmax))

    # -- internal ----------------------------------------------------------

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
        delays_ps = np.array(self._kinetic_delays[:len(kinetic)])
        positions_um = np.array([ps_to_um(d) for d in delays_ps])
        self._kinetic_curve.setData(positions_um, kinetic)
        self._kinetic_plot.setTitle(
            f"Kinetic Trace  (\u03bb = {probe_nm:.1f} nm)"
        )

        # FFT (need at least 4 uniformly spaced points)
        if len(kinetic) >= 4 and len(delays_ps) >= 4:
            dt_ps = np.mean(np.diff(delays_ps))
            if abs(dt_ps) > 1e-12:
                signal = kinetic - kinetic.mean()
                window = np.hanning(len(signal))
                fft_vals = np.abs(np.fft.rfft(signal * window))
                freqs_thz = np.fft.rfftfreq(len(signal), d=dt_ps)
                self._fft_curve.setData(freqs_thz[1:], fft_vals[1:])
                self._fft_plot.setTitle(
                    f"FFT  (\u0394t = {dt_ps:.3f} ps, "
                    f"max freq = {freqs_thz[-1]:.1f} THz)"
                )

    def reset_phase_stats(self) -> None:
        """Reset phase indicators for a new delay point."""
        self._phase_stats_label.setText("Waiting for data...")

    def clear(self) -> None:
        """Reset all plots and kinetic buffers to empty state."""
        self._kinetic_delays.clear()
        self._kinetic_signals.clear()
        self._wavelengths = np.array([])
        self._raw_curve_on.setData([], [])
        self._raw_curve_off.setData([], [])
        self._raw_curve_diff.setData([], [])
        self._fft_curve.setData([], [])
        self.reset_phase_stats()
        self._signal_curve.setData([], [])
        self._kinetic_curve.setData([], [])
        self._image_item.setImage(np.zeros((1, 1)))
        self._signal_plot.setTitle("\u0394I/I\u2080 Spectrum")
        self._kinetic_plot.setTitle("Kinetic Trace")
        self._fft_plot.setTitle("FFT")
