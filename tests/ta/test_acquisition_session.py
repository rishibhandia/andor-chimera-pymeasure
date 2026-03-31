"""Tests for AcquisitionSession context manager.

Verifies camera lifecycle, delegation to mode-specific acquisition,
and correct interaction with phase reader.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from andor_qt.ta.nidaq_phase import MockNIDAQChopper2x2Reader, MockNIDAQPhaseReader
from andor_qt.ta.scan_config import TAScanConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(mode: str = "chopper_2x2", n_averages: int = 3,
                 shots_per_frame: int = 2) -> TAScanConfig:
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=n_averages,
        acquisition_mode=mode,
        scan_direction="forward",
        sample_name="test",
        shots_per_frame=shots_per_frame,
    )


def _make_hw_chopper(on_val, off_val, n_pairs, n_pixels=5):
    """Mock hw_manager for chopper_2x2 — alternating ON/OFF frames."""
    hw = MagicMock()
    hw.motion_manager = None
    frames = []
    for _ in range(n_pairs):
        frames.append(np.full(n_pixels, on_val, dtype=float))
        frames.append(np.full(n_pixels, off_val, dtype=float))
    frame_array = np.array(frames)
    hw.camera.start_run_till_abort.return_value = None
    hw.camera.get_buffered_frames.return_value = (frame_array, len(frames))
    hw.camera.abort_acquisition.return_value = None
    return hw


def _make_hw_software(shot_values):
    """Mock hw_manager for software/boxcar mode."""
    hw = MagicMock()
    hw.motion_manager = None
    it = iter(shot_values)
    hw.camera.get_spectrum.side_effect = lambda: np.array(next(it), dtype=float)
    return hw


# ---------------------------------------------------------------------------
# chopper_2x2 mode
# ---------------------------------------------------------------------------


class TestAcquisitionSessionChopper2x2:

    def test_enter_starts_camera_and_phase_reader(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        hw = _make_hw_chopper(1200, 1000, n_pairs=5)
        reader = MagicMock()
        reader.read_tags.return_value = np.array([1, 1, 0, 0] * 5, dtype=np.int8)
        config = _make_config("chopper_2x2")

        with AcquisitionSession(hw, config, phase_reader=reader):
            hw.camera.start_run_till_abort.assert_called_once()
            reader.start.assert_called_once()
            reader.drain.assert_called_once()

    def test_exit_stops_camera(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        hw = _make_hw_chopper(1200, 1000, n_pairs=5)
        reader = MockNIDAQChopper2x2Reader()
        config = _make_config("chopper_2x2")

        with AcquisitionSession(hw, config, phase_reader=reader):
            pass
        hw.camera.abort_acquisition.assert_called_once()

    def test_exit_stops_camera_on_exception(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        hw = _make_hw_chopper(1200, 1000, n_pairs=5)
        reader = MockNIDAQChopper2x2Reader()
        config = _make_config("chopper_2x2")

        with pytest.raises(ValueError):
            with AcquisitionSession(hw, config, phase_reader=reader):
                raise ValueError("test error")
        hw.camera.abort_acquisition.assert_called_once()

    def test_camera_not_restarted_between_cycles(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        hw = _make_hw_chopper(1200, 1000, n_pairs=10)
        reader = MockNIDAQChopper2x2Reader()
        config = _make_config("chopper_2x2", n_averages=3)

        with AcquisitionSession(hw, config, phase_reader=reader) as session:
            session.acquire_one_cycle()
            session.acquire_one_cycle()
            session.acquire_one_cycle()

        # Camera started exactly once, not per cycle
        assert hw.camera.start_run_till_abort.call_count == 1

    def test_acquire_one_cycle_returns_delta_signal(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        n = 5
        hw = _make_hw_chopper(1200, 1000, n_pairs=5)
        reader = MockNIDAQChopper2x2Reader()
        config = _make_config("chopper_2x2", n_averages=3)

        with AcquisitionSession(hw, config, phase_reader=reader) as session:
            result = session.acquire_one_cycle()

        assert isinstance(result, np.ndarray)
        assert result.shape == (n,)
        # (1200 - 1000) / 1000 = 0.2
        assert result.mean() > 0

    def test_acquire_reads_tags(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        hw = _make_hw_chopper(1200, 1000, n_pairs=5)
        reader = MagicMock()
        # Return alternating tags: [1,1,0,0,1,1,0,0,...] for spf=2
        n_frames = 10
        tags = np.array([1, 1, 0, 0] * (n_frames // 2), dtype=np.int8)[:n_frames * 2]
        reader.read_tags.return_value = tags
        reader.drain.return_value = None
        config = _make_config("chopper_2x2", n_averages=3, shots_per_frame=2)

        with AcquisitionSession(hw, config, phase_reader=reader) as session:
            session.acquire_one_cycle()

        reader.read_tags.assert_called()
        # Should read n_chunk * spf tags
        call_args = reader.read_tags.call_args[0]
        assert call_args[0] == n_frames * 2  # n_chunk * spf

    def test_acquire_with_dark_subtraction(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        n = 5
        hw = _make_hw_chopper(1200, 1000, n_pairs=5)
        reader = MockNIDAQChopper2x2Reader()
        config = _make_config("chopper_2x2", n_averages=3)
        dark = np.full(n, 100.0)

        with AcquisitionSession(hw, config, phase_reader=reader) as session:
            result = session.acquire_one_cycle(dark=dark)

        assert isinstance(result, np.ndarray)
        # With dark: (1200-100 - (1000-100)) / (1000-100) = 200/900 ≈ 0.222
        assert abs(result.mean() - 200.0 / 900.0) < 0.05

    def test_acquire_with_raw_callback(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        hw = _make_hw_chopper(1200, 1000, n_pairs=5)
        reader = MockNIDAQChopper2x2Reader()
        config = _make_config("chopper_2x2", n_averages=3)

        captured = {}

        def cb(pumped, ref, n_matched, n_discarded, n_frames):
            captured["pumped"] = pumped
            captured["ref"] = ref
            captured["n_matched"] = n_matched

        with AcquisitionSession(hw, config, phase_reader=reader) as session:
            session.acquire_one_cycle(raw_callback=cb)

        assert "pumped" in captured
        assert captured["n_matched"] >= 1

    def test_applies_camera_settings_on_enter(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        hw = _make_hw_chopper(1200, 1000, n_pairs=5)
        reader = MockNIDAQChopper2x2Reader()
        config = _make_config("chopper_2x2")
        settings = {"trigger_mode": "fast_external", "exposure_time": 0.0004}

        with AcquisitionSession(hw, config, camera_settings=settings,
                                phase_reader=reader):
            pass

        hw.camera.apply_camera_settings.assert_called_once_with(settings)

    def test_zero_frames_raises(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        hw = MagicMock()
        hw.motion_manager = None
        hw.camera.start_run_till_abort.return_value = None
        hw.camera.get_buffered_frames.return_value = (np.array([]), 0)
        hw.camera.abort_acquisition.return_value = None
        reader = MockNIDAQChopper2x2Reader()
        config = _make_config("chopper_2x2", n_averages=1)

        with AcquisitionSession(hw, config, phase_reader=reader) as session:
            with pytest.raises(RuntimeError, match="no frames"):
                session.acquire_one_cycle()


# ---------------------------------------------------------------------------
# software/boxcar mode
# ---------------------------------------------------------------------------


class TestAcquisitionSessionSoftware:

    def test_enter_does_not_start_rta(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        shots = [[1200, 1000, 800], [1000, 900, 700]] * 3
        hw = _make_hw_software(shots)
        config = _make_config("boxcar", n_averages=3)

        with AcquisitionSession(hw, config):
            pass

        hw.camera.start_run_till_abort.assert_not_called()

    def test_exit_does_not_call_abort(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        shots = [[1200, 1000, 800], [1000, 900, 700]] * 3
        hw = _make_hw_software(shots)
        config = _make_config("boxcar", n_averages=3)

        with AcquisitionSession(hw, config):
            pass

        hw.camera.abort_acquisition.assert_not_called()

    def test_acquire_one_cycle_returns_delta(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        # 3 averages × 2 shots each = 6 spectra
        shots = [[1200, 1000, 800], [1000, 900, 700]] * 3
        hw = _make_hw_software(shots)
        config = _make_config("boxcar", n_averages=3)

        with AcquisitionSession(hw, config) as session:
            result = session.acquire_one_cycle()

        assert isinstance(result, np.ndarray)
        assert result.shape == (3,)

    def test_applies_camera_settings_on_enter(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        shots = [[100], [90]] * 2
        hw = _make_hw_software(shots)
        config = _make_config("boxcar", n_averages=2)
        settings = {"trigger_mode": "internal"}

        with AcquisitionSession(hw, config, camera_settings=settings):
            pass

        hw.camera.apply_camera_settings.assert_called_once_with(settings)


# ---------------------------------------------------------------------------
# shot_to_shot mode
# ---------------------------------------------------------------------------


class TestAcquisitionSessionShotToShot:

    def test_shot_to_shot_delegates(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        n = 4
        hw = MagicMock()
        hw.motion_manager = None
        # Build alternating ON/OFF frames
        frames = np.ones((10, n)) * 1000.0
        hw.camera.start_run_till_abort_crop.return_value = None
        hw.camera._current_hbin = 1
        hw.camera.get_buffered_frames.return_value = (frames, 10)
        hw.camera.abort_acquisition.return_value = None

        reader = MockNIDAQPhaseReader()
        config = _make_config("shot_to_shot", n_averages=3)

        with AcquisitionSession(hw, config, phase_reader=reader) as session:
            result = session.acquire_one_cycle()

        assert isinstance(result, np.ndarray)
        assert result.shape == (n,)

    def test_shot_to_shot_no_phase_reader_falls_back(self):
        """Without phase_reader, shot_to_shot should fall back to software mode."""
        from andor_qt.ta.acquisition import AcquisitionSession

        shots = [[1200, 1000], [1000, 900]] * 3
        hw = _make_hw_software(shots)
        config = _make_config("shot_to_shot", n_averages=3)

        with AcquisitionSession(hw, config, phase_reader=None) as session:
            result = session.acquire_one_cycle()

        assert isinstance(result, np.ndarray)


# ---------------------------------------------------------------------------
# Context manager protocol
# ---------------------------------------------------------------------------


class TestAcquisitionSessionProtocol:

    def test_context_manager_returns_self(self):
        from andor_qt.ta.acquisition import AcquisitionSession

        shots = [[100], [90]]
        hw = _make_hw_software(shots)
        config = _make_config("boxcar", n_averages=1)

        with AcquisitionSession(hw, config) as session:
            from andor_qt.ta.acquisition import AcquisitionSession as Cls
            assert isinstance(session, Cls)

    def test_no_phase_reader_for_chopper_falls_back_to_software(self):
        """chopper_2x2 without phase_reader should fall back to software mode."""
        from andor_qt.ta.acquisition import AcquisitionSession

        shots = [[1200, 1000], [1000, 900]] * 3
        hw = _make_hw_software(shots)
        config = _make_config("chopper_2x2", n_averages=3)

        with AcquisitionSession(hw, config, phase_reader=None) as session:
            result = session.acquire_one_cycle()

        assert isinstance(result, np.ndarray)
        # Should NOT have started RTA since there's no phase reader
        hw.camera.start_run_till_abort.assert_not_called()
