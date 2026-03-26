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
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

_GREEN = "background:#2ecc71;border-radius:6px;min-width:12px;min-height:12px;max-width:12px;max-height:12px;"
_RED   = "background:#e74c3c;border-radius:6px;min-width:12px;min-height:12px;max-width:12px;max-height:12px;"
_GRAY  = "background:#555;border-radius:6px;min-width:12px;min-height:12px;max-width:12px;max-height:12px;"


class _StatusLight(QWidget):
    """Small coloured LED + label indicator."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(4)
        self._dot = QLabel()
        self._dot.setStyleSheet(_GRAY)
        self._dot.setFixedSize(12, 12)
        self._text = QLabel(label)
        self._text.setStyleSheet("font-size: 10px;")
        layout.addWidget(self._dot)
        layout.addWidget(self._text)

    def set_ok(self, ok: bool | None) -> None:
        if ok is None:
            self._dot.setStyleSheet(_GRAY)
        elif ok:
            self._dot.setStyleSheet(_GREEN)
        else:
            self._dot.setStyleSheet(_RED)


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

        # --- Raw spectra + phase diagnostics ---
        raw_group = QGroupBox("Raw Spectra (Pump-ON / Pump-OFF)")
        raw_layout = QVBoxLayout(raw_group)

        self._raw_plot = pg.PlotWidget()
        self._raw_plot.setLabel("left", "Intensity (counts)")
        self._raw_plot.setLabel("bottom", "Pixel")
        self._raw_plot.setMinimumHeight(160)
        self._raw_curve_on = self._raw_plot.plot(pen=pg.mkPen("r", width=1.5), name="Pump-ON")
        self._raw_curve_off = self._raw_plot.plot(pen=pg.mkPen("b", width=1.5), name="Pump-OFF")
        self._raw_plot.addLegend()
        raw_layout.addWidget(self._raw_plot)

        # Phase match indicator row
        phase_row = QHBoxLayout()

        self._phase_on_label = _StatusLight("Pump-ON tags", parent=None)
        self._phase_off_label = _StatusLight("Pump-OFF tags", parent=None)
        phase_row.addWidget(self._phase_on_label)
        phase_row.addWidget(self._phase_off_label)
        phase_row.addStretch()

        self._phase_stats_label = QLabel("Waiting for first pair…")
        self._phase_stats_label.setStyleSheet("color: gray; font-size: 10px;")
        phase_row.addWidget(self._phase_stats_label)

        raw_layout.addLayout(phase_row)
        root.addWidget(raw_group)

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

        # FFT of kinetic trace
        self._fft_plot = pg.PlotWidget()
        self._fft_plot.setLabel("left", "Amplitude")
        self._fft_plot.setLabel("bottom", "Frequency (THz)")
        self._fft_plot.showGrid(x=True, y=True, alpha=0.3)
        self._fft_curve = self._fft_plot.plot(pen="c", name="FFT")

        kinetic_container = QGroupBox("Kinetic Trace")
        kinetic_layout = QVBoxLayout(kinetic_container)
        kinetic_layout.addLayout(selector_row)
        kinetic_layout.addWidget(self._kinetic_plot)
        kinetic_layout.addWidget(self._fft_plot)
        root.addWidget(kinetic_container)

        # --- 2-D heatmap + colorbar ---
        self._heatmap_gw = pg.GraphicsLayoutWidget()
        self._heatmap_plot = self._heatmap_gw.addPlot(title="ΔI/I₀ Map")
        self._heatmap_plot.setLabel("left", "Wavelength (nm)")
        self._heatmap_plot.setLabel("bottom", "Delay (ps)")
        self._image_item = pg.ImageItem()
        self._heatmap_plot.addItem(self._image_item)
        self._colorbar = pg.ColorBarItem(values=(-0.01, 0.01), colorMap="CET-D1")
        self._colorbar.setImageItem(self._image_item, insert_in=self._heatmap_plot)
        root.addWidget(self._heatmap_gw)

        # Trigger timing panel removed — SDG provides 500 Hz directly

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
        """Currently selected probe wavelength in nm."""
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
        px = np.arange(len(pumped))
        self._raw_curve_on.setData(px, pumped)
        self._raw_curve_off.setData(px, ref)

        match_pct = 100.0 * n_matched / n_frames if n_frames > 0 else 0.0
        self._phase_stats_label.setText(
            f"Matched: {n_matched}  Discarded: {n_discarded}  ({match_pct:.0f}% valid)"
        )
        self._phase_on_label.set_ok(True)   # pump-ON frame received
        self._phase_off_label.set_ok(True)  # pump-OFF frame received

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

    # -- timing traces -----------------------------------------------------

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
        self._kinetic_plot.setTitle(f"Kinetic Trace  (\u03bb = {probe_nm:.1f} nm)")

        # FFT of kinetic trace (need at least 4 points with uniform spacing)
        if len(kinetic) >= 4 and len(delays) >= 4:
            # Delays are in ps — compute spacing
            dt_ps = np.mean(np.diff(delays))
            if abs(dt_ps) > 1e-12:
                # Remove DC offset
                signal = kinetic - kinetic.mean()
                # Apply Hanning window to reduce spectral leakage
                window = np.hanning(len(signal))
                fft_vals = np.abs(np.fft.rfft(signal * window))
                freqs_thz = np.fft.rfftfreq(len(signal), d=dt_ps)  # 1/ps = THz
                # Skip DC component
                self._fft_curve.setData(freqs_thz[1:], fft_vals[1:])
                self._fft_plot.setTitle(f"FFT  (\u0394t = {dt_ps:.3f} ps, max freq = {freqs_thz[-1]:.1f} THz)")

    def reset_phase_stats(self) -> None:
        """Reset phase indicators for a new delay point."""
        self._phase_on_label.set_ok(None)
        self._phase_off_label.set_ok(None)
        self._phase_stats_label.setText("Waiting for first pair…")

    def clear(self) -> None:
        """Reset all plots and kinetic buffers to empty state."""
        self._kinetic_delays.clear()
        self._kinetic_signals.clear()
        self._wavelengths = np.array([])
        self._raw_curve_on.setData([], [])
        self._raw_curve_off.setData([], [])
        self._fft_curve.setData([], [])
        self.reset_phase_stats()
        self._signal_curve.setData([], [])
        self._kinetic_curve.setData([], [])
        self._image_item.setImage(np.zeros((1, 1)))
        self._signal_plot.setTitle("ΔI/I₀ Spectrum")
        self._kinetic_plot.setTitle("Kinetic Trace")
