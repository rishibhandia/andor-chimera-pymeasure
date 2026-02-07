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
        """RealtimeWindow has an exposure time spinbox."""
        from andor_qt.windows.realtime_window import RealtimeWindow

        window = RealtimeWindow(hardware_manager)

        assert hasattr(window, "_exposure_spin")
        assert window._exposure_spin is not None

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
