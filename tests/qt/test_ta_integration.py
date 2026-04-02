"""Tests for TA module integration into main window.

Verifies that TAWindowPanel is created and wired correctly,
and that the main window has a TA tab.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ["ANDOR_MOCK"] = "1"


@pytest.fixture
def mock_hw_manager():
    """Create a minimal mock HardwareManager."""
    mgr = MagicMock()
    mgr.camera = MagicMock()
    mgr.spectrograph = MagicMock()
    mgr.motion_manager = MagicMock()
    mgr.motion_manager.get_axis.return_value = None
    mgr.motion_manager.all_axes = {}
    mgr.get_wavelengths.return_value = [500.0, 600.0, 700.0]
    return mgr


class TestTAWindowPanel:
    def test_creates_successfully(self, qt_app, mock_hw_manager):
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        assert panel is not None
        panel.deleteLater()

    def test_has_config_widget(self, qt_app, mock_hw_manager):
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        assert panel.config_widget is not None
        panel.deleteLater()

    def test_has_live_display(self, qt_app, mock_hw_manager):
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        assert panel.live_display is not None
        panel.deleteLater()

    def test_has_engine(self, qt_app, mock_hw_manager):
        from andor_qt.windows.ta_panel import TAWindowPanel
        from andor_qt.ta.engine import TransientAbsorptionEngine
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        assert isinstance(panel.engine, TransientAbsorptionEngine)
        panel.deleteLater()

    def test_scan_requested_connects_to_engine(self, qt_app, mock_hw_manager):
        """scan_requested signal from config widget should trigger engine start."""
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        # Should not raise when scan is requested with mock hw
        from andor_qt.ta.scan_config import TAScanConfig
        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="boxcar", scan_direction="forward",
            sample_name="test",
        )
        # Just verify emitting doesn't crash
        panel.config_widget.scan_requested.emit(config)
        panel.engine.abort()
        panel.deleteLater()


class TestChopper2x2Panel:
    """TAWindowPanel creates mock NI DAQ objects for chopper_2x2 mode."""

    def _make_panel(self, mock_hw_manager, qt_app):
        from andor_qt.windows.ta_panel import TAWindowPanel
        return TAWindowPanel(hw_manager=mock_hw_manager)

    def test_chopper_2x2_passes_trigger_gen_to_engine(self, qt_app, mock_hw_manager):
        from unittest.mock import patch
        from andor_qt.ta.scan_config import TAScanConfig
        from andor_qt.windows.ta_panel import TAWindowPanel

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="chopper_2x2", scan_direction="forward",
            sample_name="test",
        )
        captured = {}
        original = panel._engine.start_scan
        def _capture(*args, **kwargs):
            captured.update(kwargs)
            return original(*args, **kwargs)

        with patch.object(panel._engine, "start_scan", side_effect=_capture):
            panel.config_widget.scan_requested.emit(config)

        panel.engine.abort()
        panel.deleteLater()
        assert captured.get("trigger_gen") is not None

    def test_chopper_2x2_passes_phase_reader_to_engine(self, qt_app, mock_hw_manager):
        from unittest.mock import patch
        from andor_qt.ta.scan_config import TAScanConfig
        from andor_qt.windows.ta_panel import TAWindowPanel

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="chopper_2x2", scan_direction="forward",
            sample_name="test",
        )
        captured = {}
        original = panel._engine.start_scan
        def _capture(*args, **kwargs):
            captured.update(kwargs)
            return original(*args, **kwargs)

        with patch.object(panel._engine, "start_scan", side_effect=_capture):
            panel.config_widget.scan_requested.emit(config)

        panel.engine.abort()
        panel.deleteLater()
        assert captured.get("phase_reader") is not None

    def test_non_chopper_mode_has_no_trigger_gen(self, qt_app, mock_hw_manager):
        from unittest.mock import patch
        from andor_qt.ta.scan_config import TAScanConfig
        from andor_qt.windows.ta_panel import TAWindowPanel

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="boxcar", scan_direction="forward",
            sample_name="test",
        )
        captured = {}
        original = panel._engine.start_scan
        def _capture(*args, **kwargs):
            captured.update(kwargs)
            return original(*args, **kwargs)

        with patch.object(panel._engine, "start_scan", side_effect=_capture):
            panel.config_widget.scan_requested.emit(config)

        panel.engine.abort()
        panel.deleteLater()
        assert captured.get("trigger_gen") is None
        assert captured.get("phase_reader") is None

    def test_chopper_2x2_uses_mock_objects_in_mock_mode(self, qt_app, mock_hw_manager):
        from andor_qt.ta.scan_config import TAScanConfig
        from andor_qt.ta.nidaq_trigger import MockNIDAQChopper500Hz
        from andor_qt.ta.nidaq_phase import MockNIDAQChopper2x2Reader
        from andor_qt.windows.ta_panel import TAWindowPanel

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="chopper_2x2", scan_direction="forward",
            sample_name="test",
        )
        captured = {}
        original = panel._engine.start_scan
        def _capture(*args, **kwargs):
            captured.update(kwargs)
            return original(*args, **kwargs)

        with patch.object(panel._engine, "start_scan", side_effect=_capture):
            panel.config_widget.scan_requested.emit(config)

        panel.engine.abort()
        panel.deleteLater()
        assert isinstance(captured.get("trigger_gen"), MockNIDAQChopper500Hz)
        from andor_qt.ta.nidaq_phase import MockNIDAQPhaseReader
        assert isinstance(captured.get("phase_reader"), MockNIDAQPhaseReader)


class TestShotToShotPanel:
    def test_shot_to_shot_creates_phase_reader_only(self, qt_app, mock_hw_manager):
        """shot_to_shot mode should create a phase reader but no trigger gen."""
        from unittest.mock import patch
        from andor_qt.windows.ta_panel import TAWindowPanel
        from andor_qt.ta.scan_config import TAScanConfig

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        config = TAScanConfig(
            delay_list=[0.0],
            n_averages=1,
            n_scans=1,
            acquisition_mode="shot_to_shot",
            scan_direction="forward",
            sample_name="test",
            crop_height=50,
        )

        captured = {}
        def _capture(*args, **kwargs):
            captured.update(kwargs)
        with patch.object(panel._engine, "start_scan", side_effect=_capture):
            panel.config_widget.scan_requested.emit(config)

        panel.engine.abort()
        panel.deleteLater()
        assert captured.get("trigger_gen") is None
        assert captured.get("phase_reader") is not None


class TestCameraBusySignal:
    """TAWindowPanel.camera_busy should fire True/False around scan and monitor."""

    def test_camera_busy_signal_exists(self, qt_app, mock_hw_manager):
        from andor_qt.windows.ta_panel import TAWindowPanel
        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        assert hasattr(panel, "camera_busy"), "TAWindowPanel must have camera_busy signal"
        panel.deleteLater()

    def test_camera_busy_true_on_scan_start(self, qt_app, mock_hw_manager):
        """camera_busy(True) should be emitted when a scan starts."""
        from andor_qt.windows.ta_panel import TAWindowPanel
        from andor_qt.ta.scan_config import TAScanConfig

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        received = []
        panel.camera_busy.connect(lambda v: received.append(v))

        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="boxcar", scan_direction="forward",
            sample_name="test",
        )
        panel.config_widget.scan_requested.emit(config)
        panel.engine.abort()
        panel.deleteLater()
        assert True in received, "camera_busy(True) not emitted on scan start"

    def test_camera_busy_false_on_scan_end(self, qt_app, mock_hw_manager):
        """camera_busy(False) should be emitted when a scan completes/aborts."""
        from andor_qt.windows.ta_panel import TAWindowPanel
        from andor_qt.ta.scan_config import TAScanConfig
        from PySide6.QtWidgets import QApplication
        import time

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        received = []
        panel.camera_busy.connect(lambda v: received.append(v))

        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="boxcar", scan_direction="forward",
            sample_name="test",
        )
        panel.config_widget.scan_requested.emit(config)
        panel.engine.abort()

        # Process events to let signals propagate
        app = QApplication.instance()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            app.processEvents()
            if False in received:
                break
            time.sleep(0.05)

        panel.deleteLater()
        assert False in received, "camera_busy(False) not emitted on scan end"

    def test_camera_busy_true_on_monitor_start(self, qt_app, mock_hw_manager):
        """camera_busy(True) should be emitted when monitor starts."""
        from andor_qt.windows.ta_panel import TAWindowPanel
        from andor_qt.ta.scan_config import TAScanConfig

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        received = []
        panel.camera_busy.connect(lambda v: received.append(v))

        config = TAScanConfig(
            delay_list=[0.0], n_averages=1,
            acquisition_mode="boxcar", scan_direction="forward",
            sample_name="monitor",
        )
        panel._on_monitor_requested(config)
        panel._monitor_engine.stop()

        panel.deleteLater()
        assert True in received, "camera_busy(True) not emitted on monitor start"

    def test_camera_busy_false_on_monitor_stop(self, qt_app, mock_hw_manager):
        """camera_busy(False) should be emitted when monitor stops."""
        from andor_qt.windows.ta_panel import TAWindowPanel
        from andor_qt.ta.scan_config import TAScanConfig
        from PySide6.QtWidgets import QApplication
        import time

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        received = []
        panel.camera_busy.connect(lambda v: received.append(v))

        config = TAScanConfig(
            delay_list=[0.0], n_averages=1,
            acquisition_mode="boxcar", scan_direction="forward",
            sample_name="monitor",
        )
        panel._on_monitor_requested(config)
        panel._monitor_engine.stop()

        app = QApplication.instance()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            app.processEvents()
            if False in received:
                break
            time.sleep(0.05)

        panel.deleteLater()
        assert False in received, "camera_busy(False) not emitted on monitor stop"


class TestMainWindowAcquireLockout:
    """Main window acquire/queue buttons should be disabled during TA camera use."""

    def test_acquire_disabled_during_ta_scan(self, qt_app, mock_sdk):
        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()
        # Simulate TA camera busy
        window._ta_panel.camera_busy.emit(True)

        assert not window._acquire_control._acquire_btn.isEnabled(), \
            "Acquire button should be disabled when TA camera is busy"
        window.deleteLater()

    def test_acquire_reenabled_after_ta_scan(self, qt_app, mock_sdk):
        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()
        window._ta_panel.camera_busy.emit(True)
        window._ta_panel.camera_busy.emit(False)

        assert window._acquire_control._acquire_btn.isEnabled(), \
            "Acquire button should be re-enabled when TA camera is free"
        window.deleteLater()

    def test_queue_disabled_during_ta_scan(self, qt_app, mock_sdk):
        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()
        window._ta_panel.camera_busy.emit(True)

        assert not window._queue_control._queue_button.isEnabled(), \
            "Queue button should be disabled when TA camera is busy"
        window.deleteLater()


class TestMainWindowTATab:
    def test_main_window_has_ta_tab(self, qt_app, mock_sdk):
        """Main window should have a TA tab."""
        from unittest.mock import patch
        from PySide6.QtWidgets import QTabWidget
        from andor_qt.windows.main_window import AndorSpectrometerWindow

        window = AndorSpectrometerWindow()
        # Find top-level tab widget
        tabs = window.findChildren(QTabWidget)
        assert len(tabs) > 0

        # One of them should have a tab called "TA" or "Transient Absorption"
        ta_tab_found = False
        for tab_widget in tabs:
            for i in range(tab_widget.count()):
                label = tab_widget.tabText(i)
                if "TA" in label or "Transient" in label:
                    ta_tab_found = True
                    break

        # Skip close() to avoid triggering the blocking shutdown sequence in tests
        window.deleteLater()

        assert ta_tab_found, "No TA tab found in main window"


class TestHbinWavelengthAlignment:
    """Wavelength arrays must match hbin-reduced pixel count."""

    def test_hdf5_writer_gets_hbin_adjusted_wavelengths(self, qt_app, mock_hw_manager, tmp_path):
        """HDF5 writer wavelength array should have xpixels/hbin points."""
        import numpy as np
        from andor_qt.windows.ta_panel import TAWindowPanel
        from andor_qt.ta.scan_config import TAScanConfig

        # Mock get_wavelengths to return different lengths based on hbin
        def _mock_get_wl(hbin=1):
            n_pixels = 1600 // hbin
            return np.linspace(400, 800, n_pixels)
        mock_hw_manager.get_wavelengths.side_effect = _mock_get_wl

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="boxcar", scan_direction="forward",
            sample_name="test",
            save_hdf5_dir=str(tmp_path),
        )

        # Set hbin=8 in camera settings
        panel._config_widget._camera_settings.hbin_combo.setCurrentIndex(3)  # 8x
        captured = {}
        def _capture(*args, **kwargs):
            captured.update(kwargs)
        with patch.object(panel._engine, "start_scan", side_effect=_capture):
            panel.config_widget.scan_requested.emit(config)

        panel.engine.abort()

        # Verify get_wavelengths was called with hbin=8
        mock_hw_manager.get_wavelengths.assert_called_with(hbin=8)

        # Verify the writer was created with 200 wavelength points
        writer = panel._writer
        if writer is not None:
            assert len(writer._wavelengths) == 200, (
                f"Expected 200 wavelengths (1600/8), got {len(writer._wavelengths)}"
            )
            writer.finalize()
        panel.deleteLater()

    def test_scan_engine_gets_hbin_adjusted_wavelengths(self, qt_app, mock_hw_manager):
        """Scan engine should pass hbin to get_wavelengths via ta_panel."""
        import numpy as np
        from andor_qt.windows.ta_panel import TAWindowPanel
        from andor_qt.ta.scan_config import TAScanConfig

        def _mock_get_wl(hbin=1):
            return np.linspace(400, 800, 1600 // hbin)
        mock_hw_manager.get_wavelengths.side_effect = _mock_get_wl

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        # Set hbin=4 in camera settings
        panel._config_widget._camera_settings.hbin_combo.setCurrentIndex(2)  # 4x

        config = TAScanConfig(
            delay_list=[0.0], n_averages=1, n_scans=1,
            acquisition_mode="boxcar", scan_direction="forward",
            sample_name="test",
        )
        captured = {}
        def _capture(*args, **kwargs):
            captured.update(kwargs)
        with patch.object(panel._engine, "start_scan", side_effect=_capture):
            panel.config_widget.scan_requested.emit(config)

        panel.engine.abort()
        panel.deleteLater()
        # camera_settings should have hbin=4
        cs = captured.get("camera_settings", {})
        assert cs.get("hbin") == 4

    def test_monitor_engine_gets_hbin_adjusted_wavelengths(self, qt_app, mock_hw_manager):
        """Monitor pre_set_wavelengths should pass hbin to get_wavelengths."""
        import numpy as np
        from andor_qt.windows.ta_panel import TAWindowPanel

        def _mock_get_wl(hbin=1):
            return np.linspace(400, 800, 1600 // hbin)
        mock_hw_manager.get_wavelengths.side_effect = _mock_get_wl

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        panel._pre_set_wavelengths({"hbin": 4})

        mock_hw_manager.get_wavelengths.assert_called_with(hbin=4)
        assert len(panel._live_display._wavelengths) == 400
        panel.deleteLater()

    def test_pre_set_wavelengths_passes_hbin(self, qt_app, mock_hw_manager):
        """_pre_set_wavelengths should pass hbin from camera_settings."""
        import numpy as np
        from andor_qt.windows.ta_panel import TAWindowPanel

        def _mock_get_wl(hbin=1):
            return np.linspace(400, 800, 1600 // hbin)
        mock_hw_manager.get_wavelengths.side_effect = _mock_get_wl

        panel = TAWindowPanel(hw_manager=mock_hw_manager)
        panel._pre_set_wavelengths({"hbin": 8})

        mock_hw_manager.get_wavelengths.assert_called_with(hbin=8)
        assert len(panel._live_display._wavelengths) == 200
        panel.deleteLater()
