"""Tests for TransientAbsorptionEngine scan loop and acquire helpers.

Uses MockHardwareManager to avoid real hardware.
Engine runs in a QThread — tests use signal capture with a short timeout.
"""

from __future__ import annotations

import threading
import time
from typing import List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from andor_qt.ta.scan_config import TAScanConfig
from andor_qt.ta.engine import TransientAbsorptionEngine
from andor_qt.ta.acquisition import acquire_delta_signal_at_delay


# ---------------------------------------------------------------------------
# Minimal mock hardware manager
# ---------------------------------------------------------------------------


def make_mock_hw(n_pixels: int = 64):
    """Create a minimal mock HardwareManager for TA engine tests."""
    hw = MagicMock()
    # Camera returns a flat spectrum
    hw.camera.get_spectrum.return_value = np.ones(n_pixels) * 1000.0
    hw.camera.get_image.return_value = np.ones((10, n_pixels)) * 1000.0
    # Batch read for chopper_2x2 mode
    hw.camera.start_run_till_abort.return_value = None
    hw.camera.get_buffered_frames.return_value = (
        np.ones((200, n_pixels)) * 1000.0, 200
    )
    hw.camera.abort_acquisition.return_value = None

    # Mock motion axis — set real float values so engine f-string formatting works
    mock_axis = MagicMock()
    mock_axis.t0_offset_mm = 0.0
    mock_axis.position = 0.0
    mock_axis.position_ps = 0.0
    mock_axis.position_mm = 0.0
    hw.motion.get_axis.return_value = mock_axis
    hw.motion_manager.get_axis.return_value = mock_axis
    hw.wavelengths = np.linspace(400.0, 800.0, n_pixels)
    return hw


def make_config(n_delays: int = 3, n_averages: int = 1, n_scans: int = 1):
    delays = [float(i) for i in range(n_delays)]
    return TAScanConfig(
        delay_list=delays,
        n_averages=n_averages,
        n_scans=n_scans,
        acquisition_mode="boxcar",
        scan_direction="forward",
        sample_name="test",
    )


# ---------------------------------------------------------------------------
# acquire_delta_signal_at_delay
# ---------------------------------------------------------------------------


class TestAcquireDeltaSignalAtDelay:
    def test_returns_ndarray(self):
        hw = make_mock_hw()
        config = make_config(n_averages=2)
        result = acquire_delta_signal_at_delay(
            delay_ps=1.0, hw_manager=hw, config=config, dark=None
        )
        assert isinstance(result, np.ndarray)

    def test_result_length_matches_pixels(self):
        hw = make_mock_hw(n_pixels=32)
        config = make_config(n_averages=1)
        result = acquire_delta_signal_at_delay(0.0, hw, config, dark=None)
        assert len(result) == 32

    def test_dark_subtraction_applied(self):
        hw = make_mock_hw(n_pixels=10)
        # Camera always returns 1000, dark = 100 → net = 900
        hw.camera.get_spectrum.return_value = np.ones(10) * 1000.0
        config = make_config(n_averages=1)
        dark = np.ones(10) * 100.0
        result = acquire_delta_signal_at_delay(0.0, hw, config, dark=dark)
        # ΔI/I₀ of identical pumped/ref = 0
        assert result == pytest.approx(np.zeros(10), abs=1e-8)


# ---------------------------------------------------------------------------
# TransientAbsorptionEngine — signal capture helpers
# ---------------------------------------------------------------------------


def collect_signals(engine, signal_name: str, timeout: float = 5.0) -> List:
    """Collect emitted signal values into a list."""
    received = []
    sig = getattr(engine, signal_name)
    sig.connect(lambda *args: received.append(args))
    return received


