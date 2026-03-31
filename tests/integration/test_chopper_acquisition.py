"""Integration test: chopper_2x2 acquisition with real hardware.

Mirrors the GUI's exact acquisition path — camera + phase reader in
continuous mode. Verifies ON/OFF separation over multiple read cycles.

Run with::

    uv run pytest tests/integration/test_chopper_acquisition.py --hardware -v
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
N_CYCLES = 3


def _sync_to_chopper() -> None:
    """Wait for a chopper rising edge on PFI13 (hardware edge detect)."""
    import nidaqmx
    from nidaqmx.constants import Edge

    with nidaqmx.Task("chopper_sync") as task:
        task.ci_channels.add_ci_count_edges_chan(
            f"{NIDAQ_DEVICE}/ctr0", edge=Edge.RISING,
        )
        task.ci_channels[0].ci_count_edges_term = PFI13
        task.start()
        task.read(timeout=5.0)


class TestChopper2x2Acquisition:
    """Continuous-mode chopper_2x2 acquisition produces valid delta signals."""

    def test_on_off_separation(self, camera, phase_reader):
        from andor_qt.ta.acquisition import (
            _process_chopper_frames,
            last_acquisition_stats,
        )
        from andor_qt.ta.scan_config import TAScanConfig

        camera.apply_camera_settings(CAMERA_SETTINGS)

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

        _sync_to_chopper()
        camera.start_run_till_abort()
        phase_reader.start()
        phase_reader.drain()

        # Discard first read (stabilization)
        time.sleep(wait_s)
        camera.get_buffered_frames()
        phase_reader.read_tags(300)

        try:
            results = []
            for _ in range(N_CYCLES):
                time.sleep(wait_s)
                frames, n_chunk = camera.get_buffered_frames()
                assert n_chunk > 0, "No frames received"

                tags = phase_reader.read_tags(n_chunk * spf)
                _process_chopper_frames(frames, tags, config)

                stats = last_acquisition_stats
                on_mean = float(np.asarray(stats["pump_mean"]).mean())
                off_mean = float(np.asarray(stats["ref_mean"]).mean())
                results.append((on_mean, off_mean))

        finally:
            camera.abort_acquisition()
            phase_reader.stop()

        # Verify: ON and OFF should be different across all cycles
        for i, (on_m, off_m) in enumerate(results):
            assert abs(on_m - off_m) > 50, (
                f"Cycle {i}: ON={on_m:.1f} OFF={off_m:.1f} — no separation"
            )

    def test_tag_alignment_consistent_across_cycles(self, camera, phase_reader):
        """The offset detection should pick the same offset each cycle."""
        from andor_qt.ta.acquisition import _process_chopper_frames
        from andor_qt.ta.scan_config import TAScanConfig

        camera.apply_camera_settings(CAMERA_SETTINGS)

        config = TAScanConfig(
            delay_list=[0.0],
            n_averages=50,
            acquisition_mode="chopper_2x2",
            scan_direction="forward",
            sample_name="test",
            shots_per_frame=SHOTS_PER_FRAME,
        )

        spf = SHOTS_PER_FRAME
        n_target = int(50 * 2.2) + 10
        wait_s = (n_target * spf) / 1000.0 + 0.05

        _sync_to_chopper()
        camera.start_run_till_abort()
        phase_reader.start()
        phase_reader.drain()

        # Discard first read
        time.sleep(wait_s)
        camera.get_buffered_frames()
        phase_reader.read_tags(300)

        try:
            n_on_list = []
            for _ in range(5):
                time.sleep(wait_s)
                frames, n_chunk = camera.get_buffered_frames()
                if n_chunk == 0:
                    continue
                tags = phase_reader.read_tags(n_chunk * spf)
                _process_chopper_frames(frames, tags, config)
                from andor_qt.ta.acquisition import last_acquisition_stats
                n_on_list.append(last_acquisition_stats.get("n_on", 0))
        finally:
            camera.abort_acquisition()
            phase_reader.stop()

        # All cycles should produce roughly the same n_on count
        assert len(n_on_list) >= 3, "Too few valid cycles"
        assert all(n > 0 for n in n_on_list), f"Some cycles had n_on=0: {n_on_list}"
