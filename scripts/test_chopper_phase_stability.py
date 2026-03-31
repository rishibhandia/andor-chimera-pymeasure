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
    from andor_qt.core.hardware_manager import HardwareManager
    hw = HardwareManager.instance()
    hw.initialize()
    return hw


def sync_to_chopper():
    """Wait for chopper rising edge on PFI13 (P2.5)."""
    import nidaqmx
    sync_line = f"{DEVICE}/port2/line5"
    prev = 0
    with nidaqmx.Task("chopper_sync") as task:
        task.di_channels.add_di_chan(sync_line)
        for _ in range(50000):
            val = task.read()
            if prev == 0 and val == 1:
                return True
            prev = val
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
    print("\nInitializing hardware...")
    hw = init_camera()
    camera = hw.camera

    # Apply camera settings
    camera.apply_camera_settings({
        "trigger_mode": "fast_external",
        "exposure_time": 0.0004,
        "vs_speed": 0,
        "hs_speed": 0,
    })

    phase_reader = create_phase_reader()

    results = []

    for trial in range(N_CYCLES):
        print(f"\n--- Trial {trial + 1}/{N_CYCLES} ---")

        # Sync to chopper rising edge
        print("  Syncing to chopper...")
        if not sync_to_chopper():
            print("  WARNING: sync failed, starting anyway")

        # Start camera and phase reader
        camera.start_run_till_abort()
        phase_reader.start()
        phase_reader.drain()

        # Read one cycle
        on_mean, off_mean, n_on, n_off = run_one_cycle(camera, phase_reader)

        # Stop
        camera.abort_acquisition()
        phase_reader.stop()

        if on_mean is None:
            print("  FAILED: no frames")
            results.append(None)
            continue

        # Determine which is brighter
        on_is_bright = on_mean > off_mean
        label = "ON=bright" if on_is_bright else "ON=dark (FLIPPED)"

        print(f"  ON mean: {on_mean:.1f}  OFF mean: {off_mean:.1f}  "
              f"n_on={n_on}  n_off={n_off}  -> {label}")

        results.append(on_is_bright)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    valid = [r for r in results if r is not None]
    if not valid:
        print("  No valid results!")
    else:
        n_bright = sum(valid)
        n_dark = len(valid) - n_bright
        print(f"  ON=bright: {n_bright}/{len(valid)}")
        print(f"  ON=dark (flipped): {n_dark}/{len(valid)}")

        if n_dark == 0:
            print("  RESULT: PASS -- phase is stable, no flipping")
        elif n_bright == 0:
            print("  RESULT: PASS -- phase is consistently inverted (but stable)")
            print("  (P0.0 polarity may be inverted -- check chopper controller)")
        else:
            print(f"  RESULT: FAIL -- phase flipped {n_dark} out of {len(valid)} times")
            print("  The chopper sync is not deterministic")

    # Cleanup
    print("\nShutting down...")
    hw.camera.set_cooler(False)
    time.sleep(1)

    return 0 if all(r == valid[0] for r in valid) else 1


if __name__ == "__main__":
    sys.exit(main())
