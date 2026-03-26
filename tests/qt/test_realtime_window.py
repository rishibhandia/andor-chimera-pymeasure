"""Tests for Real-Time acquisition window.

TDD: Tests written first, then implementation.
"""

from __future__ import annotations

import pytest


class TestRealtimeWindowUI:
    """Tests for RealtimeWindow UI structure."""

    def test_realtime_window_has_mode_combo(self, qt_app, hardware_manager):
        """RealtimeWindow has a mode selection combo box."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert hasattr(window, "_mode_combo")
        assert window._mode_combo is not None

    def test_realtime_window_has_exposure_spinbox(self, qt_app, hardware_manager):
        """RealtimeWindow has an exposure time spinbox via CameraSettingsWidget."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert hasattr(window, "_camera_settings")
        assert window._camera_settings.exposure_spin is not None

    def test_realtime_window_has_start_stop_buttons(self, qt_app, hardware_manager):
        """RealtimeWindow has start and stop buttons."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert hasattr(window, "_start_button")
        assert hasattr(window, "_stop_button")
        assert window._start_button is not None
        assert window._stop_button is not None

    def test_realtime_window_has_plot_stack(self, qt_app, hardware_manager):
        """RealtimeWindow has a stacked widget for plots."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert hasattr(window, "_plot_stack")
        assert window._plot_stack is not None

    def test_realtime_window_has_status_bar(self, qt_app, hardware_manager):
        """RealtimeWindow has a status bar."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert window.statusBar() is not None

    def test_realtime_window_has_frame_label(self, qt_app, hardware_manager):
        """RealtimeWindow has a frame counter label."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert hasattr(window, "_frame_label")
        assert window._frame_label is not None

    def test_realtime_window_has_fps_label(self, qt_app, hardware_manager):
        """RealtimeWindow has an FPS display label."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert hasattr(window, "_fps_label")
        assert window._fps_label is not None


class TestRealtimeWindowInitialState:
    """Tests for RealtimeWindow initial state."""

    def test_stop_button_disabled_initially(self, qt_app, hardware_manager):
        """Stop button should be disabled when not running."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert not window._stop_button.isEnabled()

    def test_start_button_enabled_initially(self, qt_app, hardware_manager):
        """Start button should be enabled when not running."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert window._start_button.isEnabled()

    def test_running_flag_false_initially(self, qt_app, hardware_manager):
        """Running flag should be False initially."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert window._running is False


class TestRealtimeSignals:
    """Tests for RealtimeSignals class."""

    def test_realtime_signals_has_spectrum_ready(self, qt_app):
        """RealtimeSignals has spectrum_ready signal."""
        from andor_qt.windows.realtime_window import RealtimeSignals

        signals = RealtimeSignals()

        assert hasattr(signals, "spectrum_ready")

    def test_realtime_signals_has_image_ready(self, qt_app):
        """RealtimeSignals has image_ready signal."""
        from andor_qt.windows.realtime_window import RealtimeSignals

        signals = RealtimeSignals()

        assert hasattr(signals, "image_ready")

    def test_realtime_signals_has_frame_count_updated(self, qt_app):
        """RealtimeSignals has frame_count_updated signal."""
        from andor_qt.windows.realtime_window import RealtimeSignals

        signals = RealtimeSignals()

        assert hasattr(signals, "frame_count_updated")

    def test_realtime_signals_has_acquisition_started(self, qt_app):
        """RealtimeSignals has acquisition_started signal."""
        from andor_qt.windows.realtime_window import RealtimeSignals

        signals = RealtimeSignals()

        assert hasattr(signals, "acquisition_started")

    def test_realtime_signals_has_acquisition_stopped(self, qt_app):
        """RealtimeSignals has acquisition_stopped signal."""
        from andor_qt.windows.realtime_window import RealtimeSignals

        signals = RealtimeSignals()

        assert hasattr(signals, "acquisition_stopped")

    def test_realtime_signals_has_error(self, qt_app):
        """RealtimeSignals has error signal."""
        from andor_qt.windows.realtime_window import RealtimeSignals

        signals = RealtimeSignals()

        assert hasattr(signals, "error")


