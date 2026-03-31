"""Tests for hardware-mode (NI DAQ) acquisition via acquire_delta_signal_at_delay.

Uses MockNIDAQPhaseReader and mock hardware — no real NI DAQ or camera needed.
"""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

import numpy as np
import pytest

from andor_qt.ta.acquisition import acquire_delta_signal_at_delay
from andor_qt.ta.nidaq_phase import MockNIDAQChopper2x2Reader, MockNIDAQPhaseReader
from andor_qt.ta.scan_config import TAScanConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_hw(shot_values):
    """Make a mock hw_manager whose camera returns shot_values in order."""
    hw = MagicMock()
    hw.motion.get_axis.return_value = MagicMock()
    it = iter(shot_values)
    hw.camera.get_spectrum.side_effect = lambda: np.array(next(it), dtype=float)
    return hw


def make_config(n_averages=1):
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=n_averages,
        acquisition_mode="boxcar",
        scan_direction="forward",
        sample_name="test",
        nidaq_device="Dev1",
        nidaq_di_channel="port0/line0",
        nidaq_clock_source="/Dev1/PFI0",
        nidaq_clock_rate=1000.0,
    )


# ---------------------------------------------------------------------------
# TAScanConfig has nidaq fields
# ---------------------------------------------------------------------------


class TestTAScanConfigNIDAQFields:
    def test_has_nidaq_device(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_device")

    def test_has_nidaq_di_channel(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_di_channel")

    def test_has_nidaq_clock_source(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_clock_source")

    def test_has_nidaq_clock_rate(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_clock_rate")

    def test_defaults(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert cfg.nidaq_device == "Astrella_DAQ"
        assert cfg.nidaq_di_channel == "port0/line0"
        assert cfg.nidaq_clock_source == "/Astrella_DAQ/PFI0"
        assert cfg.nidaq_clock_rate == 1000.0

    def test_yaml_roundtrip_preserves_nidaq_fields(self, tmp_path):
        cfg = TAScanConfig(
            delay_list=[1.0],
            nidaq_device="Dev2",
            nidaq_di_channel="port0/line3",
            nidaq_clock_source="/Dev2/PFI1",
            nidaq_clock_rate=500.0,
        )
        path = tmp_path / "cfg.yaml"
        cfg.to_yaml(path)
        loaded = TAScanConfig.from_yaml(path)
        assert loaded.nidaq_device == "Dev2"
        assert loaded.nidaq_di_channel == "port0/line3"
        assert loaded.nidaq_clock_source == "/Dev2/PFI1"
        assert loaded.nidaq_clock_rate == 500.0


# ---------------------------------------------------------------------------
# acquire_delta_signal_at_delay with hardware phase reader
# ---------------------------------------------------------------------------


class TestAcquireSoftwareFallback:
    """Tests for boxcar (software alternation) acquisition mode."""

    def test_no_phase_reader_uses_software_mode(self):
        """Passing phase_reader=None uses software alternation (boxcar)."""
        n = 8
        hw = make_hw([[1000.0] * n, [1000.0] * n])
        cfg = make_config(n_averages=1)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=None)
        assert isinstance(result, np.ndarray)
        assert len(result) == n

    def test_correct_delta_signal(self):
        """Boxcar ΔI/I₀ should equal (pump - ref) / ref."""
        n = 5
        on_val, off_val = 1200.0, 1000.0
        hw = make_hw([[on_val] * n, [off_val] * n])
        cfg = make_config(n_averages=1)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=None)
        expected = (on_val - off_val) / off_val
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_multiple_averages(self):
        """Multiple pairs should be averaged."""
        n = 4
        shots = []
        for _ in range(3):
            shots.append([1200.0] * n)  # pump
            shots.append([1000.0] * n)  # ref
        hw = make_hw(shots)
        cfg = make_config(n_averages=3)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=None)
        expected = (1200.0 - 1000.0) / 1000.0
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_dark_subtraction_applied(self):
        """Dark frame should be subtracted from both pump and ref."""
        n = 5
        on_val, off_val, dark_val = 1200.0, 1000.0, 100.0
        hw = make_hw([[on_val] * n, [off_val] * n])
        cfg = make_config(n_averages=1)
        dark = np.ones(n) * dark_val
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, dark=dark, phase_reader=None)
        expected = ((on_val - dark_val) - (off_val - dark_val)) / (off_val - dark_val)
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_raw_callback_called_with_separate_pump_ref(self):
        """raw_callback must receive distinct pump and ref averages."""
        n = 5
        on_val, off_val = 1200.0, 1000.0
        hw = make_hw([[on_val] * n, [off_val] * n])
        cfg = make_config(n_averages=1)
        captured = {}

        def _cb(pump, ref, n_matched, n_discarded, n_frames):
            captured["pump"] = pump.copy()
            captured["ref"] = ref.copy()

        acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=None, raw_callback=_cb)
        assert "pump" in captured, "raw_callback was not called"
        np.testing.assert_allclose(captured["pump"], on_val, rtol=1e-6)
        np.testing.assert_allclose(captured["ref"], off_val, rtol=1e-6)
        assert not np.array_equal(captured["pump"], captured["ref"]), \
            "Pump and ref must be different arrays"

    def test_stats_populated_as_arrays(self):
        """last_acquisition_stats should contain per-pixel arrays."""
        from andor_qt.ta.acquisition import last_acquisition_stats
        n = 5
        hw = make_hw([[1200.0] * n, [1000.0] * n])
        cfg = make_config(n_averages=1)
        acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=None)
        assert "pump_mean" in last_acquisition_stats
        assert "ref_mean" in last_acquisition_stats
        pump = last_acquisition_stats["pump_mean"]
        ref = last_acquisition_stats["ref_mean"]
        assert isinstance(pump, np.ndarray), "pump_mean should be an array"
        assert len(pump) == n
        np.testing.assert_allclose(pump, 1200.0, rtol=1e-4)
        np.testing.assert_allclose(ref, 1000.0, rtol=1e-4)

    def test_stats_cleared_before_acquisition(self):
        """Stats from a previous call should not leak into the next."""
        from andor_qt.ta.acquisition import last_acquisition_stats
        last_acquisition_stats["stale_key"] = "should_be_gone"
        n = 5
        hw = make_hw([[1000.0] * n, [1000.0] * n])
        cfg = make_config(n_averages=1)
        acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=None)
        assert "stale_key" not in last_acquisition_stats

    def test_no_motion_manager_does_not_crash(self):
        """Should work without a motion controller."""
        n = 5
        hw = MagicMock()
        hw.motion_manager = None
        hw.camera.get_spectrum.side_effect = [
            np.ones(n) * 1200.0,
            np.ones(n) * 1000.0,
        ]
        cfg = make_config(n_averages=1)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=None)
        assert isinstance(result, np.ndarray)
        assert len(result) == n

    def test_camera_settings_applied(self):
        """camera_settings dict should be passed to apply_camera_settings."""
        n = 5
        hw = MagicMock()
        hw.motion_manager = None
        hw.camera.get_spectrum.side_effect = [
            np.ones(n) * 1200.0,
            np.ones(n) * 1000.0,
        ]
        settings = {"trigger_mode": "internal", "exposure_time": 0.01}
        cfg = make_config(n_averages=1)
        acquire_delta_signal_at_delay(
            0.0, hw, cfg, phase_reader=None, camera_settings=settings,
        )
        hw.camera.apply_camera_settings.assert_called_once_with(settings)


