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
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget

from andor_qt.ta.engine import TransientAbsorptionEngine
from andor_qt.ta.hdf5_writer import TADataWriter, auto_filename
from andor_qt.ta.scan_config import TAScanConfig
from andor_qt.widgets.ta.live_display import TALiveDisplayWidget
from andor_qt.widgets.ta.scan_config_widget import TAScanConfigWidget

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


def _make_chopper_2x2_hardware(config: TAScanConfig) -> Tuple:
    """Create trigger generator and phase reader for chopper_2x2 mode.

    Returns mock objects when ``ANDOR_MOCK=1``, real NI DAQ objects otherwise.
    """
    if os.environ.get("ANDOR_MOCK"):
        from andor_qt.ta.nidaq_phase import MockNIDAQChopper2x2Reader
        from andor_qt.ta.nidaq_trigger import MockNIDAQChopper500Hz
        return MockNIDAQChopper500Hz(), MockNIDAQChopper2x2Reader()

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
    return trigger_gen, phase_reader


class TAWindowPanel(QWidget):
    """TA measurement panel composed of config, engine, and live display.

    Args:
        hw_manager: Hardware manager instance.
        parent: Optional parent widget.
    """

    def __init__(self, hw_manager, parent=None):
        super().__init__(parent)
        self._hw_manager = hw_manager

        # --- Engine ---
        self._engine = TransientAbsorptionEngine(self)
        self._writer: Optional[TADataWriter] = None
        self._current_config: Optional[TAScanConfig] = None

        # --- Trigger test state ---
        self._trigger_test_running = False
        self._trigger_test_gen = None

        # --- Widgets ---
        self._config_widget = TAScanConfigWidget()
        self._config_widget.set_hardware_manager(hw_manager)
        self._live_display = TALiveDisplayWidget()

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
        splitter.addWidget(self._config_widget)
        splitter.addWidget(live_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([700, 900])

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, stretch=1)
        layout.addLayout(status_row, stretch=0)

        # --- Signal wiring ---
        self._config_widget.scan_requested.connect(self._on_scan_requested)
        self._config_widget.abort_requested.connect(self._engine.abort)
        self._config_widget._external_trigger_check.toggled.connect(
            lambda checked: self._trigger_test_btn.setEnabled(not checked)
        )

        # Engine → live display
        self._engine.signal_updated.connect(self._live_display.on_signal_updated)
        self._engine.map_updated.connect(self._live_display.on_map_updated)
        self._engine.raw_pair_updated.connect(self._live_display.on_raw_pair_updated)

        # Engine → status / button state
        self._engine.scan_started.connect(self._on_scan_started)
        self._engine.point_started.connect(lambda _si, _d: self._live_display.reset_phase_stats())
        self._engine.point_completed.connect(self._on_point_completed)
        self._engine.scan_completed.connect(self._on_scan_completed)
        self._engine.aborted.connect(self._on_aborted)
        self._engine.error.connect(self._on_engine_error)

        self._engine.status_updated.connect(self._status_label.setText)

    @Slot(object)
    def _on_scan_requested(self, config: TAScanConfig) -> None:
        """Start scan when config widget emits scan_requested."""
        log.info(f"TA scan requested: {config.sample_name}, "
                 f"{len(config.delay_list)} delays, {config.n_scans} scans")
        self._current_config = config
        self._config_widget.set_scan_running(True)
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

        trigger_gen = None
        phase_reader = None
        if config.acquisition_mode == "chopper_2x2":
            _tgen, phase_reader = _make_chopper_2x2_hardware(config)
            if config.external_trigger:
                log.info("External camera trigger selected — NIDAQChopper500Hz not started")
            else:
                trigger_gen = _tgen

        self._engine.start_scan(config, self._hw_manager, writer=writer,
                                 camera_settings=camera_settings,
                                 trigger_gen=trigger_gen,
                                 phase_reader=phase_reader)

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

    # -- public API --------------------------------------------------------

    @property
    def engine(self) -> TransientAbsorptionEngine:
        return self._engine

    @property
    def config_widget(self) -> TAScanConfigWidget:
        return self._config_widget

    @property
    def live_display(self) -> TALiveDisplayWidget:
        return self._live_display
