"""T0Finder — automatic optical time-zero locator.

Performs a two-stage coarse→fine scan to find the pump-probe t0.

Algorithm
---------
1. **Coarse scan**: steps through delays from ``-coarse_range_ps`` to
   ``+coarse_range_ps`` in ``coarse_step_ps`` increments.
   Records the mean absolute ΔI/I₀ at each point.
2. **Onset detection**: finds the first delay where ``|mean(ΔI/I₀)| > threshold``.
3. **Fine scan**: scans from ``(onset - fine_range_ps)`` to
   ``(onset + fine_range_ps)`` in ``fine_step_ps`` increments.
4. **Max-gradient refinement**: picks the delay with the highest gradient
   in the ΔI/I₀ signal.
5. Emits ``t0_found(t0_ps, t0_mm)`` with the result.

Runs in a ``QThread`` for GUI responsiveness.
"""

from __future__ import annotations

import logging
import threading

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from andor_qt.ta.acquisition import acquire_delta_signal_at_delay
from andor_qt.ta.scan_config import TAScanConfig

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Speed of light for mm↔ps conversion (double-pass)
_C_MM_PS = 0.299792458  # mm/ps


class _T0SearchWorker(QObject):
    """Worker that runs the coarse/fine t0 search in a QThread."""

    t0_found = Signal(float, float)   # t0_ps, t0_mm
    progress = Signal(int, int)        # current, total
    error = Signal(str)
    aborted = Signal()

    def __init__(self):
        super().__init__()
        self._abort_event = threading.Event()

    def setup(
        self,
        hw_manager,
        coarse_range_ps: float,
        coarse_step_ps: float,
        fine_range_ps: float,
        fine_step_ps: float,
        threshold: float,
    ):
        self._hw = hw_manager
        self._coarse_range = coarse_range_ps
        self._coarse_step = coarse_step_ps
        self._fine_range = fine_range_ps
        self._fine_step = fine_step_ps
        self._threshold = threshold
        self._abort_event.clear()

    def _make_config(self, n_averages: int = 1) -> TAScanConfig:
        return TAScanConfig(
            delay_list=[0.0],
            n_averages=n_averages,
            n_scans=1,
            acquisition_mode="boxcar",
            scan_direction="forward",
            sample_name="_t0search",
        )

    def run(self) -> None:
        try:
            config = self._make_config()

            # --- Coarse scan ---
            n_steps = int((2 * self._coarse_range) / self._coarse_step) + 1
            coarse_delays = np.linspace(
                -self._coarse_range, self._coarse_range, n_steps
            ).tolist()

            fine_delays_est = int((2 * self._fine_range) / self._fine_step) + 1
            total = n_steps + fine_delays_est
            step = [0]

            coarse_signals = []

            for delay_ps in coarse_delays:
                if self._abort_event.is_set():
                    self.aborted.emit()
                    return
                od = acquire_delta_signal_at_delay(delay_ps, self._hw, config)
                coarse_signals.append(float(np.mean(np.abs(od))))
                step[0] += 1
                self.progress.emit(step[0], total)

            # --- Find onset ---
            onset_ps = coarse_delays[-1]  # default: end of range
            for delay, sig in zip(coarse_delays, coarse_signals):
                if sig > self._threshold:
                    onset_ps = delay
                    break

            # --- Fine scan ---
            fine_start = onset_ps - self._fine_range
            fine_end = onset_ps + self._fine_range
            n_fine = int((fine_end - fine_start) / self._fine_step) + 1
            fine_delays = np.linspace(fine_start, fine_end, max(n_fine, 2)).tolist()

            fine_signals = []
            for delay_ps in fine_delays:
                if self._abort_event.is_set():
                    self.aborted.emit()
                    return
                od = acquire_delta_signal_at_delay(delay_ps, self._hw, config)
                fine_signals.append(float(np.mean(np.abs(od))))
                step[0] += 1
                self.progress.emit(step[0], total)

            # --- Max-gradient refinement ---
            fine_arr = np.array(fine_signals)
            if len(fine_arr) > 1:
                gradients = np.abs(np.gradient(fine_arr))
                best_idx = int(np.argmax(gradients))
            else:
                best_idx = 0

            t0_ps = float(fine_delays[best_idx])
            t0_mm = (t0_ps * _C_MM_PS) / 2.0  # single-pass position

            self.t0_found.emit(t0_ps, t0_mm)

        except Exception as exc:
            log.exception("T0Finder error")
            self.error.emit(str(exc))


class T0Finder(QObject):
    """Automatic optical t0 finder.

    Emits ``t0_found(t0_ps, t0_mm)`` when the search completes.

    Example::

        finder = T0Finder()
        finder.t0_found.connect(lambda ps, mm: print(f"t0 = {ps:.2f} ps"))
        finder.find_t0(hw, coarse_range_ps=50, coarse_step_ps=2,
                       fine_range_ps=4, fine_step_ps=0.5)
    """

    t0_found = Signal(float, float)  # t0_ps, t0_mm
    progress = Signal(int, int)       # current_step, total_steps
    error = Signal(str)
    aborted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _T0SearchWorker()
        self._worker.moveToThread(self._thread)

        self._worker.t0_found.connect(self.t0_found)
        self._worker.progress.connect(self.progress)
        self._worker.error.connect(self.error)
        self._worker.aborted.connect(self.aborted)

        self._worker.t0_found.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._worker.aborted.connect(self._thread.quit)

        self._thread.started.connect(self._worker.run)

    def find_t0(
        self,
        hw_manager,
        coarse_range_ps: float = 50.0,
        coarse_step_ps: float = 2.0,
        fine_range_ps: float = 4.0,
        fine_step_ps: float = 0.5,
        threshold: float = 0.01,
    ) -> None:
        """Start the t0 search in a background thread.

        Args:
            hw_manager: Hardware manager.
            coarse_range_ps: Half-range for coarse scan in ps.
            coarse_step_ps: Step size for coarse scan in ps.
            fine_range_ps: Half-range for fine scan around onset in ps.
            fine_step_ps: Step size for fine scan in ps.
            threshold: |ΔI/I₀| threshold for onset detection.
        """
        if self._thread.isRunning():
            log.warning("T0Finder already running")
            return

        self._worker.setup(
            hw_manager,
            coarse_range_ps,
            coarse_step_ps,
            fine_range_ps,
            fine_step_ps,
            threshold,
        )
        self._thread.start()

    def abort(self) -> None:
        """Abort the search."""
        self._worker._abort_event.set()