# ---------------------------------------------------------------------------
# chopper_2x2 acquisition
# ---------------------------------------------------------------------------


def make_config_2x2(n_averages=1):
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=n_averages,
        acquisition_mode="chopper_2x2",
        scan_direction="forward",
        sample_name="test",
    )


def make_hw_2x2(on_val, off_val, n_pairs):
    """Camera alternates ON frame / OFF frame for n_pairs pairs.

    Mocks batch-read methods for chopper_2x2 acquisition.
    """
    hw = MagicMock()
    hw.motion.get_axis.return_value = MagicMock()
    # Build alternating ON/OFF frames as 2-D array
    frames = []
    for _ in range(n_pairs):
        frames.append(np.array(on_val, dtype=float))
        frames.append(np.array(off_val, dtype=float))
    frame_array = np.array(frames)
    hw.camera.start_run_till_abort.return_value = None
    hw.camera.get_buffered_frames.return_value = (frame_array, len(frames))
    hw.camera.abort_acquisition.return_value = None
    return hw


class TestAcquireChopper2x2:
    def test_returns_ndarray(self):
        n = 10
        hw = make_hw_2x2([1000.0] * n, [800.0] * n, n_pairs=1)
        cfg = make_config_2x2(n_averages=1)
        reader = MockNIDAQChopper2x2Reader()
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        assert isinstance(result, np.ndarray)
        assert len(result) == n

    def test_correct_delta_signal(self):
        n = 5
        on_val, off_val = 1200.0, 1000.0
        hw = make_hw_2x2([on_val] * n, [off_val] * n, n_pairs=1)
        cfg = make_config_2x2(n_averages=1)
        reader = MockNIDAQChopper2x2Reader(initial_phase=1)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        expected = (on_val - off_val) / off_val
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_n_averages_pairs_collected(self):
        n = 4
        hw = make_hw_2x2([1200.0] * n, [1000.0] * n, n_pairs=3)
        cfg = make_config_2x2(n_averages=3)
        reader = MockNIDAQChopper2x2Reader()
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        # Batch read: get_buffered_frames called once
        assert hw.camera.get_buffered_frames.call_count >= 1

    def test_mixed_tags_discarded(self):
        """A reader that always returns mixed tags should yield 0 valid pairs."""
        n = 4
        n_frames = 10

        class AllMixedReader:
            def start(self, **kwargs): pass
            def stop(self): pass
            def drain(self): pass
            def read_tags(self, k):
                # Alternating 1,0,1,0... — neither offset gives matched pairs
                return np.array([1, 0] * (k // 2) + [1] * (k % 2), dtype=np.int8)[:k]

        frame_array = np.ones((n_frames, n)) * 1000.0
        hw = MagicMock()
        hw.motion.get_axis.return_value = MagicMock()
        hw.camera.start_run_till_abort.return_value = None
        hw.camera.get_buffered_frames.return_value = (frame_array, n_frames)
        hw.camera.abort_acquisition.return_value = None

        cfg = make_config_2x2(n_averages=1)
        with pytest.raises(RuntimeError, match="chopper_2x2"):
            acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=AllMixedReader())

    def test_off_first_phase_still_correct(self):
        """initial_phase=0 means OFF frame arrives first."""
        n = 5
        on_val, off_val = 1200.0, 1000.0
        # OFF frame first, then ON frame
        hw = make_hw_2x2([off_val] * n, [on_val] * n, n_pairs=1)
        cfg = make_config_2x2(n_averages=1)
        reader = MockNIDAQChopper2x2Reader(initial_phase=0)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        expected = (on_val - off_val) / off_val
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_dark_subtraction_applied(self):
        n = 6
        on_val, off_val, dark_val = 1200.0, 1000.0, 100.0
        hw = make_hw_2x2([on_val] * n, [off_val] * n, n_pairs=1)
        cfg = make_config_2x2(n_averages=1)
        reader = MockNIDAQChopper2x2Reader()
        dark = np.ones(n) * dark_val
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, dark=dark, phase_reader=reader)
        expected = (on_val - dark_val - (off_val - dark_val)) / (off_val - dark_val)
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_raw_callback_called(self):
        """chopper_2x2 should invoke raw_callback at least once."""
        n = 5
        hw = make_hw_2x2([1200.0] * n, [1000.0] * n, n_pairs=2)
        cfg = make_config_2x2(n_averages=2)
        reader = MockNIDAQChopper2x2Reader()
        captured = {}

        def _cb(pump, ref, n_matched, n_discarded, n_frames):
            captured["called"] = True
            captured["n_matched"] = n_matched

        acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader, raw_callback=_cb)
        assert captured.get("called"), "raw_callback was not invoked"
        assert captured["n_matched"] >= 1

    def test_zero_frames_raises(self):
        """chopper_2x2: camera returning 0 frames should raise RuntimeError."""
        n = 5
        hw = MagicMock()
        hw.motion_manager = None
        hw.camera.start_run_till_abort.return_value = None
        hw.camera.get_buffered_frames.return_value = (np.array([]), 0)
        hw.camera.abort_acquisition.return_value = None
        cfg = make_config_2x2(n_averages=1)
        reader = MockNIDAQChopper2x2Reader()
        with pytest.raises(RuntimeError, match="chopper_2x2"):
            acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)

    def test_shot_to_shot_raw_callback_called(self):
        """shot_to_shot should also call raw_callback."""
        n = 5
        hw = make_hw_s2s([1200.0] * n, [1000.0] * n, n_pairs=1)
        cfg = make_config_s2s(n_averages=1)
        reader = MockNIDAQPhaseReader()
        captured = {}

        def _cb(pump, ref, n_matched, n_discarded, n_frames):
            captured["pump"] = pump.copy()
            captured["ref"] = ref.copy()

        acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader, raw_callback=_cb)
        assert "pump" in captured
        assert not np.array_equal(captured["pump"], captured["ref"])


