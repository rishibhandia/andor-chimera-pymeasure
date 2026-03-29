"""TA Monitor Engine — continuous acquisition at a fixed delay.

Repeatedly calls ``acquire_delta_signal_at_delay`` at the current stage
position, emitting live ΔI/I₀ spectra and a running average for signal
optimization before a full scan.

Also supports ``static_onoff`` mode: long-average pump+probe, then
long-average probe-only, compute ΔOD.
"""

from __future__ import annotations

import logging
import threading
import time as _time
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
    user_prompt = Signal(str)  # ask user to do something (e.g. block pump)
    static_completed = Signal(object, object, object, object)  # (wl, pump_avg, ref_avg, delta_od)
    single_phase_completed = Signal(str, object, object)  # (phase, wavelengths, avg_spectrum)
    stopped = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._abort = threading.Event()
        self._user_response = threading.Event()
        self._config: Optional[TAScanConfig] = None
        self._hw = None
        self._camera_settings = None
        self._trigger_gen = None
        self._phase_reader = None
        self._wavelengths = np.array([])

    def setup(
        self,
        config: TAScanConfig,
        hw_manager: object,
        camera_settings: Optional[dict] = None,
        trigger_gen: object = None,
        phase_reader: object = None,
        static_phase: Optional[str] = None,
    ) -> None:
        self._config = config
        self._hw = hw_manager
        self._camera_settings = camera_settings
        self._trigger_gen = trigger_gen
        self._phase_reader = phase_reader
        self._static_phase = static_phase
        self._abort.clear()
        self._user_response.clear()

    def stop(self) -> None:
        self._abort.set()
        self._user_response.set()

    def user_confirmed(self) -> None:
        """Called from UI thread when user confirms a prompt."""
        self._user_response.set()

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

        if config.acquisition_mode == "static_onoff" and self._static_phase:
            self._run_single_phase(config, hw)
        elif config.acquisition_mode == "static_onoff":
            self._run_static(config, hw, phase_reader, trigger_gen)
        else:
            self._run_continuous(config, hw, phase_reader, trigger_gen)

    def _run_continuous(self, config: TAScanConfig, hw: object, phase_reader: object, trigger_gen: object) -> None:
        """Standard monitor: continuous cycles at current position."""
        if trigger_gen is not None:
            trigger_gen.start()
        if phase_reader is not None:
            phase_reader.start()

        avg_stack = []
        cycle = 0

        try:
            while not self._abort.is_set():
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

    def _run_static(self, config: TAScanConfig, hw: object, phase_reader: object, trigger_gen: object) -> None:
        """Static ON/OFF: two long acquisitions with user prompt between."""
        camera = hw.camera

        try:
            # --- Phase 1: Pump ON ---
            self.status_updated.emit("Phase 1: Acquiring pump+probe (pump ON)...")
            log.info(f"Static ON/OFF phase 1: {config.n_averages} frames")

            pump_avg = self._acquire_long_average(
                hw, config, "Phase 1 (pump ON)"
            )

            if self._abort.is_set():
                self.stopped.emit()
                return

            # --- Prompt user to block pump ---
            self.status_updated.emit("Block the pump beam, then click Continue")
            self.user_prompt.emit("Block the pump beam and click Continue")
            self._user_response.clear()

            # Wait for user to confirm (or abort)
            while not self._user_response.is_set():
                if self._abort.is_set():
                    self.stopped.emit()
                    return
                _time.sleep(0.1)

            if self._abort.is_set():
                self.stopped.emit()
                return

            # --- Phase 2: Pump OFF ---
            self.status_updated.emit("Phase 2: Acquiring probe only (pump OFF)...")
            log.info(f"Static ON/OFF phase 2: {config.n_averages} frames")

            ref_avg = self._acquire_long_average(
                hw, config, "Phase 2 (pump OFF)"
            )

            if self._abort.is_set():
                self.stopped.emit()
                return

            # --- Compute ΔOD ---
            ref_safe = np.where(ref_avg == 0, 1.0, ref_avg)
            delta_od = -np.log10(pump_avg / ref_safe)

            log.info(f"Static ON/OFF complete: ΔOD range [{delta_od.min():.6f}, {delta_od.max():.6f}]")

            self.static_completed.emit(
                self._wavelengths, pump_avg, ref_avg, delta_od
            )
            self.status_updated.emit(
                f"Static ON/OFF complete  |  "
                f"\u0394OD range: [{delta_od.min():.4f}, {delta_od.max():.4f}]"
            )

        except Exception as exc:
            log.exception("Static ON/OFF error")
            self.error.emit(str(exc))
        finally:
            self.stopped.emit()

    def _run_single_phase(self, config: TAScanConfig, hw: object) -> None:
        """Acquire a single phase (pump ON or pump OFF) and emit result."""
        phase = self._static_phase
        label = "Pump ON" if phase == "pump" else "Pump OFF"
        try:
            self.status_updated.emit(f"Acquiring {label}...")
            avg, std, n = self._acquire_long_average(hw, config, label)
            self.single_phase_completed.emit(phase, self._wavelengths, avg)
            self.status_updated.emit(
                f"{label} complete — {n} frames, "
                f"mean={avg.mean():.1f}, std={std.mean():.2f}"
            )
        except Exception as exc:
            log.exception(f"Static {label} error")
            self.error.emit(str(exc))
        finally:
            self.stopped.emit()

    def _acquire_long_average(
        self, hw: object, config: TAScanConfig, phase_label: str,
    ) -> tuple[np.ndarray, np.ndarray, int]:
        """Acquire many frames and return mean, std, and count.

        Uses running sum and sum-of-squares for memory-efficient statistics.

        Returns:
            ``(mean, std, n_frames)`` where ``mean`` and ``std`` are 1-D arrays.
        """
        camera = hw.camera
        n_target = config.n_averages
        buf_size = getattr(camera, "get_circular_buffer_size", lambda: 12000)()
        max_chunk = max(1000, int(buf_size * 0.8))

        running_sum = None
        running_sum_sq = None
        collected = 0

        while collected < n_target and not self._abort.is_set():
            chunk = min(n_target - collected, max_chunk)

            camera.start_run_till_abort()

            try:
                wait_s = (chunk * 2.0) / 1000.0 * 1.2 + 0.05
                _time.sleep(wait_s)
                frames, n_read = camera.get_buffered_frames()
            finally:
                camera.abort_acquisition()

            if n_read == 0:
                break

            chunk_sum = frames.sum(axis=0)
            chunk_sum_sq = (frames.astype(np.float64) ** 2).sum(axis=0)
            if running_sum is None:
                running_sum = chunk_sum
                running_sum_sq = chunk_sum_sq
            else:
                running_sum += chunk_sum
                running_sum_sq += chunk_sum_sq
            collected += n_read

            # Emit running average so the live display updates during acquisition
            current_mean = running_sum / collected
            self.raw_pair_updated.emit(current_mean, current_mean, collected, 0, collected)

            pct = 100.0 * collected / n_target
            self.status_updated.emit(
                f"{phase_label}: {collected}/{n_target} frames ({pct:.0f}%)"
            )

        if running_sum is None or collected == 0:
            raise RuntimeError(f"Static {phase_label}: no frames acquired")

        mean = running_sum / collected
        variance = running_sum_sq / collected - mean ** 2
        std = np.sqrt(np.maximum(variance, 0.0))
        return mean, std, collected


