"""Transient Absorption scan engine.

``TransientAbsorptionEngine`` orchestrates the full TA pump-probe scan loop.
It runs in a ``QThread`` so the GUI stays responsive, and communicates back
to the main thread via Qt signals.

Pause/resume uses ``threading.Event`` (set = running, clear = paused).
Abort uses a separate ``threading.Event`` (set = abort requested).

Signals
-------
scan_started(int)
    Emitted when a new scan begins. Argument is the scan index.
point_started(int, float)
    Emitted before acquiring each delay point. Arguments: scan_idx, delay_ps.
point_completed(int, float)
    Emitted after each delay point. Arguments: scan_idx, delay_ps.
scan_completed()
    Emitted when all scans finish successfully.
aborted()
    Emitted when the scan is aborted.
error(str)
    Emitted on unhandled exception. Argument is the error message.
signal_updated(float, object, object)
    Emitted with (delay_ps, wavelengths, delta_signal) after each point.
map_updated(object, object, object)
    Emitted with (delays, wavelengths, delta_signal_matrix) after each point.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from andor_qt.ta.acquisition import acquire_delta_signal_at_delay
from andor_qt.ta.scan_config import TAScanConfig

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class _ScanWorker(QObject):
    """QObject that runs in a QThread and executes the scan loop."""

    # Status signals
    scan_started = Signal(int)
    point_started = Signal(int, float)
    point_completed = Signal(int, float)
    scan_completed = Signal()
    aborted = Signal()
    error = Signal(str)

    # Data signals
    signal_updated = Signal(float, object, object)
    map_updated = Signal(object, object, object)

    def __init__(self):
        super().__init__()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start in running state
        self._abort_event = threading.Event()
        self._config: Optional[TAScanConfig] = None
        self._hw_manager = None
        self._writer = None

    def setup(self, config: TAScanConfig, hw_manager, writer, camera_settings=None) -> None:
        """Configure the worker before starting."""
        self._config = config
        self._hw_manager = hw_manager
        self._writer = writer
        self._camera_settings = camera_settings
        self._abort_event.clear()
        self._pause_event.set()

    def run(self) -> None:
        """Execute the scan loop. Called from QThread."""
        config = self._config
        hw = self._hw_manager
        writer = self._writer

        # Accumulated data for map updates
        all_delays = []
        all_signals = []  # list of 1-D arrays

        # Apply trigger mode once before the scan, restore on exit
        trigger_mode = (self._camera_settings or {}).get("trigger_mode", "internal")
        _apply = getattr(getattr(hw, "camera", None), "apply_camera_settings", None)
        if callable(_apply) and self._camera_settings:
            _apply(self._camera_settings)

        try:
            for scan_idx in range(config.n_scans):
                if self._abort_event.is_set():
                    self.aborted.emit()
                    return

                self.scan_started.emit(scan_idx)

                if writer is not None:
                    writer.begin_scan(scan_idx)

                ordered = config.ordered_delays(scan_idx)

                for delay_ps in ordered:
                    # Check abort
                    if self._abort_event.is_set():
                        self.aborted.emit()
                        return

                    # Wait if paused
                    while not self._pause_event.is_set():
                        if self._abort_event.is_set():
                            self.aborted.emit()
                            return
                        self._pause_event.wait(timeout=0.1)

                    self.point_started.emit(scan_idx, delay_ps)

                    delta_signal = acquire_delta_signal_at_delay(
                        delay_ps, hw, config, dark=None,
                        camera_settings=self._camera_settings,
                    )

                    if writer is not None:
                        writer.write_point(scan_idx, delay_ps, delta_signal)

                    get_wl = getattr(hw, "get_wavelengths", None)
                    wavelengths = np.asarray(get_wl()) if callable(get_wl) else np.array([])
                    self.signal_updated.emit(delay_ps, wavelengths, delta_signal)

                    # Update 2-D map
                    all_delays.append(delay_ps)
                    all_signals.append(delta_signal)
                    if len(all_signals) > 0:
                        signal_matrix = np.array(all_signals)
                        self.map_updated.emit(
                            np.array(all_delays), wavelengths, signal_matrix
                        )

                    self.point_completed.emit(scan_idx, delay_ps)

            self.scan_completed.emit()

        except Exception as exc:
            log.exception("TA engine error")
            self.error.emit(str(exc))

        finally:
            # Always restore to internal trigger after scan ends or aborts
            if trigger_mode == "external" and callable(_apply):
                try:
                    _apply({"trigger_mode": "internal"})
                except Exception:
                    pass


class TransientAbsorptionEngine(QObject):
    """High-level engine for TA pump-probe scanning.

    Manages a QThread and exposes signals mirroring ``_ScanWorker``.
    """

    # Re-export signals from worker
    scan_started = Signal(int)
    point_started = Signal(int, float)
    point_completed = Signal(int, float)
    scan_completed = Signal()
    aborted = Signal()
    error = Signal(str)
    signal_updated = Signal(float, object, object)
    map_updated = Signal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _ScanWorker()
        self._worker.moveToThread(self._thread)

        # Forward worker signals
        self._worker.scan_started.connect(self.scan_started)
        self._worker.point_started.connect(self.point_started)
        self._worker.point_completed.connect(self.point_completed)
        self._worker.scan_completed.connect(self.scan_completed)
        self._worker.aborted.connect(self.aborted)
        self._worker.error.connect(self.error)
        self._worker.signal_updated.connect(self.signal_updated)
        self._worker.map_updated.connect(self.map_updated)

        # Stop thread when scan finishes
        self._worker.scan_completed.connect(self._thread.quit)
        self._worker.aborted.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.started.connect(self._worker.run)

    def start_scan(self, config: TAScanConfig, hw_manager, writer=None, camera_settings=None) -> None:
        """Start the TA scan in a background thread.

        Args:
            config: Scan parameters.
            hw_manager: Hardware manager.
            writer: Optional ``TADataWriter`` (already opened).
            camera_settings: Optional dict passed to apply_camera_settings()
                before each acquisition point.
        """
        if self._thread.isRunning():
            log.warning("Scan already running")
            return

        self._worker.setup(config, hw_manager, writer, camera_settings=camera_settings)
        self._thread.start()

    def pause(self) -> None:
        """Pause the scan after the current delay point completes."""
        self._worker._pause_event.clear()

    def resume(self) -> None:
        """Resume a paused scan."""
        self._worker._pause_event.set()

    def abort(self) -> None:
        """Abort the scan as soon as possible."""
        self._worker._abort_event.set()
        self._worker._pause_event.set()  # Unblock if paused

    def emergency_stop(self) -> None:
        """Abort scan and stop all motion."""
        self.abort()

    def acquire_dark(self, hw_manager) -> np.ndarray:
        """Acquire a dark spectrum (blocking, called from main thread).

        Args:
            hw_manager: Hardware manager.

        Returns:
            Dark spectrum as numpy array.
        """
        return np.asarray(hw_manager.camera.get_spectrum(), dtype=float)

    def acquire_reference(self, hw_manager) -> np.ndarray:
        """Acquire a reference spectrum (blocking, called from main thread).

        Args:
            hw_manager: Hardware manager.

        Returns:
            Reference spectrum as numpy array.
        """
        return np.asarray(hw_manager.camera.get_spectrum(), dtype=float)
