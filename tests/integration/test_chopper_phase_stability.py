"""Integration test: chopper phase stability across camera restarts.

Confirms that continuous camera mode keeps the phase stable, while
restarting the camera causes random ON/OFF flipping.

Run with::

    uv run pytest tests/integration/test_chopper_phase_stability.py --hardware -v
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from .conftest import NIDAQ_DEVICE, PFI13

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


def _sync_to_chopper() -> None:
    import nidaqmx
    from nidaqmx.constants import Edge

    with nidaqmx.Task("chopper_sync") as task:
        task.ci_channels.add_ci_count_edges_chan(
            f"{NIDAQ_DEVICE}/ctr0", edge=Edge.RISING,
        )
        task.ci_channels[0].ci_count_edges_term = PFI13
        task.start()
        task.read(timeout=5.0)


def _run_one_cycle(camera, phase_reader):
    """Read one batch and return (on_mean, off_mean)."""
    from andor_qt.ta.acquisition import _process_chopper_frames, last_acquisition_stats
    from andor_qt.ta.scan_config import TAScanConfig

    config = TAScanConfig(
        delay_list=[0.0],
        n_averages=N_AVERAGES,
        acquisition_mode="chopper_2x2",
        scan_direction="forward",
        sample_name="test",
        shots_per_frame=SHOTS_PER_FRAME,
    )

    spf = SHOTS_PER_FRAME
    n_target = int(N_AVERAGES * 2.2) + 10
    wait_s = (n_target * spf) / 1000.0 + 0.05

    time.sleep(wait_s)
    frames, n_chunk = camera.get_buffered_frames()
    if n_chunk == 0:
        return None, None

    tags = phase_reader.read_tags(n_chunk * spf)
    _process_chopper_frames(frames, tags, config)

    stats = last_acquisition_stats
    on_mean = float(np.asarray(stats.get("pump_mean", [0])).mean())
    off_mean = float(np.asarray(stats.get("ref_mean", [0])).mean())
    return on_mean, off_mean


class TestContinuousModeStability:
    """Camera stays running — phase should never flip."""

    def test_phase_stable_across_trials(self, camera, phase_reader):
        camera.apply_camera_settings(CAMERA_SETTINGS)

        _sync_to_chopper()
        camera.start_run_till_abort()
        phase_reader.start()
        phase_reader.drain()

        # Discard first read
        spf = SHOTS_PER_FRAME
        n_target = int(N_AVERAGES * 2.2) + 10
        wait_s = (n_target * spf) / 1000.0 + 0.05
        time.sleep(wait_s)
        camera.get_buffered_frames()
        phase_reader.read_tags(300)

        try:
            on_is_bright_list = []
            for _ in range(N_TRIALS):
                on_m, off_m = _run_one_cycle(camera, phase_reader)
                if on_m is None:
                    continue
                on_is_bright_list.append(on_m > off_m)
        finally:
            camera.abort_acquisition()
            phase_reader.stop()

        assert len(on_is_bright_list) >= 4, "Too few valid trials"
        # All trials should agree on which side is brighter
        assert all(v == on_is_bright_list[0] for v in on_is_bright_list), (
            f"Phase flipped during continuous mode: {on_is_bright_list}"
        )


class TestRestartModeInstability:
    """Camera restarts each trial — phase flipping is expected (informational).

    This test is marked ``xfail`` because restarting is *known* to flip the
    phase ~50% of the time.  If it somehow passes, that's fine too.
    """

    @pytest.mark.xfail(reason="Restart randomizes phase — expected to flip", strict=False)
    def test_phase_stable_across_restarts(self, camera, phase_reader):
        camera.apply_camera_settings(CAMERA_SETTINGS)

        on_is_bright_list = []
        for _ in range(N_TRIALS):
            _sync_to_chopper()
            camera.start_run_till_abort()
            phase_reader.start()
            phase_reader.drain()

            on_m, off_m = _run_one_cycle(camera, phase_reader)

            camera.abort_acquisition()
            phase_reader.stop()

            if on_m is None:
                continue
            on_is_bright_list.append(on_m > off_m)

        assert len(on_is_bright_list) >= 4
        assert all(v == on_is_bright_list[0] for v in on_is_bright_list), (
            f"Phase flipped across restarts: {on_is_bright_list}"
        )