# ---------------------------------------------------------------------------
# shot_to_shot acquisition mode
# ---------------------------------------------------------------------------


def make_config_s2s(n_averages=1):
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=n_averages,
        acquisition_mode="shot_to_shot",
        scan_direction="forward",
        sample_name="test",
        crop_height=50,
    )


def make_hw_s2s(on_val, off_val, n_pairs):
    """Camera alternates ON/OFF frames for shot_to_shot (1 frame per shot)."""
    hw = MagicMock()
    hw.motion.get_axis.return_value = MagicMock()
    frames = []
    for _ in range(n_pairs):
        frames.append(np.array(on_val, dtype=float))
        frames.append(np.array(off_val, dtype=float))
    frame_array = np.array(frames)
    hw.camera.start_run_till_abort_crop.return_value = None
    hw.camera._current_hbin = 1
    hw.camera.get_buffered_frames.return_value = (frame_array, len(frames))
    hw.camera.abort_acquisition.return_value = None
    return hw


class TestAcquireShotToShot:
    def test_returns_ndarray(self):
        n = 10
        hw = make_hw_s2s([1000.0] * n, [800.0] * n, n_pairs=1)
        cfg = make_config_s2s(n_averages=1)
        reader = MockNIDAQPhaseReader()
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        assert isinstance(result, np.ndarray)
        assert len(result) == n

    def test_correct_delta_signal(self):
        n = 5
        on_val, off_val = 1200.0, 1000.0
        hw = make_hw_s2s([on_val] * n, [off_val] * n, n_pairs=1)
        cfg = make_config_s2s(n_averages=1)
        reader = MockNIDAQPhaseReader()
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        expected = (on_val - off_val) / off_val
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_n_averages_pairs_collected(self):
        n = 4
        hw = make_hw_s2s([1200.0] * n, [1000.0] * n, n_pairs=3)
        cfg = make_config_s2s(n_averages=3)
        reader = MockNIDAQPhaseReader()
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        assert hw.camera.get_buffered_frames.call_count >= 1

    def test_all_same_tag_raises(self):
        n = 4

        class AllOnReader:
            def start(self): pass
            def stop(self): pass
            def drain(self): pass
            def read_tags(self, k):
                return np.ones(k, dtype=np.int8)

        frame_array = np.ones((10, n)) * 1000.0
        hw = MagicMock()
        hw.motion.get_axis.return_value = MagicMock()
        hw.camera.start_run_till_abort_crop.return_value = None
        hw.camera._current_hbin = 1
        hw.camera.get_buffered_frames.return_value = (frame_array, 10)
        hw.camera.abort_acquisition.return_value = None

        cfg = make_config_s2s(n_averages=1)
        with pytest.raises(RuntimeError, match="shot_to_shot"):
            acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=AllOnReader())

    def test_dark_subtraction_applied(self):
        n = 6
        on_val, off_val, dark_val = 1200.0, 1000.0, 100.0
        hw = make_hw_s2s([on_val] * n, [off_val] * n, n_pairs=1)
        cfg = make_config_s2s(n_averages=1)
        reader = MockNIDAQPhaseReader()
        dark = np.ones(n) * dark_val
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, dark=dark, phase_reader=reader)
        expected = (on_val - dark_val - (off_val - dark_val)) / (off_val - dark_val)
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_zero_frames_raises(self):
        """shot_to_shot: camera returning 0 frames should raise RuntimeError."""
        n = 5
        hw = MagicMock()
        hw.motion_manager = None
        hw.camera.start_run_till_abort_crop.return_value = None
        hw.camera._current_hbin = 1
        hw.camera.get_buffered_frames.return_value = (np.array([]), 0)
        hw.camera.abort_acquisition.return_value = None
        cfg = make_config_s2s(n_averages=1)
        reader = MockNIDAQPhaseReader()
        with pytest.raises(RuntimeError, match="shot_to_shot"):
            acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)

    def test_frames_with_empty_tags_raises(self):
        """shot_to_shot: frames exist but 0 aligned tags should raise."""
        n = 5

        class EmptyTagReader:
            def start(self): pass
            def stop(self): pass
            def drain(self): pass
            def read_tags(self, k):
                return np.array([], dtype=np.int8)

        hw = MagicMock()
        hw.motion_manager = None
        hw.camera.start_run_till_abort_crop.return_value = None
        hw.camera._current_hbin = 1
        hw.camera.get_buffered_frames.return_value = (np.ones((10, n)), 10)
        hw.camera.abort_acquisition.return_value = None
        cfg = make_config_s2s(n_averages=1)
        with pytest.raises(RuntimeError, match="shot_to_shot"):
            acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=EmptyTagReader())