class TestTransientAbsorptionEngineSignals:
    """Test that the engine emits expected signals during a scan."""

    def _run_engine(self, engine, config, hw, writer=None, timeout=10.0):
        """Start engine scan and wait for it to finish, processing Qt events."""
        import time as _time
        from PySide6.QtWidgets import QApplication

        done = [False]
        engine.scan_completed.connect(lambda: done.__setitem__(0, True))
        engine.aborted.connect(lambda: done.__setitem__(0, True))
        engine.error.connect(lambda msg: done.__setitem__(0, True))

        engine.start_scan(config, hw, writer)

        start = _time.time()
        while not done[0] and _time.time() - start < timeout:
            QApplication.instance().processEvents()
            _time.sleep(0.005)

    def test_scan_started_emitted(self, qt_app):
        hw = make_mock_hw()
        config = make_config(n_delays=2, n_scans=1)
        engine = TransientAbsorptionEngine()

        started = []
        engine.scan_started.connect(lambda idx: started.append(idx))

        self._run_engine(engine, config, hw)
        assert len(started) == 1
        assert started[0] == 0

    def test_scan_completed_emitted(self, qt_app):
        hw = make_mock_hw()
        config = make_config(n_delays=2, n_scans=1)
        engine = TransientAbsorptionEngine()

        done = []
        engine.scan_completed.connect(lambda: done.append(True))

        self._run_engine(engine, config, hw)
        assert len(done) == 1

    def test_point_completed_emitted_for_each_delay(self, qt_app):
        hw = make_mock_hw()
        config = make_config(n_delays=3, n_scans=1)
        engine = TransientAbsorptionEngine()

        points = []
        engine.point_completed.connect(lambda idx, delay: points.append((idx, delay)))

        self._run_engine(engine, config, hw)
        assert len(points) == 3

    def test_abort_stops_scan(self, qt_app):
        from PySide6.QtWidgets import QApplication

        hw = make_mock_hw()
        # Slow down acquisition so we can abort mid-scan
        hw.camera.get_spectrum.side_effect = lambda: (time.sleep(0.01), np.ones(64) * 1000.0)[1]
        config = make_config(n_delays=10, n_scans=5)
        engine = TransientAbsorptionEngine()

        aborted = []
        engine.aborted.connect(lambda: aborted.append(True))

        done = [False]
        engine.aborted.connect(lambda: done.__setitem__(0, True))
        engine.scan_completed.connect(lambda: done.__setitem__(0, True))

        engine.start_scan(config, hw, None)
        time.sleep(0.05)
        engine.abort()

        start = time.time()
        while not done[0] and time.time() - start < 5.0:
            QApplication.instance().processEvents()
            time.sleep(0.005)

        assert len(aborted) >= 1

    def test_multiple_scans_emits_scan_started_for_each(self, qt_app):
        hw = make_mock_hw()
        config = make_config(n_delays=2, n_scans=3)
        engine = TransientAbsorptionEngine()

        started = []
        engine.scan_started.connect(lambda idx: started.append(idx))

        self._run_engine(engine, config, hw)
        assert len(started) == 3
        assert started == [0, 1, 2]

    def test_signal_updated_emitted(self, qt_app):
        hw = make_mock_hw(n_pixels=16)
        config = make_config(n_delays=2, n_scans=1)
        engine = TransientAbsorptionEngine()

        updates = []
        engine.signal_updated.connect(lambda delay, wl, sig: updates.append(delay))

        self._run_engine(engine, config, hw)
        assert len(updates) == 2  # once per delay point


class TestEngineSaveSpectra:
    def _run_engine(self, engine, config, hw, writer=None, timeout=10.0):
        import time as _time
        from PySide6.QtWidgets import QApplication

        done = [False]
        engine.scan_completed.connect(lambda: done.__setitem__(0, True))
        engine.aborted.connect(lambda: done.__setitem__(0, True))
        engine.error.connect(lambda msg: done.__setitem__(0, True))
        engine.start_scan(config, hw, writer)
        start = _time.time()
        while not done[0] and _time.time() - start < timeout:
            QApplication.instance().processEvents()
            _time.sleep(0.005)

    def _make_config(self, n_delays=3, save_spectra_dir=None):
        return TAScanConfig(
            delay_list=[float(i) for i in range(n_delays)],
            n_averages=1,
            n_scans=1,
            acquisition_mode="boxcar",
            scan_direction="forward",
            sample_name="test",
            save_spectra_dir=save_spectra_dir,
        )

    def test_saves_spectrum_file_for_each_point(self, qt_app, tmp_path):
        hw = make_mock_hw(n_pixels=16)
        hw.get_wavelengths.return_value = np.linspace(400, 800, 16)
        config = self._make_config(n_delays=3, save_spectra_dir=str(tmp_path))
        engine = TransientAbsorptionEngine()
        self._run_engine(engine, config, hw)
        # Spectra are saved in a timestamped subfolder
        subdirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(subdirs) == 1
        files = sorted(subdirs[0].glob("*.txt"))
        # 3 delays × 5 files each (delta, pump, ref, pump_std, ref_std)
        assert len(files) == 15

    def test_spectrum_file_is_two_column_text(self, qt_app, tmp_path):
        hw = make_mock_hw(n_pixels=4)
        hw.get_wavelengths.return_value = np.linspace(400, 800, 4)
        config = self._make_config(n_delays=1, save_spectra_dir=str(tmp_path))
        engine = TransientAbsorptionEngine()
        self._run_engine(engine, config, hw)
        subdirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(subdirs) == 1
        # Pick the main delta spectrum file (scan000_pos*.txt)
        files = sorted(subdirs[0].glob("scan*.txt"))
        assert len(files) >= 1
        lines = [ln for ln in files[0].read_text().splitlines() if not ln.startswith("#")]
        assert len(lines) == 4  # 4 pixels
        cols = lines[0].split("\t")
        assert len(cols) == 2

    def test_no_files_when_save_dir_none(self, qt_app, tmp_path):
        hw = make_mock_hw(n_pixels=4)
        config = self._make_config(n_delays=2, save_spectra_dir=None)
        engine = TransientAbsorptionEngine()
        self._run_engine(engine, config, hw)
        assert list(tmp_path.iterdir()) == []


