#!/usr/bin/env python
"""Test PFI13 start trigger for deterministic chopper phase alignment.

Hypothesis: If the phase reader's NI DAQ task uses PFI13 rising edge as
its start trigger, the first tag will always correspond to pump-ON
(blade open), making the tag-to-frame alignment deterministic across
camera restarts.

Test procedure (N trials):
  1. Start camera (RTA mode, fast_external trigger from SDG)
  2. Start phase reader with PFI13 start trigger
  3. Wait for frames, read frames + tags
  4. Check: is tag=1 always the bright (or always the dim) side?
  5. Stop camera + phase reader
  6. Repeat — the assignment should NOT flip.

Compare with control (no start trigger) to confirm the fix.

Run from project root:
    uv run python scripts/test_pfi13_start_trigger.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

os.environ["ANDOR_MOCK"] = ""  # ensure real hardware

DEVICE = "Astrella_DAQ"
N_TRIALS = 10
N_AVERAGES = 50
SHOTS_PER_FRAME = 2
SDK_PATH = r"C:\Program Files\Andor SDK"

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


def init_camera():
    from andor_pymeasure.instruments.andor_camera import AndorCamera
    camera = AndorCamera(sdk_path=SDK_PATH)
    camera.initialize()
    camera.apply_camera_settings(CAMERA_SETTINGS)
    print(f"  Camera: {camera._info.xpixels}x{camera._info.ypixels}")
    return camera


def make_phase_reader_with_start_trigger():
    """Create a phase reader that arms on PFI13 rising edge."""
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge

    task = nidaqmx.Task("phase_triggered")
    task.di_channels.add_di_chan(f"{DEVICE}/port0/line0")
    task.timing.cfg_samp_clk_timing(
        rate=1000.0,
        source=f"/{DEVICE}/PFI0",
        active_edge=Edge.RISING,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=100000,
    )
    # KEY: arm on PFI13 rising edge — task waits until chopper cycle starts
    task.triggers.start_trigger.cfg_dig_edge_start_trig(
        trigger_source=f"/{DEVICE}/PFI13",
        trigger_edge=Edge.RISING,
    )
    return task


def make_phase_reader_no_trigger():
    """Create a phase reader with no start trigger (control)."""
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge

    task = nidaqmx.Task("phase_free")
    task.di_channels.add_di_chan(f"{DEVICE}/port0/line0")
    task.timing.cfg_samp_clk_timing(
        rate=1000.0,
        source=f"/{DEVICE}/PFI0",
        active_edge=Edge.RISING,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=100000,
    )
    return task


def run_one_trial(camera, make_reader_fn, use_orphan_skip=False):
    """Run one acquisition cycle and return (on_mean, off_mean, first_tag)."""
    spf = SHOTS_PER_FRAME
    n_target = int(N_AVERAGES * 2.2) + 10
    wait_s = (n_target * spf) / 1000.0 + 0.05

    # 1. Create + start phase reader FIRST (if PFI13-triggered, it arms and
    #    waits for the rising edge before acquiring any samples)
    task = make_reader_fn()
    task.start()

    # 2. Start camera — it captures on the next SDG trigger
    camera.start_run_till_abort()

    # 3. Wait for frames + tags to accumulate
    time.sleep(wait_s)
    frames, n_chunk = camera.get_buffered_frames()

    if n_chunk == 0:
        camera.abort_acquisition()
        task.stop()
        task.close()
        return None, None, None

    # Read ALL available tags (not n_chunk * spf — we want to know exactly
    # how many tags arrived since the reader started)
    n_tags_avail = task.in_stream.avail_samp_per_chan
    if n_tags_avail == 0:
        camera.abort_acquisition()
        task.stop()
        task.close()
        return None, None, None

    tags = np.array(
        task.read(number_of_samples_per_channel=n_tags_avail, timeout=5.0),
        dtype=np.int8,
    )

    # 5. Stop
    camera.abort_acquisition()
    task.stop()
    task.close()

    # 6. Determine orphan frames (captured before phase reader started)
    n_tagged_frames = len(tags) // spf
    orphan = n_chunk - n_tagged_frames

    if use_orphan_skip and orphan > 0:
        # Skip orphan frames — these have no corresponding tags
        frames = frames[orphan:]
        n_chunk = len(frames)
        print(f"    (skipped {orphan} orphan frames)")

    # 7. Process
    usable = min(n_chunk, len(tags) // spf)
    tag_groups = tags[:usable * spf].reshape(usable, spf)
    use_frames = frames[:usable]

    matched_mask = (tag_groups == tag_groups[:, :1]).all(axis=1)
    matched_frames = use_frames[matched_mask]
    matched_tags = tag_groups[matched_mask, 0]

    on_frames = matched_frames[matched_tags == 1]
    off_frames = matched_frames[matched_tags == 0]

    if len(on_frames) == 0 or len(off_frames) == 0:
        return None, None, None

    on_mean = float(on_frames.mean())
    off_mean = float(off_frames.mean())
    first_tag = int(tags[0])

    return on_mean, off_mean, first_tag


def run_test(label, camera, make_reader_fn, use_orphan_skip=False):
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")

    results = []
    for trial in range(N_TRIALS):
        on_m, off_m, first_tag = run_one_trial(
            camera, make_reader_fn, use_orphan_skip=use_orphan_skip,
        )
        if on_m is None:
            print(f"  Trial {trial+1}: FAILED (no frames)")
            continue

        on_bright = on_m > off_m
        tag_label = "ON=bright" if on_bright else "ON=dim"
        print(
            f"  Trial {trial+1}: ON={on_m:.0f}  OFF={off_m:.0f}  "
            f"first_tag={first_tag}  -> {tag_label}"
        )
        results.append(on_bright)
        time.sleep(0.2)  # short pause between trials

    if not results:
        print(f"  RESULT: NO VALID TRIALS")
        return results

    n_bright = sum(results)
    n_dim = len(results) - n_bright
    if n_bright == 0 or n_dim == 0:
        print(f"  RESULT: PASS — stable ({n_bright} bright, {n_dim} dim)")
    else:
        print(f"  RESULT: FAIL — flipped {min(n_bright, n_dim)}/{len(results)} times")

    return results


def main():
    print("PFI13 Start Trigger Test")
    print(f"Device: {DEVICE}")
    print(f"Trials: {N_TRIALS}")
    print(f"Averages: {N_AVERAGES}")
    print()

    print("Initializing camera...")
    camera = init_camera()

    try:
        # Test A: No start trigger (control — should flip ~50%)
        results_a = run_test(
            "TEST A: No start trigger (control)",
            camera,
            make_phase_reader_no_trigger,
        )

        # Test B: PFI13 start trigger (should be stable)
        results_b = run_test(
            "TEST B: PFI13 start trigger (no orphan skip)",
            camera,
            make_phase_reader_with_start_trigger,
        )

        # Test C: PFI13 start trigger + orphan frame skip
        results_c = run_test(
            "TEST C: PFI13 start trigger + orphan skip",
            camera,
            make_phase_reader_with_start_trigger,
            use_orphan_skip=True,
        )

        # Summary
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        for label, res in [
            ("A (no trigger)", results_a),
            ("B (PFI13, no skip)", results_b),
            ("C (PFI13 + orphan skip)", results_c),
        ]:
            if not res:
                print(f"  {label}: no valid results")
                continue
            n_bright = sum(res)
            n_dim = len(res) - n_bright
            stable = (n_bright == 0 or n_dim == 0)
            status = "STABLE" if stable else f"FLIPPED {min(n_bright, n_dim)}x"
            print(f"  {label}: {status}  ({n_bright} bright, {n_dim} dim)")

    finally:
        print("\nShutting down camera...")
        camera.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
