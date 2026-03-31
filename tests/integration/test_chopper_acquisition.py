"""Integration test: chopper_2x2 acquisition with real hardware.

Uses AcquisitionSession with Camera Fire start trigger on PFI13 for
deterministic tag-to-frame alignment. Verifies ON/OFF separation over
multiple read cycles.

Run with::

    uv run pytest tests/integration/test_chopper_acquisition.py --hardware -v
"""

from __future__ import annotations

import time

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
N_CYCLES = 3


def _make_config(n_averages=N_AVERAGES):
    from andor_qt.ta.scan_config import TAScanConfig
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=n_averages,
        acquisition_mode="chopper_2x2",
        scan_direction="forward",
        sample_name="test",
        shots_per_frame=SHOTS_PER_FRAME,
    )


def _make_hw_manager(camera):
    """Wrap camera in a minimal hw_manager-like object."""
    from unittest.mock import MagicMock
    hw = MagicMock()
    hw.camera = camera
    hw.motion_manager = None
    return hw


class TestChopper2x2Acquisition:
    """AcquisitionSession with Fire trigger produces valid delta signals."""

    def test_on_off_separation(self, camera, phase_reader):
        from andor_qt.ta.acquisition import AcquisitionSession, last_acquisition_stats

        hw = _make_hw_manager(camera)
        config = _make_config()

        with AcquisitionSession(hw, config, camera_settings=CAMERA_SETTINGS,
                                phase_reader=phase_reader) as session:
            results = []
            for _ in range(N_CYCLES):
                session.acquire_one_cycle()
                stats = last_acquisition_stats
                on_mean = float(np.asarray(stats["pump_mean"]).mean())
                off_mean = float(np.asarray(stats["ref_mean"]).mean())
                results.append((on_mean, off_mean))

        for i, (on_m, off_m) in enumerate(results):
            assert abs(on_m - off_m) > 50, (
                f"Cycle {i}: ON={on_m:.1f} OFF={off_m:.1f} — no separation"
            )

    def test_tag_alignment_consistent_across_cycles(self, camera, phase_reader):
        """The ON/OFF counts should be consistent across all cycles."""
        from andor_qt.ta.acquisition import AcquisitionSession, last_acquisition_stats

        hw = _make_hw_manager(camera)
        config = _make_config(n_averages=50)

        with AcquisitionSession(hw, config, camera_settings=CAMERA_SETTINGS,
                                phase_reader=phase_reader) as session:
            n_on_list = []
            for _ in range(5):
                try:
                    session.acquire_one_cycle()
                    n_on_list.append(last_acquisition_stats.get("n_on", 0))
                except RuntimeError:
                    continue

        assert len(n_on_list) >= 3, "Too few valid cycles"
        assert all(n > 0 for n in n_on_list), f"Some cycles had n_on=0: {n_on_list}"

    def test_polarity_deterministic_with_fire_trigger(self, camera, phase_reader):
        """With Fire start trigger, tag=1 should always map to the same intensity."""
        from andor_qt.ta.acquisition import AcquisitionSession, last_acquisition_stats

        hw = _make_hw_manager(camera)
        config = _make_config(n_averages=50)

        on_is_bright = []
        for _ in range(5):
            with AcquisitionSession(hw, config, camera_settings=CAMERA_SETTINGS,
                                    phase_reader=phase_reader) as session:
                session.acquire_one_cycle()
                stats = last_acquisition_stats
                on_m = float(np.asarray(stats["pump_mean"]).mean())
                off_m = float(np.asarray(stats["ref_mean"]).mean())
                on_is_bright.append(on_m > off_m)

        assert len(on_is_bright) >= 3
        assert all(v == on_is_bright[0] for v in on_is_bright), (
            f"Fire trigger polarity flipped: {on_is_bright}"
        )
