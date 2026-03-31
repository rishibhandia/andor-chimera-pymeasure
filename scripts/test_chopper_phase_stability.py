#!/usr/bin/env python
"""Test chopper phase stability across camera start/stop cycles.

Starts the camera with chopper sync, reads frames, checks ON/OFF assignment,
stops, repeats N times. Reports whether the phase flips.

Run from project root:
    uv run python scripts/test_chopper_phase_stability.py

Requires:
  - Camera initialized (will init/shutdown automatically)
  - PFI0: 1 kHz laser sync
  - P0.0: chopper REF OUT (pump phase tags)
  - PFI13: chopper REF OUT (for sync — User 1 BNC)
  - SDG 500 Hz -> Camera Ext Trigger
  - Chopper running at 250 Hz
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

os.environ["ANDOR_MOCK"] = ""  # ensure real hardware

DEVICE = "Astrella_DAQ"
N_CYCLES = 10
N_AVERAGES = 100
SHOTS_PER_FRAME = 2


def init_camera():
    """Initialize camera and return it."""
    from andor_pymeasure.instruments.andor_camera import AndorCamera
    sdk_path = r"C:\Program Files\Andor SDK"
    print(f"  SDK path: {sdk_path}")
    camera = AndorCamera(sdk_path=sdk_path)
    camera.initialize()
    print(f"  Camera initialized: {camera._info.xpixels}x{camera._info.ypixels}")
    return camera


def sync_to_chopper():
    """Wait for chopper rising edge on PFI13 using hardware counter."""
    import nidaqmx
    from nidaqmx.constants import Edge
    try:
        with nidaqmx.Task("chopper_sync") as task:
            task.ci_channels.add_ci_count_edges_chan(
                f"{DEVICE}/ctr0",
                edge=Edge.RISING,
            )
            task.ci_channels[0].ci_count_edges_term = f"/{DEVICE}/PFI13"
            task.start()
            task.read(timeout=5.0)  # blocks until rising edge
        return True
    except Exception as exc:
        print(f"  Sync failed: {exc}")
        return False


def create_phase_reader():
    """Create and return the NI DAQ phase reader."""
    from andor_qt.ta.nidaq_phase import NIDAQPhaseReader
    return NIDAQPhaseReader(
        device=DEVICE,
        di_channel="port0/line0",
        clock_source=f"/{DEVICE}/PFI0",
        clock_rate=1000.0,
    )


def run_one_cycle(camera, phase_reader):
    """Run one acquisition cycle and return (on_mean, off_mean, n_on, n_off)."""
    from andor_qt.ta.acquisition import _process_chopper_frames
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
    frame_period_ms = spf
    wait_s = (n_target * frame_period_ms) / 1000.0 + 0.05

    time.sleep(wait_s)
    frames, n_chunk = camera.get_buffered_frames()
    if n_chunk == 0:
        return None, None, 0, 0

    tags = phase_reader.read_tags(n_chunk * spf)

    delta = _process_chopper_frames(frames, tags, config)

    from andor_qt.ta.acquisition import last_acquisition_stats
    stats = last_acquisition_stats
    on_mean = float(stats.get("pump_mean", np.array([0])).mean())
    off_mean = float(stats.get("ref_mean", np.array([0])).mean())
    n_on = stats.get("n_on", 0)
    n_off = stats.get("n_off", 0)
    return on_mean, off_mean, n_on, n_off


def main():
    print("=" * 60)
    print("Chopper Phase Stability Test")
    print(f"Device: {DEVICE}")
    print(f"Cycles: {N_CYCLES}")
    print(f"Averages per cycle: {N_AVERAGES}")
    print(f"Shots per frame: {SHOTS_PER_FRAME}")
    print("=" * 60)

    # Init hardware
    print("\nInitializing camera...")
    camera = init_camera()

    # Apply camera settings
    camera.apply_camera_settings({
        "trigger_mode": "fast_external",
        "exposure_time": 0.0004,
        "vs_speed_index": 0,
        "hs_speed_index": 0,
        "amplifier_type": 1,
        "preamp_gain_index": 0,
        "hbin": 1,
        "vbin": 1,
    })

    phase_reader = create_phase_reader()

    results = []

    # Test A: restart camera each trial (old behavior)
    print("\n=== TEST A: Restart camera each trial ===")
    for trial in range(N_CYCLES):
        print(f"\n--- Trial {trial + 1}/{N_CYCLES} ---")

        print("  Syncing to chopper...")
        sync_to_chopper()

        camera.start_run_till_abort()
        phase_reader.start()
        phase_reader.drain()

        on_mean, off_mean, n_on, n_off = run_one_cycle(camera, phase_reader)

        camera.abort_acquisition()
        phase_reader.stop()

        if on_mean is None:
            print("  FAILED: no frames")
            results.append(None)
            continue

        on_is_bright = on_mean > off_mean
        label = "ON=bright" if on_is_bright else "ON=dark (FLIPPED)"
        print(f"  ON mean: {on_mean:.1f}  OFF mean: {off_mean:.1f}  "
              f"n_on={n_on}  n_off={n_off}  -> {label}")
        results.append(on_is_bright)

    # Test B: continuous camera (new behavior — matches app)
    print("\n=== TEST B: Continuous camera (no restart) ===")
    results_b = []

    print("  Syncing to chopper...")
    sync_to_chopper()

    camera.start_run_till_abort()
    phase_reader.start()
    phase_reader.drain()

    for trial in range(N_CYCLES):
        print(f"\n--- Trial {trial + 1}/{N_CYCLES} ---")

        on_mean, off_mean, n_on, n_off = run_one_cycle(camera, phase_reader)

        if on_mean is None:
            print("  FAILED: no frames")
            results_b.append(None)
            continue

        on_is_bright = on_mean > off_mean
        label = "ON=bright" if on_is_bright else "ON=dark (FLIPPED)"
        print(f"  ON mean: {on_mean:.1f}  OFF mean: {off_mean:.1f}  "
              f"n_on={n_on}  n_off={n_off}  -> {label}")
        results_b.append(on_is_bright)

    camera.abort_acquisition()
    phase_reader.stop()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for label, res in [("Test A (restart)", results), ("Test B (continuous)", results_b)]:
        valid = [r for r in res if r is not None]
        if not valid:
            print(f"  {label}: No valid results!")
            continue
        n_bright = sum(valid)
        n_dark = len(valid) - n_bright
        if n_dark == 0 or n_bright == 0:
            print(f"  {label}: PASS -- stable ({n_bright} bright, {n_dark} flipped)")
        else:
            print(f"  {label}: FAIL -- {n_dark}/{len(valid)} flipped")

    # Cleanup
    print("\nShutting down...")
    camera.shutdown()

    return 0 if all(r == valid[0] for r in valid) else 1


if __name__ == "__main__":
    sys.exit(main())