class TestRealtimeAcquisitionLoop:
    """Tests for continuous acquisition loop behavior.

    Note: These tests verify signal connections and state management
    without running actual acquisition to avoid Qt/threading issues.
    """

    def test_acquisition_started_signal_updates_ui(self, qt_app, hardware_manager):
        """Acquisition started signal updates UI state."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        # Simulate the signal being emitted
        window._signals.acquisition_started.emit()
        qt_app.processEvents()

        # Check UI state updates
        assert not window._start_button.isEnabled()
        assert window._stop_button.isEnabled()
        assert not window._mode_combo.isEnabled()
        assert window._status_label.text() == "Running"

    def test_acquisition_stopped_signal_updates_ui(self, qt_app, hardware_manager):
        """Acquisition stopped signal updates UI state."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        # First start, then stop
        window._signals.acquisition_started.emit()
        qt_app.processEvents()
        window._signals.acquisition_stopped.emit()
        qt_app.processEvents()

        # Check UI state returns to initial
        assert window._start_button.isEnabled()
        assert not window._stop_button.isEnabled()
        assert window._mode_combo.isEnabled()
        assert window._status_label.text() == "Stopped"

    def test_frame_count_signal_updates_label(self, qt_app, hardware_manager):
        """Frame count updated signal updates the frame label."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        window._signals.frame_count_updated.emit(42)
        qt_app.processEvents()

        assert "42" in window._frame_label.text()

    def test_error_signal_updates_status(self, qt_app, hardware_manager):
        """Error signal updates status label."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        window._signals.error.emit("Test error message")
        qt_app.processEvents()

        assert "Test error" in window._status_label.text()

    def test_start_without_hardware_emits_error(self, qt_app, hardware_manager):
        """Starting acquisition without initialized hardware emits error."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        # Don't initialize hardware
        window = RealtimeWindow(hardware_manager)

        errors = []
        window._signals.error.connect(lambda msg: errors.append(msg))

        window._start_acquisition()
        qt_app.processEvents()

        assert len(errors) == 1
        assert "not initialized" in errors[0]


class TestRealtimePlotUpdates:
    """Tests for plot updates and FPS display."""

    def test_spectrum_signal_updates_plot(self, qt_app, hardware_manager, wait_for):
        """Spectrum signal updates the spectrum plot."""
        import numpy as np

        from andor_qt.windows.realtime_window import RealtimeWindow

        hardware_manager.initialize()
        wait_for(lambda: hardware_manager.is_initialized, timeout=10.0)

        window = RealtimeWindow(hardware_manager)

        # Emit mock spectrum data
        wavelengths = np.linspace(400, 800, 100)
        intensities = np.random.rand(100) * 1000

        window._signals.spectrum_ready.emit(wavelengths, intensities)
        qt_app.processEvents()

        # Plot should have data set
        assert window._spectrum_plot is not None

    def test_fps_display_updates(self, qt_app, hardware_manager, wait_for):
        """FPS display updates during acquisition."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        hardware_manager.initialize()
        wait_for(lambda: hardware_manager.is_initialized, timeout=10.0)

        window = RealtimeWindow(hardware_manager)

        # Simulate frame updates
        window._frame_count = 10
        window._last_frame_count = 0
        window._update_fps()
        qt_app.processEvents()

        assert "10" in window._fps_label.text()

    def test_mode_switch_changes_plot(self, qt_app, hardware_manager):
        """Switching mode changes the visible plot."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        # Start with FVB mode (spectrum plot)
        window._mode_combo.setCurrentIndex(0)
        qt_app.processEvents()
        assert window._plot_stack.currentWidget() == window._spectrum_plot

        # Switch to Image mode
        window._mode_combo.setCurrentIndex(1)
        qt_app.processEvents()
        assert window._plot_stack.currentWidget() == window._image_plot
