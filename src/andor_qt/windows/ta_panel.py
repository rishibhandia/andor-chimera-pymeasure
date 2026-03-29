"""TAWindowPanel — composite TA panel for main window integration.

Composes:
- ``TAScanConfigWidget`` (left) — delay list builder + scan parameters
- ``TALiveDisplayWidget`` (right) — real-time ΔOD plots
- Optional ``StageControlWidget`` (if a delay axis is available)

Wires ``scan_requested`` → ``TransientAbsorptionEngine.start_scan``.
Wires engine data signals → live display slots.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

import numpy as np
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget

from andor_qt.ta.engine import TransientAbsorptionEngine
from andor_qt.ta.hdf5_writer import TADataWriter, auto_filename
from andor_qt.ta.monitor_engine import TAMonitorEngine
from andor_qt.ta.scan_config import TAScanConfig
from andor_qt.widgets.ta.live_display import TALiveDisplayWidget
from andor_qt.widgets.ta.monitor_widget import TAMonitorWidget
from andor_qt.widgets.ta.scan_config_widget import TAScanConfigWidget

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


def _make_daq_hardware(config: TAScanConfig) -> Tuple:
    """Create trigger generator and phase reader for the configured acquisition mode.

    Returns ``(trigger_gen, phase_reader)`` — either or both may be ``None``
    depending on the mode. Uses mock objects when ``ANDOR_MOCK=1``.
    """
    trigger_gen = None
    phase_reader = None

    if config.acquisition_mode == "chopper_2x2":
        if os.environ.get("ANDOR_MOCK"):
            from andor_qt.ta.nidaq_phase import MockNIDAQChopper2x2Reader
            from andor_qt.ta.nidaq_trigger import MockNIDAQChopper500Hz
            trigger_gen = MockNIDAQChopper500Hz()
            phase_reader = MockNIDAQChopper2x2Reader()
        else:
            from andor_qt.ta.nidaq_phase import NIDAQPhaseReader
            from andor_qt.ta.nidaq_trigger import NIDAQChopper500Hz
            trigger_gen = NIDAQChopper500Hz(
                device=config.nidaq_device,
                clock_source=config.nidaq_clock_source,
                sync_source=config.nidaq_chopper_sync_source,
                counter=config.nidaq_chopper_counter,
            )
            phase_reader = NIDAQPhaseReader(
                device=config.nidaq_device,
                di_channel=config.nidaq_di_channel,
                clock_source=config.nidaq_clock_source,
                clock_rate=config.nidaq_clock_rate,
            )
        if config.external_trigger:
            log.info("External camera trigger — NIDAQChopper500Hz not started")
            trigger_gen = None

    elif config.acquisition_mode == "shot_to_shot":
        log.info("shot_to_shot mode — camera triggered by PFI0 at 1 kHz")
        if os.environ.get("ANDOR_MOCK"):
            from andor_qt.ta.nidaq_phase import MockNIDAQPhaseReader
            phase_reader = MockNIDAQPhaseReader()
        else:
            from andor_qt.ta.nidaq_phase import NIDAQPhaseReader
            phase_reader = NIDAQPhaseReader(
                device=config.nidaq_device,
                di_channel=config.nidaq_di_channel,
                clock_source=config.nidaq_clock_source,
                clock_rate=config.nidaq_clock_rate,
            )

    return trigger_gen, phase_reader


class TAWindowPanel(QWidget):
    """TA measurement panel composed of config, engine, and live display.

    Signals:
        camera_busy: Emitted with ``True`` when the TA module starts using
            the camera (scan or monitor) and ``False`` when it finishes.
            The main window connects this to disable/re-enable the
            spectrometer acquire and queue controls.

    Args:
        hw_manager: Hardware manager instance.
        parent: Optional parent widget.
    """

    camera_busy = Signal(bool)

    def __init__(self, hw_manager, parent=None):
        super().__init__(parent)
        self._hw_manager = hw_manager

        # --- Engine ---
        self._engine = TransientAbsorptionEngine(self)
        self._writer: Optional[TADataWriter] = None
        self._current_config: Optional[TAScanConfig] = None
        self._dark_frame: Optional[np.ndarray] = None
        self._dark_acquiring: bool = False

        # --- Trigger test state ---
        self._trigger_test_running = False
        self._trigger_test_gen = None

        # --- Monitor engine ---
        self._monitor_engine = TAMonitorEngine(self)

        # --- Widgets ---
        self._config_widget = TAScanConfigWidget()
        self._config_widget.set_hardware_manager(hw_manager)
        self._monitor_widget = TAMonitorWidget(hw_manager)
        self._live_display = TALiveDisplayWidget()

        # --- Left pane: tabs for Scan / Monitor ---
        from PySide6.QtWidgets import QTabWidget
        self._left_tabs = QTabWidget()
        self._left_tabs.addTab(self._config_widget, "Scan")
        self._left_tabs.addTab(self._monitor_widget, "Monitor")

        # --- Status / trigger-test bar ---
        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("padding: 2px 6px; font-size: 12px;")
        self._trigger_test_btn = QPushButton("Start Trigger Test")
        self._trigger_test_btn.setFixedWidth(150)
        self._trigger_test_btn.setToolTip(
            "Start NIDAQChopper500Hz without a scan so you can probe CTR1OUT on an oscilloscope"
        )
        self._trigger_test_btn.clicked.connect(self._toggle_trigger_test)

        status_row = QHBoxLayout()
        status_row.addWidget(self._status_label, stretch=1)
        status_row.addWidget(self._trigger_test_btn, stretch=0)

        # --- Layout ---
        live_scroll = QScrollArea()
        live_scroll.setWidget(self._live_display)
        live_scroll.setWidgetResizable(True)
        live_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        splitter = QSplitter()
        splitter.addWidget(self._left_tabs)
        splitter.addWidget(live_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([700, 900])

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, stretch=1)
        layout.addLayout(status_row, stretch=0)

        # --- Signal wiring: Scan ---
        self._config_widget.scan_requested.connect(self._on_scan_requested)
        self._config_widget.abort_requested.connect(self._engine.abort)
        self._config_widget._external_trigger_check.toggled.connect(
            lambda checked: self._trigger_test_btn.setEnabled(not checked)
        )

        # Engine → live display
        self._engine.signal_updated.connect(self._live_display.on_signal_updated)
        self._engine.map_updated.connect(self._live_display.on_map_updated)
        self._engine.raw_pair_updated.connect(self._live_display.on_raw_pair_updated)

        # --- Signal wiring: Monitor ---
        self._monitor_widget.monitor_requested.connect(self._on_monitor_requested)
        self._monitor_widget.stop_requested.connect(self._on_monitor_stop)
        self._monitor_widget.static_acquire_requested.connect(self._on_static_acquire_requested)
        self._monitor_widget.dark_requested.connect(self._on_dark_requested)
        self._monitor_widget.dark_cleared.connect(self._on_dark_cleared)

        # Static ON/OFF state
        self._static_pump_avg = None
        self._static_ref_avg = None
        self._monitor_engine.cycle_completed.connect(self._on_monitor_cycle)
        self._monitor_engine.raw_pair_updated.connect(self._live_display.on_raw_pair_updated)
        self._monitor_engine.raw_pair_updated.connect(self._cache_monitor_raw)
        self._engine.raw_pair_updated.connect(self._cache_monitor_raw)
        self._monitor_engine.status_updated.connect(self._status_label.setText)
        self._monitor_engine.stopped.connect(self._on_monitor_stopped)
        self._monitor_engine.error.connect(self._on_monitor_error)
        self._monitor_engine.user_prompt.connect(self._on_user_prompt)
        self._monitor_engine.static_completed.connect(self._on_static_completed)
        self._monitor_engine.single_phase_completed.connect(self._on_single_phase_completed)

        # Engine → status / button state
        self._engine.scan_started.connect(self._on_scan_started)
        self._engine.point_started.connect(lambda _si, _d: self._live_display.reset_phase_stats())
        self._engine.point_completed.connect(self._on_point_completed)
        self._engine.scan_completed.connect(self._on_scan_completed)
        self._engine.aborted.connect(self._on_aborted)
        self._engine.error.connect(self._on_engine_error)
        self._engine.user_prompt.connect(self._on_engine_user_prompt)

        self._engine.status_updated.connect(self._status_label.setText)

    @Slot(object)
    def _on_scan_requested(self, config: TAScanConfig) -> None:
        """Start scan when config widget emits scan_requested."""
        log.info(f"TA scan requested: {config.sample_name}, "
                 f"{len(config.delay_list)} delays, {config.n_scans} scans")
        self._current_config = config
        self._config_widget.set_scan_running(True)
        self.camera_busy.emit(True)
        self._status_label.setText(
            f"Starting scan — {len(config.delay_list)} delays × {config.n_scans} scan(s)"
        )
        self._live_display.clear()
        camera_settings = self._config_widget.camera_settings

        # Create HDF5 writer if a save directory is configured
        writer: Optional[TADataWriter] = None
        if config.save_hdf5_dir:
            try:
                get_wl = getattr(self._hw_manager, "get_wavelengths", None)
                wavelengths = np.asarray(get_wl()) if callable(get_wl) else np.array([])
                h5_path = auto_filename(
                    config.sample_name or "ta_scan", config.save_hdf5_dir
                )
                writer = TADataWriter(
                    h5_path, wavelengths=wavelengths,
                    sample_name=config.sample_name, notes=config.notes,
                )
                writer.open()
                self._writer = writer
                log.info(f"HDF5 writer opened: {h5_path}")
            except Exception as exc:
                log.error(f"Failed to create HDF5 writer: {exc}")
                writer = None
                self._writer = None

        trigger_gen, phase_reader = _make_daq_hardware(config)

        self._engine.start_scan(config, self._hw_manager, writer=writer,
                                 camera_settings=camera_settings,
                                 trigger_gen=trigger_gen,
                                 phase_reader=phase_reader,
                                 dark=self._dark_frame)

    def _finalize_writer(self) -> None:
        if self._writer is not None:
            try:
                self._writer.finalize()
            except Exception as exc:
                log.warning(f"Error finalizing HDF5 writer: {exc}")
            self._writer = None

    def _end_scan(self) -> None:
        """Common cleanup after any scan termination."""
        self._finalize_writer()
        self._config_widget.set_scan_running(False)
        self._trigger_test_btn.setEnabled(True)
        self._current_config = None
        self.camera_busy.emit(False)

    @Slot(int)
    def _on_scan_started(self, scan_idx: int) -> None:
        # Stop trigger test if running before scan takes over the counter
        if self._trigger_test_running:
            self._toggle_trigger_test()
        n_scans = self._current_config.n_scans if self._current_config else "?"
        self._status_label.setText(f"Scan {scan_idx + 1}/{n_scans} — starting…")
        self._trigger_test_btn.setEnabled(False)

    @Slot(int, float)
    def _on_point_completed(self, scan_idx: int, delay_ps: float) -> None:
        pass  # status_updated signal provides richer detail; keep slot for future use

    @Slot()
    def _on_scan_completed(self) -> None:
        log.info("TA scan completed")
        self._status_label.setText("Scan complete")
        self._end_scan()

    @Slot()
    def _on_aborted(self) -> None:
        log.info("TA scan aborted")
        self._status_label.setText("Scan aborted")
        self._end_scan()

    @Slot(str)
    def _on_engine_error(self, message: str) -> None:
        log.error(f"TA engine error: {message}")
        self._status_label.setText(f"Error: {message}")
        self._end_scan()

    @Slot(str)
    def _on_engine_user_prompt(self, msg: str) -> None:
        """Handle user prompt from engine (e.g. static_onoff pump block)."""
        from PySide6.QtWidgets import QMessageBox
        result = QMessageBox.information(
            self, "Action Required", msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Ok:
            self._engine.user_confirmed()
        else:
            self._engine.abort()

    def _toggle_trigger_test(self) -> None:
        """Start or stop NIDAQChopper500Hz without a scan for oscilloscope testing."""
        if self._trigger_test_running:
            # Stop
            if self._trigger_test_gen is not None:
                try:
                    self._trigger_test_gen.stop()
                except Exception as exc:
                    log.warning(f"Trigger test stop error: {exc}")
                self._trigger_test_gen = None
            self._trigger_test_running = False
            self._trigger_test_btn.setText("Start Trigger Test")
            self._status_label.setText("Trigger test stopped")
            log.info("Trigger test stopped")
        else:
            # Start
            config = self._config_widget._build_config()
            if os.environ.get("ANDOR_MOCK"):
                from andor_qt.ta.nidaq_trigger import MockNIDAQChopper500Hz
                gen = MockNIDAQChopper500Hz()
            else:
                from andor_qt.ta.nidaq_trigger import NIDAQChopper500Hz
                gen = NIDAQChopper500Hz(
                    device=config.nidaq_device,
                    clock_source=config.nidaq_clock_source,
                    sync_source=config.nidaq_chopper_sync_source,
                    counter=config.nidaq_chopper_counter,
                )
            try:
                gen.start()
                self._trigger_test_gen = gen
                self._trigger_test_running = True
                self._trigger_test_btn.setText("Stop Trigger Test")
                self._status_label.setText(
                    f"Trigger test RUNNING — probe CTR1OUT (PFI13) on oscilloscope"
                )
                log.info("Trigger test started")
            except Exception as exc:
                log.error(f"Trigger test start failed: {exc}")
                self._status_label.setText(f"Trigger test failed: {exc}")

    # -- Monitor mode ------------------------------------------------------

    def _pre_set_wavelengths(self, camera_settings: dict) -> None:
        """Pre-set wavelengths on live display so raw spectra save with nm axis."""
        hbin = camera_settings.get("hbin", 1)
        if isinstance(hbin, str):
            hbin = int(hbin.replace("x", ""))
        get_wl = getattr(self._hw_manager, "get_wavelengths", None)
        if callable(get_wl):
            self._live_display._wavelengths = np.asarray(get_wl(hbin=hbin))

    @Slot(object)
    def _on_monitor_requested(self, config: TAScanConfig) -> None:
        """Start monitor mode."""
        if self._monitor_engine.is_running:
            return

        # Stop trigger test if running
        if self._trigger_test_running:
            self._toggle_trigger_test()

        camera_settings = self._monitor_widget.camera_settings
        trigger_gen, phase_reader = _make_daq_hardware(config)

        self._live_display.set_monitor_mode(True)
        self._live_display.clear()
        self._monitor_widget.set_monitor_running(True)
        self._config_widget.set_scan_running(True)  # lock out scan
        self.camera_busy.emit(True)
        self._status_label.setText("Monitor starting...")
        self._pre_set_wavelengths(camera_settings)

        self._monitor_engine.start_monitor(
            config, self._hw_manager,
            camera_settings=camera_settings,
            trigger_gen=trigger_gen,
            phase_reader=phase_reader,
            dark=self._dark_frame,
        )

    def _on_monitor_cycle(self, wavelengths, delta, avg_delta) -> None:
        """Handle monitor cycle completion — update live display."""
        # Dark frame acquisition: store raw average and stop after first cycle
        if getattr(self, "_dark_acquiring", False):
            self._dark_acquiring = False
            # Use the pump-ON average as the dark frame (shutter should be closed)
            if hasattr(self._monitor_widget, "_last_pump"):
                self._dark_frame = np.asarray(self._monitor_widget._last_pump).copy()
                from datetime import datetime
                ts = datetime.now().strftime("%H:%M:%S")
                n = getattr(self._monitor_widget, "_last_n_on", 0)
                self._monitor_widget.set_dark_status(f"Dark: {n} frames, {ts}")
                self._status_label.setText(f"Dark frame acquired ({n} frames)")
                log.info(f"Dark frame stored: {len(self._dark_frame)} pixels, {n} frames")
            self._monitor_engine.stop()
            return

        # Normal monitor cycle
        axis = None
        if self._hw_manager.motion_manager:
            axis = self._hw_manager.motion_manager.get_axis("delay")
        delay_ps = getattr(axis, "position_ps", 0.0) if axis else 0.0
        self._live_display.on_signal_updated(delay_ps, wavelengths, delta)
        self._monitor_widget.update_position()

    def _cache_monitor_raw(self, pumped, ref, n_matched, n_discarded, n_frames):
        """Cache the last raw pair for the monitor save buttons."""
        from datetime import datetime
        self._monitor_widget._last_pump = np.asarray(pumped)
        self._monitor_widget._last_ref = np.asarray(ref)
        self._monitor_widget._last_n_on = n_matched
        self._monitor_widget._last_n_off = n_matched
        self._monitor_widget._last_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Cache wavelengths that match the data length
        self._monitor_widget._last_wavelengths = (
            self._live_display._wavelengths
            if len(self._live_display._wavelengths) == len(pumped)
            else None
        )

    @Slot()
    def _on_monitor_stop(self) -> None:
        """Stop monitor mode."""
        self._monitor_engine.stop()

    @Slot()
    def _on_monitor_stopped(self) -> None:
        """Handle monitor engine stopped."""
        self._monitor_widget.set_monitor_running(False)
        self._config_widget.set_scan_running(False)
        self._live_display.set_monitor_mode(False)
        self.camera_busy.emit(False)
        self._status_label.setText("Monitor stopped")

    @Slot(str)
    def _on_monitor_error(self, msg: str) -> None:
        """Handle monitor engine error."""
        self._monitor_widget.set_monitor_running(False)
        self._config_widget.set_scan_running(False)
        self._live_display.set_monitor_mode(False)
        self.camera_busy.emit(False)
        self._status_label.setText(f"Monitor error: {msg}")
        log.error(f"Monitor error: {msg}")

    # -- Dark frame -----------------------------------------------------------

    def _on_dark_requested(self, config: TAScanConfig) -> None:
        """Acquire dark frame using the monitor engine in single-cycle mode."""
        if self._monitor_engine.is_running:
            return

        camera_settings = self._monitor_widget.camera_settings
        trigger_gen, phase_reader = _make_daq_hardware(config)

        self._monitor_widget.set_monitor_running(True)
        self._config_widget.set_scan_running(True)
        self.camera_busy.emit(True)
        self._status_label.setText("Acquiring dark frame...")
        self._pre_set_wavelengths(camera_settings)

        # Use single cycle — the cycle_completed callback stores the result
        self._dark_acquiring = True
        self._monitor_engine.start_monitor(
            config, self._hw_manager,
            camera_settings=camera_settings,
            trigger_gen=trigger_gen,
            phase_reader=phase_reader,
        )

    def _on_dark_cleared(self) -> None:
        """Clear the stored dark frame."""
        self._dark_frame = None
        self._status_label.setText("Dark frame cleared")
        log.info("Dark frame cleared")

    @Slot(str)
    def _on_user_prompt(self, msg: str) -> None:
        """Show a dialog asking user to do something (e.g. block pump)."""
        from PySide6.QtWidgets import QMessageBox
        result = QMessageBox.information(
            self, "Action Required", msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Ok:
            self._monitor_engine.user_confirmed()
        else:
            self._monitor_engine.stop()

    @Slot(object, object, object, object)
    def _on_static_completed(self, wavelengths, pump_avg, ref_avg, delta_od) -> None:
        """Handle static ON/OFF completion — display ΔOD in signal plot."""
        self._live_display.on_signal_updated(0.0, wavelengths, delta_od)
        self._live_display.on_raw_pair_updated(
            pump_avg, ref_avg, 1, 0, 2
        )

    @Slot(str, object)
    def _on_static_acquire_requested(self, phase: str, config: TAScanConfig) -> None:
        """Handle static single-phase acquisition (pump ON or pump OFF)."""
        if self._monitor_engine.is_running:
            return

        camera_settings = self._monitor_widget.camera_settings

        self._monitor_widget.set_monitor_running(True)
        self._config_widget.set_scan_running(True)
        self.camera_busy.emit(True)
        self._status_label.setText(f"Static: acquiring {phase}...")
        self._pre_set_wavelengths(camera_settings)

        self._monitor_engine.start_monitor(
            config, self._hw_manager,
            camera_settings=camera_settings,
            static_phase=phase,
        )

    @Slot(str, object, object)
    def _on_single_phase_completed(self, phase: str, wavelengths, avg_spectrum) -> None:
        """Store result of a static single-phase acquisition."""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")

        if phase == "pump":
            self._static_pump_avg = avg_spectrum
            self._static_pump_time = ts
            self._static_wavelengths = wavelengths
            log.info(f"Static pump ON collected at {ts}: mean={avg_spectrum.mean():.1f}")
        else:
            self._static_ref_avg = avg_spectrum
            self._static_ref_time = ts
            self._static_wavelengths = wavelengths
            log.info(f"Static pump OFF collected at {ts}: mean={avg_spectrum.mean():.1f}")

        # Update status with timestamps
        pump_done = self._static_pump_avg is not None
        ref_done = self._static_ref_avg is not None
        self._monitor_widget.update_static_status(
            pump_done, ref_done,
            pump_time=getattr(self, "_static_pump_time", ""),
            ref_time=getattr(self, "_static_ref_time", ""),
        )

        # Show raw spectra — use cached pump/ref so both curves display correctly
        pump = self._static_pump_avg if self._static_pump_avg is not None else avg_spectrum
        ref = self._static_ref_avg if self._static_ref_avg is not None else avg_spectrum
        self._live_display.on_raw_pair_updated(pump, ref, 1, 0, 2)

        # Update save cache so "Save Pump ON"/"Save Pump OFF" buttons use correct data
        from datetime import datetime
        self._monitor_widget._last_pump = np.asarray(pump).copy()
        self._monitor_widget._last_ref = np.asarray(ref).copy()
        self._monitor_widget._last_n_on = 1
        self._monitor_widget._last_n_off = 1
        self._monitor_widget._last_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._monitor_widget._last_wavelengths = (
            np.asarray(wavelengths) if wavelengths is not None else None
        )

        # If both phases collected, compute ΔOD
        if pump_done and ref_done:
            ref_safe = np.where(self._static_ref_avg == 0, 1.0, self._static_ref_avg)
            delta_od = -np.log10(self._static_pump_avg / ref_safe)
            self._live_display.on_signal_updated(0.0, self._static_wavelengths, delta_od)
            self._status_label.setText(
                f"Static ON/OFF complete  |  "
                f"\u0394OD range: [{delta_od.min():.6f}, {delta_od.max():.6f}]"
            )
            log.info(f"Static ΔOD computed: [{delta_od.min():.6f}, {delta_od.max():.6f}]")

    # -- public API --------------------------------------------------------

    @property
    def engine(self) -> TransientAbsorptionEngine:
        return self._engine

    @property
    def config_widget(self) -> TAScanConfigWidget:
        return self._config_widget

    @property
    def monitor_widget(self) -> TAMonitorWidget:
        return self._monitor_widget

    @property
    def live_display(self) -> TALiveDisplayWidget:
        return self._live_display