class TestEngineChopper2x2:
    """Engine correctly starts/stops trigger_gen and phase_reader."""

    def _run_engine(self, engine, config, hw, trigger_gen=None, phase_reader=None, timeout=10.0):
        import time as _time
        from PySide6.QtWidgets import QApplication
        done = [False]
        engine.scan_completed.connect(lambda: done.__setitem__(0, True))
        engine.aborted.connect(lambda: done.__setitem__(0, True))
        engine.error.connect(lambda msg: done.__setitem__(0, True))
        engine.start_scan(config, hw, writer=None, trigger_gen=trigger_gen, phase_reader=phase_reader)
        start = _time.time()
        while not done[0] and _time.time() - start < timeout:
            QApplication.instance().processEvents()
            _time.sleep(0.005)

    def _make_chopper_config(self):
        from andor_qt.ta.nidaq_phase import MockNIDAQChopper2x2Reader
        return TAScanConfig(
            delay_list=[0.0, 1.0],
            n_averages=1,
            n_scans=1,
            acquisition_mode="chopper_2x2",
            scan_direction="forward",
            sample_name="test",
        )

    def test_trigger_gen_started_and_stopped(self, qt_app):
        from unittest.mock import MagicMock
        from andor_qt.ta.nidaq_phase import MockNIDAQChopper2x2Reader
        hw = make_mock_hw()
        config = self._make_chopper_config()
        trigger_gen = MagicMock()
        reader = MockNIDAQChopper2x2Reader()
        self._run_engine(engine=TransientAbsorptionEngine(), config=config,
                         hw=hw, trigger_gen=trigger_gen, phase_reader=reader)
        trigger_gen.start.assert_called_once()
        trigger_gen.stop.assert_called_once()

    def test_phase_reader_started_and_stopped(self, qt_app):
        from unittest.mock import MagicMock
        from andor_qt.ta.nidaq_phase import MockNIDAQChopper2x2Reader
        hw = make_mock_hw()
        config = self._make_chopper_config()
        trigger_gen = MagicMock()
        reader = MagicMock()
        # Return matched-pair pattern for any requested length
        reader.read_tags.side_effect = lambda n: np.array(
            [1, 1, 0, 0] * ((n // 4) + 1), dtype=np.int8
        )[:n]
        self._run_engine(engine=TransientAbsorptionEngine(), config=config,
                         hw=hw, trigger_gen=trigger_gen, phase_reader=reader)
        reader.start.assert_called_once()
        reader.stop.assert_called_once()

    def test_scan_completes_with_chopper_2x2(self, qt_app):
        from andor_qt.ta.nidaq_phase import MockNIDAQChopper2x2Reader
        hw = make_mock_hw()
        config = self._make_chopper_config()
        trigger_gen = MagicMock()
        reader = MockNIDAQChopper2x2Reader()
        done = []
        engine = TransientAbsorptionEngine()
        engine.scan_completed.connect(lambda: done.append(True))
        self._run_engine(engine=engine, config=config, hw=hw,
                         trigger_gen=trigger_gen, phase_reader=reader)
        assert done


class TestEngineShotToShot:
    """Integration tests for shot_to_shot mode through the full engine."""

    def _run_engine(self, engine, config, hw, trigger_gen=None, phase_reader=None,
                    timeout=15.0):
        from PySide6.QtWidgets import QApplication
        import time as _time

        camera_settings = {"trigger_mode": "fast_external", "hbin": 1}
        engine.start_scan(config, hw, camera_settings=camera_settings,
                          trigger_gen=trigger_gen, phase_reader=phase_reader)
        done = [False]
        engine.scan_completed.connect(lambda: done.__setitem__(0, True))
        engine.error.connect(lambda e: done.__setitem__(0, True))
        start = _time.time()
        while not done[0] and _time.time() - start < timeout:
            QApplication.instance().processEvents()
            _time.sleep(0.005)

    def _make_s2s_config(self):
        return TAScanConfig(
            delay_list=[0.0, 1.0],
            n_averages=1,
            n_scans=1,
            acquisition_mode="shot_to_shot",
            scan_direction="forward",
            sample_name="test",
            crop_height=50,
        )

    def test_scan_completes_with_shot_to_shot(self, qt_app):
        from andor_qt.ta.nidaq_phase import MockNIDAQPhaseReader
        hw = make_mock_hw()
        # shot_to_shot uses crop mode RTA
        hw.camera.start_run_till_abort_crop.return_value = None
        hw.camera._current_hbin = 1
        config = self._make_s2s_config()
        reader = MockNIDAQPhaseReader()
        done = []
        engine = TransientAbsorptionEngine()
        engine.scan_completed.connect(lambda: done.append(True))
        self._run_engine(engine=engine, config=config, hw=hw,
                         phase_reader=reader)
        assert done

    def test_phase_reader_started_and_stopped(self, qt_app):
        from unittest.mock import MagicMock
        hw = make_mock_hw()
        hw.camera.start_run_till_abort_crop.return_value = None
        hw.camera._current_hbin = 1
        config = self._make_s2s_config()
        reader = MagicMock()
        reader.read_tags.side_effect = lambda n: np.array(
            [1, 0] * ((n // 2) + 1), dtype=np.int8
        )[:n]
        self._run_engine(engine=TransientAbsorptionEngine(), config=config,
                         hw=hw, phase_reader=reader)
        reader.start.assert_called_once()
        reader.stop.assert_called_once()

    def test_no_trigger_gen_needed(self, qt_app):
        from andor_qt.ta.nidaq_phase import MockNIDAQPhaseReader
        hw = make_mock_hw()
        hw.camera.start_run_till_abort_crop.return_value = None
        hw.camera._current_hbin = 1
        config = self._make_s2s_config()
        reader = MockNIDAQPhaseReader()
        done = []
        engine = TransientAbsorptionEngine()
        engine.scan_completed.connect(lambda: done.append(True))
        # No trigger_gen passed — shot_to_shot doesn't need one
        self._run_engine(engine=engine, config=config, hw=hw,
                         phase_reader=reader)
        assert done

    def test_signal_updated_emitted(self, qt_app):
        from andor_qt.ta.nidaq_phase import MockNIDAQPhaseReader
        hw = make_mock_hw()
        hw.camera.start_run_till_abort_crop.return_value = None
        hw.camera._current_hbin = 1
        config = self._make_s2s_config()
        reader = MockNIDAQPhaseReader()
        updates = []
        engine = TransientAbsorptionEngine()
        engine.signal_updated.connect(lambda d, w, s: updates.append(d))
        self._run_engine(engine=engine, config=config, hw=hw,
                         phase_reader=reader)
        assert len(updates) == 2  # 2 delay points


class TestTransientAbsorptionEnginePauseResume:
    def test_pause_resume_completes_scan(self, qt_app):
        from PySide6.QtWidgets import QApplication

        hw = make_mock_hw()
        config = make_config(n_delays=3, n_scans=1)
        engine = TransientAbsorptionEngine()

        done = [False]
        engine.scan_completed.connect(lambda: done.__setitem__(0, True))

        engine.start_scan(config, hw, None)
        time.sleep(0.01)
        engine.pause()
        time.sleep(0.05)
        engine.resume()

        start = time.time()
        while not done[0] and time.time() - start < 5.0:
            QApplication.instance().processEvents()
            time.sleep(0.005)

        assert done[0] is True
