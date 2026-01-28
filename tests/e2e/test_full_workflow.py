"""End-to-end integration tests for the full application workflow.

These tests verify complete user workflows using mock hardware,
from startup through acquisition to shutdown.
"""

from __future__ import annotations

import time
import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestFullStartupSequence:
    """Test the full application startup sequence."""

    def test_full_startup_sequence(self, qt_app, reset_singletons, wait_for):
        """Application starts, initializes hardware, and UI is ready.

        Verifies:
        - HardwareManager initializes in mock mode
        - Camera and spectrograph are available
        - Hardware signals are emitted
        - UI components are present and configured
        """
        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.core.signals import get_hardware_signals

        signals = get_hardware_signals()

        # Track signals
        camera_init_received = []
        spec_init_received = []
        signals.camera_initialized.connect(
            lambda d: camera_init_received.append(d)
        )
        signals.spectrograph_initialized.connect(
            lambda d: spec_init_received.append(d)
        )

        # Initialize hardware (as app would)
        manager = HardwareManager.instance()
        init_complete = threading.Event()
        init_error = []

        manager.initialize(
            on_complete=lambda: init_complete.set(),
            on_error=lambda msg: init_error.append(msg),
        )

        # Wait for initialization
        assert init_complete.wait(timeout=10), "Hardware initialization timed out"
        assert len(init_error) == 0, f"Hardware init error: {init_error}"

        # Verify hardware is ready
        assert manager.is_initialized
        assert manager.camera is not None
        assert manager.spectrograph is not None
        assert manager.mock_mode is True

        # Verify camera properties
        assert manager.camera.xpixels > 0
        assert manager.camera.ypixels > 0

        # Verify spectrograph properties
        assert manager.spectrograph.wavelength >= 0

        # Verify signals were emitted (need event processing for cross-thread signals)
        assert wait_for(lambda: len(camera_init_received) > 0, timeout=5)
        assert wait_for(lambda: len(spec_init_received) > 0, timeout=5)

        # Verify camera init signal content
        cam_info = camera_init_received[0]
        assert "xpixels" in cam_info
        assert "ypixels" in cam_info

        # Cleanup
        manager.shutdown(warmup=False)
        wait_for(lambda: not manager.is_initialized, timeout=5)

    def test_startup_creates_all_widgets(self, qt_app, reset_singletons, wait_for):
        """Main window creates all required widgets on startup."""
        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.windows.main_window import AndorSpectrometerWindow

        # The main window will create HardwareManager.instance() internally
        # and call initialize(). We need to wait for that.
        window = AndorSpectrometerWindow()

        # Wait for hardware initialization
        manager = HardwareManager.instance()
        wait_for(lambda: manager.is_initialized, timeout=10)

        # Verify all UI components exist
        assert window._temp_control is not None
        assert window._spec_control is not None
        assert window._inputs_widget is not None
        assert window._acquire_control is not None
        assert window._queue_control is not None
        assert window._data_settings is not None
        assert window._spectrum_plot is not None
        assert window._image_plot is not None
        assert window._results_table is not None
        assert window._menu_bar is not None

        # Verify status bar
        assert window._status_bar is not None
        assert window._temp_status_label is not None
        assert window._wl_status_label is not None

        # Cleanup
        manager.stop_temperature_polling()
        manager.shutdown(warmup=False)
        wait_for(lambda: not manager.is_initialized, timeout=5)


class TestAcquireAndSaveWorkflow:
    """Test the acquisition and data saving workflow."""

    def test_acquire_and_save_workflow(self, qt_app, reset_singletons, wait_for, tmp_path):
        """Full acquire → display → save workflow with mock hardware.

        Verifies:
        - Hardware initializes
        - Acquisition completes successfully
        - Data is saved to disk when auto-save is on
        """
        from PySide6.QtWidgets import QApplication
        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()
        manager = HardwareManager.instance()

        # Wait for initialization
        assert wait_for(lambda: manager.is_initialized, timeout=10), \
            "Hardware did not initialize"

        # Process pending events to let UI update
        QApplication.processEvents()

        # Configure data settings for auto-save to tmp directory
        window._data_settings.directory = str(tmp_path)
        window._data_settings.base_name = "test_spectrum"
        window._data_settings.auto_save = True

        # Track acquisition completion
        acq_completed = []
        original_on_acq_completed = window._on_acq_completed

        def _on_completed(exp_id):
            original_on_acq_completed(exp_id)
            acq_completed.append(exp_id)

        window._acq_signals.completed.disconnect(window._on_acq_completed)
        window._acq_signals.completed.connect(_on_completed)

        # Trigger acquisition via the queue click handler
        window._on_queue_clicked()

        # Wait for acquisition to complete (needs Qt event processing for signals)
        assert wait_for(lambda: len(acq_completed) > 0, timeout=15), \
            "Acquisition did not complete"

        # Process remaining events for auto-save
        QApplication.processEvents()
        time.sleep(0.5)
        QApplication.processEvents()

        # Verify data was saved (auto-save should have triggered)
        saved_files = list(tmp_path.glob("test_spectrum_*"))
        assert len(saved_files) > 0, f"No saved files found in {tmp_path}"

        # Verify the saved file has content
        saved_file = saved_files[0]
        assert saved_file.stat().st_size > 0

        # Cleanup
        manager.stop_temperature_polling()
        manager.shutdown(warmup=False)
        wait_for(lambda: not manager.is_initialized, timeout=5)


