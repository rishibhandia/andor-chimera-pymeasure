"""Main window for the Andor Spectrometer Qt GUI.

This is the primary application window that assembles all widgets
and coordinates their interactions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from andor_qt.core.hardware_manager import HardwareManager
from andor_qt.core.signals import get_hardware_signals
from andor_qt.widgets.display import ImagePlotWidget, ResultsTableWidget, SpectrumPlotWidget, TraceListWidget
from andor_qt.widgets.hardware import (
    DataSettingsWidget,
    SpectrographControlWidget,
    TemperatureControlWidget,
)
from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog
from andor_qt.widgets.inputs import DynamicInputsWidget, QueueControlWidget
from andor_qt.widgets.inputs.acquire_control import AcquireControlWidget
from andor_qt.widgets.menu_bar import AndorMenuBar

log = logging.getLogger(__name__)


class AcquisitionSignals(QObject):
    """Signals for thread-safe acquisition updates."""

    progress = Signal(int, float)  # (exp_id, progress)
    spectrum_ready = Signal(object, object)  # (wavelengths, intensities)
    image_ready = Signal(object, object)  # (image, wavelengths)
    completed = Signal(int)  # exp_id
    failed = Signal(int, str)  # (exp_id, error_message)
    status = Signal(str)  # status message
    shutdown_progress = Signal(str)  # shutdown progress message
    shutdown_complete = Signal()  # shutdown complete


class AndorSpectrometerWindow(QMainWindow):
    """Main window for Andor spectrometer control.

    Layout:
        ┌─────────────────────────────────────────────────────────────┐
        │  Menu Bar                                                   │
        ├───────────────────────┬─────────────────────────────────────┤
        │   Control Panel       │            Display Panel            │
        │   (left side)         │            (right side)             │
        │  ┌─────────────────┐  │  ┌───────────────────────────────┐  │
        │  │TemperatureCtrl  │  │  │ QStackedWidget                │  │
        │  │SpectrographCtrl │  │  │  - SpectrumPlotWidget (1D)    │  │
        │  │ DynamicInputs   │  │  │  - ImagePlotWidget (2D)       │  │
        │  │ QueueControl    │  │  └───────────────────────────────┘  │
        │  │ DataSettings    │  │  ┌───────────────────────────────┐  │
        │  └─────────────────┘  │  │ ResultsTableWidget            │  │
        │                       │  └───────────────────────────────┘  │
        ├───────────────────────┴─────────────────────────────────────┤
        │  Status Bar: Ready | Temp: -60.1C (STABILIZED) | WL: 500nm │
        └─────────────────────────────────────────────────────────────┘
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setWindowTitle("Andor Spectrometer Control")
        self.setMinimumSize(1200, 800)

        self._hw_manager = HardwareManager.instance()
        self._signals = get_hardware_signals()
        self._acq_signals = AcquisitionSignals()

        self._current_exp_id: Optional[int] = None
        self._last_calibration: Optional[np.ndarray] = None
        self._last_data: Optional[np.ndarray] = None

        self._setup_ui()
        self._setup_status_bar()
        self._connect_signals()

        # Start hardware initialization
        self._init_hardware()

    def _setup_ui(self) -> None:
        """Set up the main window UI."""
        # Menu bar
        self._menu_bar = AndorMenuBar(self)
        self.setMenuBar(self._menu_bar)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # Create main splitter
        self._splitter = QSplitter(Qt.Horizontal)

        # Left panel - Controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)

        # Hardware control widgets
        self._temp_control = TemperatureControlWidget(self._hw_manager)
        left_layout.addWidget(self._temp_control)

        self._spec_control = SpectrographControlWidget(self._hw_manager)
        left_layout.addWidget(self._spec_control)

        # Acquisition parameters
        self._inputs_widget = DynamicInputsWidget()
        left_layout.addWidget(self._inputs_widget)

        # Direct acquire controls
        self._acquire_control = AcquireControlWidget()
        left_layout.addWidget(self._acquire_control)

        # Queue control
        self._queue_control = QueueControlWidget()
        left_layout.addWidget(self._queue_control)

        # Data settings
        self._data_settings = DataSettingsWidget()
        left_layout.addWidget(self._data_settings)

        left_layout.addStretch()

        # Right panel - Display
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        # Stacked widget for 1D/2D plots
        self._plot_stack = QStackedWidget()

        self._spectrum_plot = SpectrumPlotWidget()
        self._plot_stack.addWidget(self._spectrum_plot)

        self._image_plot = ImagePlotWidget()
        self._plot_stack.addWidget(self._image_plot)

        right_layout.addWidget(self._plot_stack, stretch=2)

        # Trace list for overlay management
        self._trace_list = TraceListWidget()
        right_layout.addWidget(self._trace_list, stretch=0)

        # Results table
        self._results_table = ResultsTableWidget()
        right_layout.addWidget(self._results_table, stretch=1)

        # Add panels to splitter
        self._splitter.addWidget(left_panel)
        self._splitter.addWidget(right_panel)
        self._splitter.setStretchFactor(0, 1)  # Left panel: smaller
        self._splitter.setStretchFactor(1, 3)  # Right panel: larger
        self._splitter.setSizes([350, 850])

        main_layout.addWidget(self._splitter)

    def _setup_status_bar(self) -> None:
        """Set up the status bar."""
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        # Status label
        self._status_label = QLabel("Initializing...")
        self._status_bar.addWidget(self._status_label)

        # Temperature label
        self._temp_status_label = QLabel("Temp: -- °C")
        self._status_bar.addPermanentWidget(self._temp_status_label)

        # Wavelength label
        self._wl_status_label = QLabel("WL: -- nm")
        self._status_bar.addPermanentWidget(self._wl_status_label)

    def _connect_signals(self) -> None:
        """Connect signals between components."""
        # Menu bar signals
        self._menu_bar.exit_requested.connect(self.close)
        self._menu_bar.acquire_requested.connect(self._on_queue_clicked)
        self._menu_bar.abort_requested.connect(self._on_abort_clicked)

        # Acquire control signals
        self._acquire_control.acquire_requested.connect(self._on_queue_clicked)
        self._acquire_control.abort_requested.connect(self._on_abort_clicked)

        # Hardware signals
        self._signals.camera_initialized.connect(self._on_camera_initialized)
        self._signals.spectrograph_initialized.connect(self._on_spectrograph_initialized)
        self._signals.temperature_changed.connect(self._on_temperature_changed)
        self._signals.wavelength_changed.connect(self._on_wavelength_changed)
        self._signals.error_occurred.connect(self._on_error)

        # Input signals
        self._inputs_widget.read_mode_changed.connect(self._on_read_mode_changed)

        # Queue control signals
        self._queue_control.queue_clicked.connect(self._on_queue_clicked)
        self._queue_control.abort_clicked.connect(self._on_abort_clicked)

        # Trace overlay signals
        self._spectrum_plot.trace_added.connect(self._trace_list.add_trace)
        self._trace_list.visibility_toggled.connect(self._spectrum_plot.set_trace_visible)
        self._trace_list.trace_remove_requested.connect(self._spectrum_plot.remove_trace)
        self._trace_list.clear_all_requested.connect(self._spectrum_plot.clear_traces)
        self._spectrum_plot.trace_removed.connect(self._trace_list.remove_trace)
        self._spectrum_plot.traces_cleared.connect(self._trace_list.clear)

        # Acquisition signals (thread-safe)
        self._acq_signals.progress.connect(self._on_acq_progress)
        self._acq_signals.spectrum_ready.connect(self._on_spectrum_ready)
        self._acq_signals.image_ready.connect(self._on_image_ready)
        self._acq_signals.completed.connect(self._on_acq_completed)
        self._acq_signals.failed.connect(self._on_acq_failed)
        self._acq_signals.status.connect(self._on_acq_status)
        self._acq_signals.shutdown_progress.connect(self._on_shutdown_progress)
        self._acq_signals.shutdown_complete.connect(self._on_shutdown_complete)

    def _init_hardware(self) -> None:
        """Initialize hardware in background."""
        self._set_controls_enabled(False)

        self._hw_manager.initialize(
            on_complete=self._on_hardware_ready,
            on_error=self._on_hardware_error,
        )

    @Slot()
    def _on_hardware_ready(self) -> None:
        """Handle hardware initialization complete."""
        log.info("Hardware ready")
        # Emit signal to update UI from main thread
        self._signals.status_message.emit("Ready")

    @Slot(dict)
    def _on_camera_initialized(self, info: dict) -> None:
        """Handle camera initialization."""
        log.info(f"Camera initialized: {info}")

        # Start temperature polling from main thread (QTimer requirement)
        self._hw_manager.start_temperature_polling(interval_ms=2000)

        # Enable controls
        self._status_label.setText("Ready")
        self._set_controls_enabled(True)

        # Inject hardware into procedures
        from andor_qt.procedures import ImageProcedure, SpectrumProcedure

        self._hw_manager.inject_into_procedure(SpectrumProcedure)
        self._hw_manager.inject_into_procedure(ImageProcedure)

    @Slot(str)
    def _on_hardware_error(self, error_msg: str) -> None:
        """Handle hardware initialization error."""
        log.error(f"Hardware error: {error_msg}")
        self._status_label.setText(f"Error: {error_msg}")

        QMessageBox.critical(
            self,
            "Hardware Error",
            f"Failed to initialize hardware:\n\n{error_msg}",
        )

    @Slot(dict)
    def _on_spectrograph_initialized(self, info: dict) -> None:
        """Handle spectrograph initialization."""
        log.info(f"Spectrograph initialized: {info}")

    @Slot(float, str)
    def _on_temperature_changed(self, temperature: float, status: str) -> None:
        """Update temperature status display."""
        self._temp_status_label.setText(f"Temp: {temperature:.1f}°C ({status})")

    @Slot(float)
    def _on_wavelength_changed(self, wavelength: float) -> None:
        """Update wavelength status display."""
        self._wl_status_label.setText(f"WL: {wavelength:.1f} nm")

    @Slot(str, str)
    def _on_error(self, source: str, message: str) -> None:
        """Handle error from hardware."""
        log.error(f"Error from {source}: {message}")
        self._status_label.setText(f"Error: {message}")

    @Slot(str)
    def _on_read_mode_changed(self, mode: str) -> None:
        """Handle read mode change."""
        if mode == "image":
            self._plot_stack.setCurrentWidget(self._image_plot)
        else:
            self._plot_stack.setCurrentWidget(self._spectrum_plot)

    # Acquisition signal handlers (called on main thread)
    @Slot(int, float)
    def _on_acq_progress(self, exp_id: int, progress: float) -> None:
        """Handle acquisition progress update."""
        self._queue_control.set_progress(progress)
        self._results_table.update_status(exp_id, "running", progress)

    @Slot(object, object)
    def _on_spectrum_ready(self, wavelengths, intensities) -> None:
        """Handle spectrum data ready — add as new overlay trace."""
        self._last_calibration = wavelengths
        self._last_data = intensities

        # Build descriptive label
        params = self._inputs_widget.get_parameters()
        exp_id = self._current_exp_id or 0
        exp_t = params.get("exposure_time", 0)
        label = f"#{exp_id} exp={exp_t:.2f}s"

        self._spectrum_plot.add_trace(wavelengths, intensities, label=label)

    @Slot(object, object)
    def _on_image_ready(self, image, wavelengths) -> None:
        """Handle image data ready."""
        self._last_calibration = wavelengths
        self._last_data = image
        self._image_plot.set_data(image, wavelengths)

    @Slot(int)
    def _on_acq_completed(self, exp_id: int) -> None:
        """Handle acquisition completed."""
        self._results_table.update_status(exp_id, "completed", 100)
        self._queue_control.set_running(False)
        self._status_label.setText("Ready")

        # Auto-save if enabled
        if self._data_settings.auto_save and self._last_data is not None:
            params = self._inputs_widget.get_parameters()
            self._save_data(self._last_data, self._last_calibration, params)

    @Slot(int, str)
    def _on_acq_failed(self, exp_id: int, error_msg: str) -> None:
        """Handle acquisition failed."""
        self._results_table.update_status(exp_id, "failed", error_message=error_msg)
        self._queue_control.set_running(False)
        self._status_label.setText(f"Error: {error_msg}")

    @Slot(str)
    def _on_acq_status(self, message: str) -> None:
        """Handle status message from acquisition."""
        self._status_label.setText(message)

    @Slot()
    def _on_queue_clicked(self) -> None:
        """Handle Queue button click - run acquisition."""
        if not self._hw_manager.is_initialized:
            QMessageBox.warning(self, "Not Ready", "Hardware is not initialized.")
            return

        # Get current settings
        params = self._inputs_widget.get_parameters()
        params["center_wavelength"] = self._hw_manager.spectrograph.wavelength
        params["grating"] = self._hw_manager.spectrograph.grating

        # Add to results table
        procedure_type = "FVB" if params["read_mode"] == "fvb" else "Image"
        exp_id = self._results_table.add_experiment(procedure_type, params)
        self._current_exp_id = exp_id

        # Run acquisition in background
        self._queue_control.set_running(True)
        self._results_table.update_status(exp_id, "running")
        self._status_label.setText("Acquiring...")

        import threading

        def _run_acquisition():
            try:
                # Emit status
                self._acq_signals.status.emit("Getting calibration...")

                # Get calibration based on source setting
                cal_source = self._data_settings.calibration_source
                if cal_source == "file" and self._data_settings.calibration_file:
                    calibration = self._load_calibration_file(
                        self._data_settings.calibration_file
                    )
                else:
                    calibration = self._hw_manager.get_calibration()

                # Set exposure
                self._hw_manager.camera.set_exposure(params["exposure_time"])

                self._acq_signals.status.emit("Acquiring...")

                # Acquire based on mode
                if params["read_mode"] == "fvb":
                    # FVB acquisition
                    if params.get("num_accumulations", 1) > 1:
                        eff_xpixels = self._hw_manager.camera.xpixels // params["hbin"]
                        accumulated = np.zeros(eff_xpixels, dtype=np.float64)
                        for i in range(params["num_accumulations"]):
                            data = self._hw_manager.camera.acquire_fvb()
                            accumulated += data
                            progress = 100 * (i + 1) / params["num_accumulations"]
                            self._acq_signals.progress.emit(exp_id, progress)
                        data = accumulated / params["num_accumulations"]
                    else:
                        data = self._hw_manager.camera.acquire_fvb()

                    # Emit spectrum ready (on main thread)
                    self._acq_signals.spectrum_ready.emit(calibration, data)
                else:
                    # Image acquisition
                    data = self._hw_manager.camera.acquire_image(
                        hbin=params["hbin"],
                        vbin=params["vbin"],
                    )

                    # Emit image ready (on main thread)
                    self._acq_signals.image_ready.emit(data, calibration)

                # Emit completed
                self._acq_signals.completed.emit(exp_id)

            except Exception as e:
                log.error(f"Acquisition failed: {e}")
                self._acq_signals.failed.emit(exp_id, str(e))

        thread = threading.Thread(target=_run_acquisition, daemon=True)
        thread.start()

    @Slot()
    def _on_abort_clicked(self) -> None:
        """Handle Abort button click."""
        if self._hw_manager.camera:
            self._hw_manager.camera.abort_acquisition()

        self._queue_control.set_running(False)
        self._status_label.setText("Aborted")

        if self._current_exp_id:
            self._results_table.update_status(self._current_exp_id, "aborted")

    def _load_calibration_file(self, filepath: str) -> Optional[np.ndarray]:
        """Load wavelength calibration from a file.

        File format: (pixel, wavelength) pairs, one per line.
        Supports CSV (.csv), text (.txt, .cal) with comma/space separators,
        and NPZ files with a 'wavelengths' array.

        For text files, fits a polynomial (degree 2) to the calibration points
        and generates wavelengths for all pixels.

        Args:
            filepath: Path to the calibration file.

        Returns:
            Numpy array of wavelengths, or None if loading fails.
        """
        try:
            path = Path(filepath)

            if path.suffix.lower() == ".npz":
                # NPZ format - look for 'wavelengths' key (full array)
                data = np.load(filepath)
                if "wavelengths" in data:
                    return data["wavelengths"]
                elif "calibration" in data:
                    return data["calibration"]
                else:
                    log.error(f"NPZ file missing 'wavelengths' key: {filepath}")
                    return None

            elif path.suffix.lower() in (".csv", ".txt", ".cal"):
                # Text format - (pixel, wavelength) pairs
                # Try comma delimiter first, then whitespace
                try:
                    data = np.loadtxt(filepath, delimiter=",", comments="#")
                except ValueError:
                    data = np.loadtxt(filepath, comments="#")

                if data.ndim != 2 or data.shape[1] < 2:
                    log.error(
                        f"Calibration file must have pixel,wavelength columns: {filepath}"
                    )
                    return None

                pixels = data[:, 0]
                wavelengths = data[:, 1]

                # Fit polynomial (degree 2) to calibration points
                coeffs = np.polyfit(pixels, wavelengths, deg=2)

                # Generate wavelengths for all pixels
                num_pixels = 1024  # Default
                if self._hw_manager.camera:
                    num_pixels = self._hw_manager.camera.xpixels
                all_pixels = np.arange(num_pixels)
                calibration = np.polyval(coeffs, all_pixels)

                log.info(
                    f"Loaded calibration from {filepath}: "
                    f"{len(data)} points, fitted polynomial"
                )
                return calibration

            log.error(f"Unsupported calibration file format: {filepath}")
            return None

        except Exception as e:
            log.error(f"Failed to load calibration file: {e}")
            return None

    def _save_data(
        self,
        data: np.ndarray,
        calibration: Optional[np.ndarray],
        params: dict,
    ) -> None:
        """Save acquisition data to file.

        Args:
            data: Acquired data (1D or 2D).
            calibration: Wavelength calibration array.
            params: Acquisition parameters.
        """
        try:
            filepath = self._data_settings.get_next_filepath(".csv")

            if data.ndim == 1:
                # 1D spectrum
                import csv

                with open(filepath, "w", newline="") as f:
                    writer = csv.writer(f)

                    # Write header with metadata
                    writer.writerow(["# Andor Spectrum Data"])
                    for key, value in params.items():
                        writer.writerow([f"# {key}", value])
                    writer.writerow(["# sample_id", self._data_settings.sample_id])
                    writer.writerow(["# operator", self._data_settings.operator])
                    writer.writerow([])
                    writer.writerow(["Wavelength (nm)", "Intensity"])

                    # Write data
                    if calibration is not None:
                        for wl, intensity in zip(calibration, data):
                            writer.writerow([f"{wl:.3f}", f"{intensity:.1f}"])
                    else:
                        for i, intensity in enumerate(data):
                            writer.writerow([i, f"{intensity:.1f}"])

            else:
                # 2D image - save as NPZ
                filepath = filepath.with_suffix(".npz")
                np.savez(
                    filepath,
                    data=data,
                    wavelengths=calibration,
                    **params,
                )

            log.info(f"Data saved to {filepath}")
            self._status_label.setText(f"Saved: {filepath.name}")

        except Exception as e:
            log.error(f"Failed to save data: {e}")

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable control widgets."""
        self._temp_control.set_enabled(enabled)
        self._spec_control.set_enabled(enabled)
        self._inputs_widget.setEnabled(enabled)
        self._queue_control.setEnabled(enabled)

    def closeEvent(self, event) -> None:
        """Handle window close - shutdown hardware safely."""
        # Check if hardware is initialized and needs warmup
        if not self._hw_manager.is_initialized:
            event.accept()
            return

        # Check current temperature
        current_temp = None
        if self._hw_manager.camera:
            try:
                current_temp = self._hw_manager.camera.temperature
            except Exception:
                pass

        # Build confirmation message
        if current_temp is not None and current_temp < -20:
            msg = (
                f"Are you sure you want to exit?\n\n"
                f"Camera temperature: {current_temp:.1f}°C\n"
                f"The camera will warm up to -20°C before shutdown.\n"
                f"This may take a few minutes."
            )
        else:
            msg = "Are you sure you want to exit?"

        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            event.ignore()
            return

        # Prevent the close and start shutdown with visual progress
        event.ignore()
        self._start_shutdown_with_dialog()

    def _start_shutdown(self) -> None:
        """Start the shutdown process.

        Note: This blocks the UI during shutdown/warmup. This is intentional
        to avoid Qt crashes from cross-thread signal/timer interactions.
        """
        import threading

        self._set_controls_enabled(False)
        self._status_label.setText("Shutting down (please wait)...")

        # Force UI update before blocking
        QApplication.processEvents()

        # Use an Event to wait for the hardware manager's internal
        # shutdown thread to actually complete (not just the call returning).
        shutdown_done = threading.Event()

        self._hw_manager.shutdown(
            warmup=True,
            on_complete=lambda: shutdown_done.set(),
            on_progress=lambda msg: log.info(f"Shutdown: {msg}"),
        )

        # Block until the hardware shutdown thread finishes
        shutdown_done.wait(timeout=360)

        log.info("Shutdown complete, closing application")
        QApplication.instance().quit()

    def _start_shutdown_with_dialog(self) -> None:
        """Start shutdown with a progress dialog.

        Shows a ShutdownDialog that displays temperature progress
        and allows force-quit.
        """
        self._set_controls_enabled(False)

        # Get current temperature for progress range
        start_temp = -60.0
        if self._hw_manager.camera:
            try:
                start_temp = self._hw_manager.camera.temperature
            except Exception:
                pass

        target_temp = -20.0

        # Create and show dialog
        self._shutdown_dialog = ShutdownDialog(self)
        self._shutdown_dialog.set_temperature_range(start_temp, target_temp)
        self._shutdown_dialog.set_status("Starting shutdown...")
        self._shutdown_dialog.force_quit_requested.connect(self._on_force_quit)

        # Connect temperature signal to update dialog
        self._signals.temperature_changed.connect(
            self._shutdown_dialog.update_temperature
        )

        self._shutdown_dialog.show()

        # Start shutdown in background
        self._hw_manager.shutdown(
            warmup=True,
            on_complete=lambda: self._acq_signals.shutdown_complete.emit(),
            on_progress=lambda msg: self._acq_signals.shutdown_progress.emit(msg),
        )

    def _on_force_quit(self) -> None:
        """Handle force quit request from shutdown dialog."""
        log.warning("Force quit requested")
        QApplication.instance().quit()

    @Slot()
    def _update_shutdown_progress(self) -> None:
        """Update shutdown progress bar based on last received temperature.

        Note: Does NOT access hardware directly to avoid race conditions.
        Temperature updates come from _on_shutdown_progress signal.
        """
        if not hasattr(self, "_shutdown_dialog") or self._shutdown_dialog is None:
            return

        # Calculate progress from stored temperature
        temp = getattr(self, "_shutdown_last_temp", self._shutdown_start_temp)
        temp_range = self._shutdown_target_temp - self._shutdown_start_temp
        if abs(temp_range) > 0.1:
            progress = (temp - self._shutdown_start_temp) / temp_range * 100
            progress = max(0, min(100, progress))
        else:
            progress = 100

        self._shutdown_dialog.setValue(int(progress))

    @Slot(str)
    def _on_shutdown_progress(self, message: str) -> None:
        """Handle shutdown progress message from hardware manager."""
        log.info(f"Shutdown progress: {message}")
        self._status_label.setText(message)

        # Update shutdown dialog status if visible
        if hasattr(self, "_shutdown_dialog") and self._shutdown_dialog is not None:
            self._shutdown_dialog.set_status(message)

    @Slot()
    def _on_shutdown_complete(self) -> None:
        """Handle shutdown complete - close the application."""
        log.info("Shutdown complete, closing application")
        self._status_label.setText("Shutdown complete")
        self._shutdown_in_progress = False

        # Close the shutdown dialog if visible
        if hasattr(self, "_shutdown_dialog") and self._shutdown_dialog is not None:
            self._shutdown_dialog.on_shutdown_complete()

        # Now close the application
        QApplication.instance().quit()