# ---------------------------------------------------------------------------
# TAScanConfig — chopper_2x2 NI DAQ fields
# ---------------------------------------------------------------------------


class TestAcquireStaticAtDelay:
    """Tests for acquire_static_at_delay (bulk frame averaging for static mode)."""

    def _make_hw(self, frame_shape=(100,), n_return=50):
        hw = MagicMock()
        hw.motion_manager = MagicMock()
        hw.motion_manager.get_axis.return_value = MagicMock()
        hw.camera.get_circular_buffer_size.return_value = 12000
        frames = np.random.rand(n_return, *frame_shape).astype(np.float32) * 1000
        hw.camera.get_buffered_frames.return_value = (frames, n_return)
        hw.camera.start_run_till_abort.return_value = None
        hw.camera.abort_acquisition.return_value = None
        return hw, frames

    def test_returns_mean_std_count(self):
        import threading
        from andor_qt.ta.acquisition import acquire_static_at_delay
        hw, _ = self._make_hw(n_return=50)
        mean, std, count = acquire_static_at_delay(
            hw, 50, threading.Event(),
        )
        assert isinstance(mean, np.ndarray)
        assert isinstance(std, np.ndarray)
        assert count == 50

    def test_applies_camera_settings(self):
        import threading
        from andor_qt.ta.acquisition import acquire_static_at_delay
        hw, _ = self._make_hw()
        settings = {"trigger_mode": "internal", "exposure_time": 0.002}
        acquire_static_at_delay(hw, 50, threading.Event(), camera_settings=settings)
        hw.camera.apply_camera_settings.assert_called_once_with(settings)

    def test_dark_subtraction_applied(self):
        import threading
        from andor_qt.ta.acquisition import acquire_static_at_delay
        n = 100
        hw = MagicMock()
        frames = np.ones((50, n)) * 1000.0
        hw.camera.get_circular_buffer_size.return_value = 12000
        hw.camera.get_buffered_frames.return_value = (frames, 50)
        hw.camera.start_run_till_abort.return_value = None
        hw.camera.abort_acquisition.return_value = None
        dark = np.ones(n) * 200.0
        mean, _, _ = acquire_static_at_delay(
            hw, 50, threading.Event(), dark=dark,
        )
        np.testing.assert_allclose(mean, 800.0, rtol=1e-6)

    def test_stats_populated_as_arrays(self):
        import threading
        from andor_qt.ta.acquisition import acquire_static_at_delay, last_acquisition_stats
        hw, _ = self._make_hw()
        acquire_static_at_delay(hw, 50, threading.Event())
        assert "pump_mean" in last_acquisition_stats
        assert isinstance(last_acquisition_stats["pump_mean"], np.ndarray)
        assert last_acquisition_stats["n_on"] == 50

    def test_progress_callback_called(self):
        import threading
        from andor_qt.ta.acquisition import acquire_static_at_delay
        hw, _ = self._make_hw()
        calls = []
        def _cb(running_mean, collected, n_target):
            calls.append(collected)
        acquire_static_at_delay(hw, 50, threading.Event(), progress_cb=_cb)
        assert len(calls) >= 1


class TestTAScanConfigChopper2x2Fields:
    def test_has_nidaq_chopper_sync_source(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_chopper_sync_source")

    def test_has_nidaq_chopper_counter(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_chopper_counter")

    def test_default_sync_source(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert "PFI12" in cfg.nidaq_chopper_sync_source

    def test_default_counter(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert cfg.nidaq_chopper_counter == "ctr1"

    def test_yaml_roundtrip_chopper_fields(self, tmp_path):
        cfg = TAScanConfig(
            delay_list=[1.0],
            nidaq_chopper_sync_source="/Dev2/PFI5",
            nidaq_chopper_counter="ctr0",
        )
        path = tmp_path / "cfg.yaml"
        cfg.to_yaml(path)
        loaded = TAScanConfig.from_yaml(path)
        assert loaded.nidaq_chopper_sync_source == "/Dev2/PFI5"
        assert loaded.nidaq_chopper_counter == "ctr0"