class TestChangeSettingsAndAcquire:
    """Test changing settings and then acquiring."""

    def test_change_settings_and_acquire(self, qt_app, reset_singletons, wait_for):
        """Changing hardware settings before acquisition works correctly.

        Verifies:
        - Wavelength can be changed
        - Grating can be changed
        - Acquisition works after settings change
        """
        from PySide6.QtWidgets import QApplication
        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.core.signals import get_hardware_signals

        signals = get_hardware_signals()
        manager = HardwareManager.instance()

        # Initialize hardware
        init_complete = threading.Event()
        manager.initialize(on_complete=lambda: init_complete.set())
        assert init_complete.wait(timeout=10), "Hardware init timed out"

        # Change wavelength
        wl_changed = threading.Event()
        manager.set_wavelength(
            600.0,
            on_complete=lambda: wl_changed.set(),
        )
        assert wl_changed.wait(timeout=5), "Wavelength change timed out"

        # Verify wavelength was set
        assert manager.spectrograph.wavelength == 600.0

        # Change grating
        grating_changed = threading.Event()
        manager.set_grating(
            2,
            on_complete=lambda: grating_changed.set(),
        )
        assert grating_changed.wait(timeout=5), "Grating change timed out"

        # Verify grating was set
        assert manager.spectrograph.grating == 2

        # Get calibration (should reflect new settings)
        calibration = manager.get_calibration()
        assert calibration is not None
        assert len(calibration) == manager.camera.xpixels

        # Perform an acquisition
        data = manager.camera.acquire_fvb()
        assert data is not None
        assert len(data) > 0

        # Cleanup
        manager.shutdown(warmup=False)
        wait_for(lambda: not manager.is_initialized, timeout=5)


class TestShutdownWorkflow:
    """Test the shutdown workflow."""

    def test_shutdown_workflow(self, qt_app, reset_singletons, wait_for):
        """Shutdown properly cleans up hardware resources.

        Verifies:
        - Shutdown completes without errors
        - Camera and spectrograph are released
        - Hardware is no longer initialized
        - EventBus publishes shutdown event
        """
        from andor_qt.core.event_bus import get_event_bus
        from andor_qt.core.hardware_manager import HardwareManager

        manager = HardwareManager.instance()

        # Initialize hardware first
        init_complete = threading.Event()
        manager.initialize(on_complete=lambda: init_complete.set())
        assert init_complete.wait(timeout=10), "Hardware init timed out"
        assert manager.is_initialized

        # Track shutdown event
        shutdown_events = []
        event_bus = get_event_bus()
        handler = MagicMock()
        handler.__name__ = "test_handler"
        event_bus.subscribe("hardware.shutdown", handler)

        # Track shutdown progress
        progress_messages = []

        # Start shutdown
        shutdown_complete = threading.Event()
        manager.shutdown(
            warmup=False,
            on_complete=lambda: shutdown_complete.set(),
            on_progress=lambda msg: progress_messages.append(msg),
        )

        # Wait for shutdown
        assert shutdown_complete.wait(timeout=10), "Shutdown did not complete"

        # Verify hardware is released
        assert not manager.is_initialized
        assert manager.camera is None
        assert manager.spectrograph is None

        # Verify progress messages were sent
        assert len(progress_messages) > 0

        # Verify EventBus event was published
        assert wait_for(lambda: handler.call_count > 0, timeout=2), \
            "Shutdown event not published to EventBus"

    def test_shutdown_dialog_creation(self, qt_app, reset_singletons, wait_for):
        """ShutdownDialog can be created and shows required components."""
        from andor_qt.widgets.dialogs.shutdown_dialog import ShutdownDialog

        dialog = ShutdownDialog()

        # Verify dialog has all required components
        assert dialog._status_label is not None
        assert dialog._temp_label is not None
        assert dialog._progress_bar is not None
        assert dialog._force_quit_btn is not None

        # Verify initial state
        dialog.set_temperature_range(-60.0, -20.0)
        dialog.set_status("Testing shutdown...")
        assert "Testing" in dialog._status_label.text()

        # Update temperature
        dialog.update_temperature(-40.0, "NOT_REACHED")
        assert "-40" in dialog._temp_label.text()

        # Test progress calculation
        progress = dialog._progress_bar.value()
        assert progress >= 0
