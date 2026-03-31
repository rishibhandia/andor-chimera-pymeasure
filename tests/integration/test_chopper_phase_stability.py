"""Integration test: chopper phase stability with Camera Fire trigger.

With the Camera Fire output on PFI13 as the phase reader's start trigger,
the tag-to-frame alignment should be deterministic across both continuous
sessions and camera restarts.

Run with::

    uv run pytest tests/integration/test_chopper_phase_stability.py --hardware -v
"""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.hardware

CAMERA_SETTINGS = {
    "trigger_mode": "fast_external",
    "exposure_time": 0.0004,
    "vs_speed_index": 0,
    "hs_speed_index": 0,
    "amplifier_type": 1,
    "preamp_gain_index": 0,
    "hbin": 1,
    "vbin": 1,
}

N_AVERAGES = 100
SHOTS_PER_FRAME = 2
N_TRIALS = 6


def _make_config():
    from andor_qt.ta.scan_config import TAScanConfig
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=N_AVERAGES,
        acquisition_mode="chopper_2x2",
        scan_direction="forward",
        sample_name="test",
        shots_per_frame=SHOTS_PER_FRAME,
    )


def _make_hw_manager(camera):
    from unittest.mock import MagicMock
    hw = MagicMock()
    hw.camera = camera
    hw.motion_manager = None
    return hw


class TestContinuousModeStability:
    """Camera stays running within one session — phase should never flip."""

    def test_phase_stable_across_trials(self, camera, phase_reader):
        from andor_qt.ta.acquisition import AcquisitionSession, last_acquisition_stats

        hw = _make_hw_manager(camera)
        config = _make_config()

        with AcquisitionSession(hw, config, camera_settings=CAMERA_SETTINGS,
                                phase_reader=phase_reader) as session:
            on_is_bright_list = []
            for _ in range(N_TRIALS):
                try:
                    session.acquire_one_cycle()
                except RuntimeError:
                    continue
                stats = last_acquisition_stats
                on_m = float(np.asarray(stats.get("pump_mean", [0])).mean())
                off_m = float(np.asarray(stats.get("ref_mean", [0])).mean())
                on_is_bright_list.append(on_m > off_m)

        assert len(on_is_bright_list) >= 4, "Too few valid trials"
        assert all(v == on_is_bright_list[0] for v in on_is_bright_list), (
            f"Phase flipped during continuous mode: {on_is_bright_list}"
        )


class TestRestartModeWithFireTrigger:
    """Camera restarts each trial — Fire trigger should keep phase stable."""

    def test_phase_stable_across_restarts(self, camera, phase_reader):
        """With Camera Fire start trigger, restarts should NOT flip phase."""
        from andor_qt.ta.acquisition import AcquisitionSession, last_acquisition_stats

        hw = _make_hw_manager(camera)
        config = _make_config()

        on_is_bright_list = []
        for _ in range(N_TRIALS):
            with AcquisitionSession(hw, config, camera_settings=CAMERA_SETTINGS,
                                    phase_reader=phase_reader) as session:
                try:
                    session.acquire_one_cycle()
                except RuntimeError:
                    continue
                stats = last_acquisition_stats
                on_m = float(np.asarray(stats.get("pump_mean", [0])).mean())
                off_m = float(np.asarray(stats.get("ref_mean", [0])).mean())
                on_is_bright_list.append(on_m > off_m)

        assert len(on_is_bright_list) >= 4
        assert all(v == on_is_bright_list[0] for v in on_is_bright_list), (
            f"Phase flipped across restarts: {on_is_bright_list}"
        )
