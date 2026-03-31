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
from PySide6.QtCore import QObject, Signal, Slot

from andor_qt.ta.engine_base import _EngineBase

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
        dark: Optional[np.ndarray] = None,
    ) -> None:
        self._config = config
        self._hw = hw_manager
        self._camera_settings = camera_settings
        self._trigger_gen = trigger_gen
        self._phase_reader = phase_reader
        self._static_phase = static_phase
        self._dark = dark
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
        from andor_qt.ta.acquisition import AcquisitionSession
        from andor_qt.ta.engine import _estimate_point_time_s, _format_time

        if trigger_gen is not None:
            trigger_gen.start()

        is_static = config.acquisition_mode == "static_onoff"
        est_cycle_s = _estimate_point_time_s(
            self._camera_settings or {}, config.n_averages, static=is_static,
        )
        if est_cycle_s > 0:
            self.status_updated.emit(f"Monitor starting — est. ~{_format_time(est_cycle_s)}/cycle")

        avg_stack = []
        cycle = 0

        log.info(f"=== MONITOR STARTED === mode={config.acquisition_mode}")
        is_chopper = config.acquisition_mode == "chopper_2x2" and phase_reader is not None

        # PFI13 hardware sync: wait for chopper rising edge before starting
        # the camera, so the first frame aligns with pump-ON phase.
        if is_chopper:
            self.status_updated.emit("Waiting for chopper phase sync...")
            log.info("Waiting for chopper rising edge on PFI13 (hardware)...")
            try:
                import nidaqmx
                from nidaqmx.constants import Edge
                device = config.nidaq_device
                with nidaqmx.Task("chopper_sync") as sync_task:
                    sync_task.ci_channels.add_ci_count_edges_chan(
                        f"{device}/ctr0",
                        edge=Edge.RISING,
                    )
                    sync_task.ci_channels[0].ci_count_edges_term = f"/{device}/PFI13"
                    sync_task.start()
                    sync_task.read(timeout=5.0)
                log.info("Chopper rising edge detected on PFI13 -- starting camera")
            except Exception as exc:
                log.warning(f"Chopper sync failed ({exc}) -- starting without sync")

        # Non-chopper modes: start phase reader before session
        if not is_chopper and phase_reader is not None:
            phase_reader.start()

        session = AcquisitionSession(
            hw, config,
            camera_settings=self._camera_settings,
            phase_reader=phase_reader,
        )

        try:
            with session:
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

                    try:
                        delta = session.acquire_one_cycle(
                            dark=self._dark, raw_callback=_raw_cb,
                        )
                    except RuntimeError:
                        # Zero frames in cycle — retry
                        continue

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
            log.info("=== MONITOR STOPPED ===")
            if trigger_gen is not None:
                trigger_gen.stop()
            if phase_reader is not None:
                phase_reader.stop()
            self.stopped.emit()

    def _run_static(self, config: TAScanConfig, hw: object, phase_reader: object, trigger_gen: object) -> None:
        """Static ON/OFF: two long acquisitions with user prompt between."""
        camera = hw.camera

        try:
            from andor_qt.ta.engine import _estimate_point_time_s, _format_time
            est_s = _estimate_point_time_s(
                self._camera_settings or {}, config.n_averages, static=True,
            )
            est_str = f" (est. ~{_format_time(est_s)})" if est_s > 0 else ""

            # --- Phase 1: Pump ON ---
            self.status_updated.emit(f"Phase 1: Acquiring pump+probe (pump ON)...{est_str}")
            log.info(f"Static ON/OFF phase 1: {config.n_averages} frames")

            pump_avg, _pump_std, _pump_n = self._acquire_static(
                hw, config, "Phase 1 (pump ON)", slot="pump",
            )

            if self._abort.is_set():
                self.stopped.emit()
                return

            # Emit pump result so raw display shows it on the ON curve
            self.raw_pair_updated.emit(pump_avg, pump_avg, _pump_n, 0, _pump_n)

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
            self.status_updated.emit(f"Phase 2: Acquiring probe only (pump OFF)...{est_str}")
            log.info(f"Static ON/OFF phase 2: {config.n_averages} frames")

            ref_avg, _ref_std, _ref_n = self._acquire_static(
                hw, config, "Phase 2 (pump OFF)",
                other_slot=pump_avg, slot="ref",
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
            from andor_qt.ta.engine import _estimate_point_time_s, _format_time
            est_s = _estimate_point_time_s(
                self._camera_settings or {}, config.n_averages, static=True,
            )
            est_str = f" (est. ~{_format_time(est_s)})" if est_s > 0 else ""
            self.status_updated.emit(f"Acquiring {label}...{est_str}")
            avg, std, n = self._acquire_static(
                hw, config, label, slot="pump" if phase == "pump" else "ref",
            )
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

    def _acquire_static(
        self, hw: object, config: TAScanConfig, phase_label: str,
        other_slot: Optional[np.ndarray] = None,
        slot: str = "pump",
    ) -> tuple[np.ndarray, np.ndarray, int]:
        """Acquire bulk frames with slot-aware progress and dark subtraction.

        Wraps ``acquire_static_at_delay`` with a progress callback that
        updates the correct raw display curve (pump or ref).

        Args:
            hw: Hardware manager.
            config: Scan config (uses n_averages).
            phase_label: Human-readable label for status updates.
            other_slot: Cached spectrum for the other raw display curve.
            slot: ``"pump"`` or ``"ref"`` — which raw curve to update live.
        """
        from andor_qt.ta.acquisition import acquire_static_at_delay

        _other = other_slot if other_slot is not None else np.array([])

        def _progress(running_mean, collected, n_target):
            if slot == "pump":
                pump = running_mean
                ref = _other if len(_other) == len(running_mean) else running_mean
            else:
                pump = _other if len(_other) == len(running_mean) else running_mean
                ref = running_mean
            self.raw_pair_updated.emit(pump, ref, collected, 0, collected)
            pct = 100.0 * collected / n_target
            self.status_updated.emit(
                f"{phase_label}: {collected}/{n_target} frames ({pct:.0f}%)"
            )

        return acquire_static_at_delay(
            hw, config.n_averages, self._abort,
            dark=self._dark,
            camera_settings=self._camera_settings,
            progress_cb=_progress,
        )


class TAMonitorEngine(_EngineBase):
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
        worker = _MonitorWorker()
        super().__init__(worker, [worker.stopped, worker.error], parent)

        worker.cycle_completed.connect(self.cycle_completed)
        worker.raw_pair_updated.connect(self.raw_pair_updated)
        worker.status_updated.connect(self.status_updated)
        worker.user_prompt.connect(self.user_prompt)
        worker.static_completed.connect(self.static_completed)
        worker.single_phase_completed.connect(self.single_phase_completed)
        worker.stopped.connect(self.stopped)
        worker.error.connect(self.error)

    def start_monitor(
        self,
        config: TAScanConfig,
        hw_manager: object,
        camera_settings: Optional[dict] = None,
        trigger_gen: object = None,
        phase_reader: object = None,
        static_phase: Optional[str] = None,
        dark: Optional[np.ndarray] = None,
    ) -> None:
        if self.is_running:
            return
        self._worker.setup(config, hw_manager, camera_settings,
                           trigger_gen, phase_reader, static_phase=static_phase,
                           dark=dark)
        self._start_worker()

    def stop(self) -> None:
        self._worker.stop()
