"""Real-Time acquisition window for continuous live display.

Provides a separate window for continuous acquisition with live
spectrum or image display, FPS counter, and frame statistics.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from andor_qt.core.hardware_manager import HardwareManager
from andor_qt.widgets.display import ImagePlotWidget, SpectrumPlotWidget

log = logging.getLogger(__name__)


class RealtimeSignals(QObject):
    """Signals for thread-safe real-time acquisition updates."""

    spectrum_ready = Signal(object, object)  # (wavelengths, intensities)
    image_ready = Signal(object, object)  # (image, wavelengths)
    frame_count_updated = Signal(int)  # frame_count
    acquisition_started = Signal()
    acquisition_stopped = Signal()
    error = Signal(str)  # error_message


class RealtimeWindow(QMainWindow):
    """Real-Time acquisition window with continuous live display.

    Layout:
        ┌─────────────────────────────────────────────────────────────┐
        │  Real-Time Acquisition                           [─][□][×]  │
        ├───────────────────────┬─────────────────────────────────────┤
        │  Settings             │            Display                  │
        │  Mode: [FVB ▼]        │  ┌─────────────────────────────┐    │
        │  Exposure: [0.1] s    │  │ SpectrumPlot / ImagePlot   │    │
        │  [▶ Start] [■ Stop]   │  │                             │    │
        │  Frame: 0             │  └─────────────────────────────┘    │
        ├───────────────────────┴─────────────────────────────────────┤
        │  Status: Idle | FPS: -- | Last acquisition: --              │
        └─────────────────────────────────────────────────────────────┘
    """

    def __init__(self, hw_manager: HardwareManager, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._hw_manager = hw_manager
        self._signals = RealtimeSignals()
        self._running = False
        self._frame_count = 0
        self._last_frame_count = 0
        self._acq_thread: Optional[threading.Thread] = None

        self.setWindowTitle("Real-Time Acquisition")
        self.setMinimumSize(900, 600)

        self._setup_ui()
        self._setup_status_bar()
        self._connect_signals()
        self._setup_fps_timer()

    def _setup_ui(self) -> None:
        """Set up the main window UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # Left panel - Settings
        settings_panel = self._create_settings_panel()
        main_layout.addWidget(settings_panel)

        # Right panel - Display
        display_panel = self._create_display_panel()
        main_layout.addWidget(display_panel, stretch=1)

    def _create_settings_panel(self) -> QWidget:
        """Create the settings panel with controls."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        # Mode selection
        mode_group = QGroupBox("Acquisition Mode")
        mode_layout = QVBoxLayout(mode_group)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("FVB (Full Vertical Binning)", "fvb")
        self._mode_combo.addItem("Image (2D)", "image")
        mode_layout.addWidget(self._mode_combo)

        layout.addWidget(mode_group)

        # Exposure settings
        exposure_group = QGroupBox("Exposure")
        exposure_layout = QVBoxLayout(exposure_group)

        exposure_row = QHBoxLayout()
        exposure_row.addWidget(QLabel("Exposure:"))
        self._exposure_spin = QDoubleSpinBox()
        self._exposure_spin.setRange(0.001, 300.0)
        self._exposure_spin.setValue(0.1)
        self._exposure_spin.setSuffix(" s")
        self._exposure_spin.setDecimals(3)
        exposure_row.addWidget(self._exposure_spin)
        exposure_layout.addLayout(exposure_row)

        layout.addWidget(exposure_group)

        # Control buttons
        control_group = QGroupBox("Control")
        control_layout = QVBoxLayout(control_group)

        button_row = QHBoxLayout()
        self._start_button = QPushButton("▶ Start")
        self._start_button.clicked.connect(self._start_acquisition)
        button_row.addWidget(self._start_button)

        self._stop_button = QPushButton("■ Stop")
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._stop_acquisition)
        button_row.addWidget(self._stop_button)
        control_layout.addLayout(button_row)

        layout.addWidget(control_group)

        # Frame counter
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout(stats_group)

        self._frame_label = QLabel("Frame: 0")
        stats_layout.addWidget(self._frame_label)

        self._fps_label = QLabel("FPS: --")
        stats_layout.addWidget(self._fps_label)

        layout.addWidget(stats_group)

        layout.addStretch()
        return panel

    def _create_display_panel(self) -> QWidget:
        """Create the display panel with plot stack."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Stacked widget for 1D/2D plots
        self._plot_stack = QStackedWidget()

        self._spectrum_plot = SpectrumPlotWidget()
        self._plot_stack.addWidget(self._spectrum_plot)

        self._image_plot = ImagePlotWidget()
        self._plot_stack.addWidget(self._image_plot)

        layout.addWidget(self._plot_stack)
        return panel

    def _setup_status_bar(self) -> None:
        """Set up the status bar."""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self._status_label = QLabel("Idle")
        status_bar.addWidget(self._status_label)

    def _connect_signals(self) -> None:
        """Connect signals between components."""
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._signals.spectrum_ready.connect(self._on_spectrum_ready)
        self._signals.image_ready.connect(self._on_image_ready)
        self._signals.frame_count_updated.connect(self._on_frame_count_updated)
        self._signals.acquisition_started.connect(self._on_acquisition_started)
        self._signals.acquisition_stopped.connect(self._on_acquisition_stopped)
        self._signals.error.connect(self._on_error)

    def _setup_fps_timer(self) -> None:
        """Set up the FPS calculation timer."""
        self._fps_timer = QTimer()
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.setInterval(1000)  # Update every second

    @Slot(int)
    def _on_mode_changed(self, index: int) -> None:
        """Handle mode selection change."""
        mode = self._mode_combo.currentData()
        if mode == "image":
            self._plot_stack.setCurrentWidget(self._image_plot)
        else:
            self._plot_stack.setCurrentWidget(self._spectrum_plot)

    def _start_acquisition(self) -> None:
        """Start continuous acquisition loop."""
        if self._running:
            return

        if not self._hw_manager.is_initialized:
            self._signals.error.emit("Hardware not initialized")
            return

        self._running = True
        self._frame_count = 0
        self._last_frame_count = 0
        self._signals.acquisition_started.emit()

        mode = self._mode_combo.currentData()

        def _acquisition_loop():
            """Background acquisition loop."""
            try:
                while self._running:
                    exposure = self._exposure_spin.value()
                    self._hw_manager.camera.set_exposure(exposure)

                    if mode == "fvb":
                        data = self._hw_manager.camera.acquire_fvb()
                        calibration = self._hw_manager.get_calibration()
                        self._signals.spectrum_ready.emit(calibration, data)
                    else:
                        data = self._hw_manager.camera.acquire_image()
                        calibration = self._hw_manager.get_calibration()
                        self._signals.image_ready.emit(data, calibration)

                    self._frame_count += 1
                    self._signals.frame_count_updated.emit(self._frame_count)

            except Exception as e:
                log.error(f"Acquisition error: {e}")
                self._signals.error.emit(str(e))
            finally:
                self._running = False
                self._signals.acquisition_stopped.emit()

        self._acq_thread = threading.Thread(target=_acquisition_loop, daemon=True)
        self._acq_thread.start()

    def _stop_acquisition(self) -> None:
        """Stop continuous acquisition."""
        self._running = False
        if self._hw_manager.camera:
            self._hw_manager.camera.abort_acquisition()

    @Slot(object, object)
    def _on_spectrum_ready(self, wavelengths, intensities) -> None:
        """Handle spectrum data ready."""
        self._spectrum_plot.set_data(wavelengths, intensities)

    @Slot(object, object)
    def _on_image_ready(self, image, wavelengths) -> None:
        """Handle image data ready."""
        self._image_plot.set_data(image, wavelengths)

    @Slot(int)
    def _on_frame_count_updated(self, frame_count: int) -> None:
        """Handle frame count update."""
        self._frame_label.setText(f"Frame: {frame_count}")

    @Slot()
    def _on_acquisition_started(self) -> None:
        """Handle acquisition started."""
        self._start_button.setEnabled(False)
        self._stop_button.setEnabled(True)
        self._mode_combo.setEnabled(False)
        self._status_label.setText("Running")
        self._fps_timer.start()

    @Slot()
    def _on_acquisition_stopped(self) -> None:
        """Handle acquisition stopped."""
        self._start_button.setEnabled(True)
        self._stop_button.setEnabled(False)
        self._mode_combo.setEnabled(True)
        self._status_label.setText("Stopped")
        self._fps_timer.stop()

    @Slot(str)
    def _on_error(self, error_msg: str) -> None:
        """Handle acquisition error."""
        self._status_label.setText(f"Error: {error_msg}")
        self._stop_acquisition()

    @Slot()
    def _update_fps(self) -> None:
        """Update FPS display."""
        fps = self._frame_count - self._last_frame_count
        self._last_frame_count = self._frame_count
        self._fps_label.setText(f"FPS: {fps}")

    def closeEvent(self, event) -> None:
        """Handle window close - stop acquisition first."""
        self._stop_acquisition()
        # Wait briefly for thread to stop
        if self._acq_thread and self._acq_thread.is_alive():
            self._acq_thread.join(timeout=1.0)
        event.accept()
