"""TA Monitor Engine — continuous acquisition at a fixed delay.

Repeatedly calls ``acquire_delta_signal_at_delay`` at the current stage
position, emitting live ΔI/I₀ spectra and a running average for signal
optimization before a full scan.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot

from andor_qt.ta.acquisition import acquire_delta_signal_at_delay
from andor_qt.ta.scan_config import TAScanConfig

log = logging.getLogger(__name__)


class _MonitorWorker(QObject):
    """Worker that runs continuous acquisition cycles in a QThread."""

    cycle_completed = Signal(object, object, object)  # (wavelengths, delta, avg_delta)
    raw_pair_updated = Signal(object, object, int, int, int)
    status_updated = Signal(str)
    stopped = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._abort = threading.Event()
        self._config: Optional[TAScanConfig] = None
        self._hw = None
        self._camera_settings = None
        self._trigger_gen = None
        self._phase_reader = None
        self._wavelengths = np.array([])

    def setup(self, config, hw_manager, camera_settings=None,
              trigger_gen=None, phase_reader=None):
        self._config = config
        self._hw = hw_manager
        self._camera_settings = camera_settings
        self._trigger_gen = trigger_gen
        self._phase_reader = phase_reader
        self._abort.clear()

    def stop(self):
        self._abort.set()

    @Slot()
    def run(self):
        config = self._config
        hw = self._hw
        phase_reader = self._phase_reader
        trigger_gen = self._trigger_gen

        # Get wavelength calibration
        hbin = (self._camera_settings or {}).get("hbin", 1)
        if isinstance(hbin, str):
            hbin = int(hbin.replace("x", ""))
        get_wl = getattr(hw, "get_wavelengths", None)
        if callable(get_wl):
            self._wavelengths = np.asarray(get_wl(hbin=hbin))
        else:
            self._wavelengths = np.array([])

        # Apply camera settings
        _apply = getattr(getattr(hw, "camera", None), "apply_camera_settings", None)
        if callable(_apply) and self._camera_settings:
            _apply(self._camera_settings)

        # Start NI DAQ
        if trigger_gen is not None:
            trigger_gen.start()
        if phase_reader is not None:
            phase_reader.start()

        avg_stack = []
        cycle = 0

        try:
            while not self._abort.is_set():
                # Get current position — don't move, just read
                axis = getattr(
                    getattr(hw, "motion_manager", None),
                    "get_axis", lambda _: None
                )("delay")
                delay_ps = getattr(axis, "position_ps", 0.0) if axis else 0.0

                def _raw_cb(pumped, ref, n_matched, n_discarded, n_frames):
                    self.raw_pair_updated.emit(
                        pumped, ref, n_matched, n_discarded, n_frames
                    )

                delta = acquire_delta_signal_at_delay(
                    delay_ps, hw, config, dark=None,
                    camera_settings=self._camera_settings,
                    phase_reader=phase_reader,
                    raw_callback=_raw_cb,
                )

                cycle += 1
                avg_stack.append(delta)
                avg = np.mean(avg_stack, axis=0)

                self.cycle_completed.emit(self._wavelengths, delta, avg)

                pos_um = getattr(axis, "position", 0.0) * 1000 if axis else 0.0
                self.status_updated.emit(
                    f"Monitor cycle {cycle}  |  "
                    f"{delay_ps:.2f} ps ({pos_um:.0f} \u00b5m)  |  "
                    f"avg of {len(avg_stack)} cycles"
                )

        except Exception as exc:
            log.exception("Monitor error")
            self.error.emit(str(exc))
        finally:
            if trigger_gen is not None:
                trigger_gen.stop()
            if phase_reader is not None:
                phase_reader.stop()
            self.stopped.emit()


class TAMonitorEngine(QObject):
    """High-level monitor engine managing a QThread."""

    cycle_completed = Signal(object, object, object)
    raw_pair_updated = Signal(object, object, int, int, int)
    status_updated = Signal(str)
    stopped = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _MonitorWorker()
        self._worker.moveToThread(self._thread)

        self._worker.cycle_completed.connect(self.cycle_completed)
        self._worker.raw_pair_updated.connect(self.raw_pair_updated)
        self._worker.status_updated.connect(self.status_updated)
        self._worker.stopped.connect(self.stopped)
        self._worker.stopped.connect(self._thread.quit)
        self._worker.error.connect(self.error)
        self._worker.error.connect(self._thread.quit)

        self._thread.started.connect(self._worker.run)

    def start_monitor(self, config, hw_manager, camera_settings=None,
                      trigger_gen=None, phase_reader=None):
        if self._thread.isRunning():
            return
        self._worker.setup(config, hw_manager, camera_settings,
                           trigger_gen, phase_reader)
        self._thread.start()

    def stop(self):
        self._worker.stop()

    @property
    def is_running(self) -> bool:
        return self._thread.isRunning()
