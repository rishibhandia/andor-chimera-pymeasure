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
from typing import Optional

from typing import Optional

import numpy as np
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from andor_qt.ta.engine import TransientAbsorptionEngine
from andor_qt.ta.hdf5_writer import TADataWriter, auto_filename
from andor_qt.ta.scan_config import TAScanConfig
from andor_qt.widgets.ta.live_display import TALiveDisplayWidget
from andor_qt.widgets.ta.scan_config_widget import TAScanConfigWidget

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


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

        # --- Widgets ---
        self._config_widget = TAScanConfigWidget()
        self._live_display = TALiveDisplayWidget()

        # --- Layout ---
        splitter = QSplitter()
        splitter.addWidget(self._config_widget)
        splitter.addWidget(self._live_display)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        # --- Signal wiring ---
        self._config_widget.scan_requested.connect(self._on_scan_requested)

        # Engine → live display
        self._engine.signal_updated.connect(self._live_display.on_signal_updated)
        self._engine.map_updated.connect(self._live_display.on_map_updated)

        # Status feedback
        self._engine.scan_completed.connect(self._on_scan_completed)
        self._engine.aborted.connect(self._finalize_writer)
        self._engine.error.connect(self._on_engine_error)

    @Slot(object)
    def _on_scan_requested(self, config: TAScanConfig) -> None:
        """Start scan when config widget emits scan_requested."""
        log.info(f"TA scan requested: {config.sample_name}, "
                 f"{len(config.delay_list)} delays, {config.n_scans} scans")
        self._live_display.clear()
        camera_settings = self._config_widget.camera_settings

        # Create HDF5 writer if a save directory is configured
        writer: Optional[TADataWriter] = None
        if config.save_spectra_dir:
            try:
                get_wl = getattr(self._hw_manager, "get_wavelengths", None)
                wavelengths = np.asarray(get_wl()) if callable(get_wl) else np.array([])
                h5_path = auto_filename(
                    config.sample_name or "ta_scan", config.save_spectra_dir
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

        self._engine.start_scan(config, self._hw_manager, writer=writer,
                                 camera_settings=camera_settings)

    def _finalize_writer(self) -> None:
        if self._writer is not None:
            try:
                self._writer.finalize()
            except Exception as exc:
                log.warning(f"Error finalizing HDF5 writer: {exc}")
            self._writer = None

    @Slot()
    def _on_scan_completed(self) -> None:
        log.info("TA scan completed")
        self._finalize_writer()

    @Slot(str)
    def _on_engine_error(self, message: str) -> None:
        log.error(f"TA engine error: {message}")
        self._finalize_writer()

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
