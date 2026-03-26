"""End-to-end integration tests for Real-Time acquisition workflow.

These tests verify the Real-Time mode functionality through the
menu integration and signal-based state management.
"""

from __future__ import annotations

import time
import threading
from unittest.mock import MagicMock

import pytest


class TestRealtimeMenuIntegration:
    """Test Real-Time mode is accessible from the main window."""

    def test_realtime_menu_action_opens_window(
        self, qt_app, reset_singletons, wait_for
    ):
        """Real-Time Mode menu action opens the RealtimeWindow.

        Verifies:
        - Menu action exists and is clickable
        - RealtimeWindow is created
        - Window uses same HardwareManager instance
        """
        from PySide6.QtWidgets import QApplication

        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.windows.main_window import AndorSpectrometerWindow
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = AndorSpectrometerWindow()
        manager = HardwareManager.instance()

        # Wait for hardware initialization
        wait_for(lambda: manager.is_initialized, timeout=10)

        # Trigger Real-Time mode via menu action
        window._menu_bar.realtime_action.trigger()
        QApplication.processEvents()

        # Verify RealtimeWindow was created
        assert hasattr(window, "_realtime_window")
        assert window._realtime_window is not None
        assert isinstance(window._realtime_window, RealtimeWindow)

        # Verify it uses the same hardware manager
        assert window._realtime_window._hw_manager is manager

        # Cleanup
        window._realtime_window.close()
        manager.stop_temperature_polling()
        manager.shutdown(warmup=False)
        wait_for(lambda: not manager.is_initialized, timeout=5)


class TestRealtimeWindowWorkflow:
    """Test Real-Time window workflow states."""

    def test_realtime_start_stop_workflow(self, qt_app, reset_singletons, wait_for):
        """Start and stop acquisition updates UI state correctly.

        Verifies:
        - Start button disabled when running
        - Stop button enabled when running
        - Status shows "Running" when active
        - Status shows "Stopped" after stopping
        """
        from PySide6.QtWidgets import QApplication

        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.windows.realtime_window import RealtimeWindow

        # Initialize hardware
        hardware_manager = HardwareManager.instance()
        init_done = threading.Event()
        hardware_manager.initialize(on_complete=init_done.set)
        init_done.wait(timeout=10)

        window = RealtimeWindow(hardware_manager)

        # Initial state
        assert window._start_button.isEnabled()
        assert not window._stop_button.isEnabled()
        assert window._status_label.text() == "Idle"

        # Simulate acquisition started signal
        window._signals.acquisition_started.emit()
        QApplication.processEvents()

        # Running state
        assert not window._start_button.isEnabled()
        assert window._stop_button.isEnabled()
        assert window._status_label.text() == "Running"

        # Simulate acquisition stopped signal
        window._signals.acquisition_stopped.emit()
        QApplication.processEvents()

        # Stopped state
        assert window._start_button.isEnabled()
        assert not window._stop_button.isEnabled()
        assert window._status_label.text() == "Stopped"

        # Cleanup
        hardware_manager.shutdown(warmup=False)

    def test_realtime_mode_switching_fvb_to_image(
        self, qt_app, reset_singletons
    ):
        """Switching mode between FVB and Image changes the plot.

        Verifies:
        - Mode combo has FVB and Image options
        - Switching mode changes the visible plot widget
        - Mode combo is disabled during acquisition
        """
        from PySide6.QtWidgets import QApplication

        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.windows.realtime_window import RealtimeWindow

        hardware_manager = HardwareManager.instance()
        window = RealtimeWindow(hardware_manager)

        # Initial mode should be FVB (index 0)
        assert window._mode_combo.currentIndex() == 0
        assert window._plot_stack.currentWidget() == window._spectrum_plot

        # Switch to Image mode
        window._mode_combo.setCurrentIndex(1)
        QApplication.processEvents()

        # Plot should switch to image
        assert window._plot_stack.currentWidget() == window._image_plot

        # Switch back to FVB
        window._mode_combo.setCurrentIndex(0)
        QApplication.processEvents()

        # Plot should switch back to spectrum
        assert window._plot_stack.currentWidget() == window._spectrum_plot

        # Mode combo should be disabled during acquisition
        window._signals.acquisition_started.emit()
        QApplication.processEvents()
        assert not window._mode_combo.isEnabled()

        # And re-enabled when stopped
        window._signals.acquisition_stopped.emit()
        QApplication.processEvents()
        assert window._mode_combo.isEnabled()

    def test_realtime_exposure_change_while_not_running(
        self, qt_app, reset_singletons
    ):
        """Exposure time can be changed when not running.

        Verifies:
        - Exposure spinbox is accessible
        - Value can be changed
        - Has appropriate range limits
        """
        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.windows.realtime_window import RealtimeWindow

        hardware_manager = HardwareManager.instance()
        window = RealtimeWindow(hardware_manager)

        # Exposure spinbox is now inside CameraSettingsWidget
        exposure_spin = window._camera_settings.exposure_spin

        # Check initial value is within valid range
        assert exposure_spin.minimum() <= exposure_spin.value() <= exposure_spin.maximum()

        # Change exposure
        exposure_spin.setValue(0.5)
        assert exposure_spin.value() == 0.5

        # Check range
        assert exposure_spin.minimum() >= 1e-6  # minimum is 1 µs
        assert exposure_spin.maximum() <= 300.0


class TestRealtimeFPSAndFrameCounter:
    """Test FPS and frame counter functionality."""

    def test_frame_counter_updates_on_signal(self, qt_app, reset_singletons):
        """Frame counter label updates when signal emitted.

        Verifies:
        - Frame label shows initial value 0
        - Updates when frame_count_updated signal emitted
        """
        from PySide6.QtWidgets import QApplication

        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.windows.realtime_window import RealtimeWindow

        hardware_manager = HardwareManager.instance()
        window = RealtimeWindow(hardware_manager)

        # Initial frame count
        assert "0" in window._frame_label.text()

        # Emit frame count signals
        window._signals.frame_count_updated.emit(10)
        QApplication.processEvents()
        assert "10" in window._frame_label.text()

        window._signals.frame_count_updated.emit(100)
        QApplication.processEvents()
        assert "100" in window._frame_label.text()

    def test_fps_updates_correctly(self, qt_app, reset_singletons):
        """FPS display calculates correctly from frame delta.

        Verifies:
        - FPS label shows "--" initially
        - Updates correctly based on frame count delta
        """
        from PySide6.QtWidgets import QApplication

        from andor_qt.core.hardware_manager import HardwareManager
        from andor_qt.windows.realtime_window import RealtimeWindow

        hardware_manager = HardwareManager.instance()
        window = RealtimeWindow(hardware_manager)

        # Initial FPS display
        assert "--" in window._fps_label.text()

        # Simulate frame counts
        window._frame_count = 30
        window._last_frame_count = 0
        window._update_fps()
        QApplication.processEvents()

        # FPS should show 30 (frames in 1 second)
        assert "30" in window._fps_label.text()

        # Simulate another second
        window._frame_count = 55
        window._last_frame_count = 30
        window._update_fps()
        QApplication.processEvents()

        # FPS should show 25
        assert "25" in window._fps_label.text()