class TAMonitorEngine(QObject):
    """High-level monitor engine managing a QThread."""

    cycle_completed = Signal(object, object, object)
    raw_pair_updated = Signal(object, object, int, int, int)
    status_updated = Signal(str)
    user_prompt = Signal(str)
    static_completed = Signal(object, object, object, object)
    single_phase_completed = Signal(str, object, object)
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
        self._worker.user_prompt.connect(self.user_prompt)
        self._worker.static_completed.connect(self.static_completed)
        self._worker.single_phase_completed.connect(self.single_phase_completed)
        self._worker.stopped.connect(self.stopped)
        self._worker.stopped.connect(self._thread.quit)
        self._worker.error.connect(self.error)
        self._worker.error.connect(self._thread.quit)

        self._thread.started.connect(self._worker.run)

    def start_monitor(
        self,
        config: TAScanConfig,
        hw_manager: object,
        camera_settings: Optional[dict] = None,
        trigger_gen: object = None,
        phase_reader: object = None,
        static_phase: Optional[str] = None,
    ) -> None:
        if self._thread.isRunning():
            return
        self._worker.setup(config, hw_manager, camera_settings,
                           trigger_gen, phase_reader, static_phase=static_phase)
        self._thread.start()

    def stop(self) -> None:
        self._worker.stop()

    def user_confirmed(self) -> None:
        """Forward user confirmation to worker thread."""
        self._worker.user_confirmed()

    @property
    def is_running(self) -> bool:
        return self._thread.isRunning()
