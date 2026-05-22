#!/usr/bin/env python
"""Test P0.0 clocked by PFI12 (SDG 500 Hz) for deterministic chopper tagging.

Hypothesis: Since PFI12 (SDG 500 Hz) drives both the camera trigger and
the chopper (via REF IN ÷2), clocking P0.0 by PFI12 gives exactly 1 tag
per camera frame with no alignment ambiguity. Tag N = chopper state when
frame N was captured.

Compares:
  A. PFI0 clock (1 kHz, current approach) — 2 tags/frame, alignment issues
  B. PFI12 clock (500 Hz, proposed) — 1 tag/frame, no alignment issues

Run from project root (close GUI first):
    uv run python scripts/test_pfi12_clock.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

os.environ["ANDOR_MOCK"] = ""

DEVICE = "Astrella_DAQ"
N_TRIALS = 30
N_AVERAGES = 50
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


def make_reader_pfi0():
    """Phase reader clocked by PFI0 (1 kHz) — current approach."""
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge

    task = nidaqmx.Task("phase_pfi0")
    task.di_channels.add_di_chan(f"{DEVICE}/port0/line0")
    task.timing.cfg_samp_clk_timing(
        rate=1000.0,
        source=f"/{DEVICE}/PFI0",
        active_edge=Edge.RISING,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=100000,
    )
    return task


def make_reader_pfi12():
    """Phase reader clocked by PFI12 (SDG 500 Hz) — proposed approach."""
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge

    task = nidaqmx.Task("phase_pfi12")
    task.di_channels.add_di_chan(f"{DEVICE}/port0/line0")
    task.timing.cfg_samp_clk_timing(
        rate=500.0,
        source=f"/{DEVICE}/PFI12",
        active_edge=Edge.RISING,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=100000,
    )
    return task


def run_trial_pfi0(camera):
    """One trial with PFI0 clock (spf=2, current approach)."""
    spf = 2
    n_target = int(N_AVERAGES * 2.2) + 10
    wait_s = (n_target * spf) / 1000.0 + 0.05

    task = make_reader_pfi0()
    task.start()
    camera.start_run_till_abort()

    time.sleep(wait_s)
    frames, n_chunk = camera.get_buffered_frames()
    if n_chunk == 0:
        camera.abort_acquisition()
        task.stop(); task.close()
        return None, None

    tags = np.array(
        task.read(number_of_samples_per_channel=n_chunk * spf, timeout=5.0),
        dtype=np.int8,
    )
    camera.abort_acquisition()
    task.stop(); task.close()

    # Group tags by spf=2, find best offset
    best_offset, best_matched = 0, -1
    for offset in range(spf):
        usable = (len(tags) - offset) // spf
        if usable < 1:
            continue
        grp = tags[offset:offset + usable * spf].reshape(usable, spf)
        n_m = int((grp == grp[:, :1]).all(axis=1).sum())
        if n_m > best_matched:
            best_matched = n_m
            best_offset = offset

    usable = min(n_chunk, (len(tags) - best_offset) // spf)
    tag_groups = tags[best_offset:best_offset + usable * spf].reshape(usable, spf)
    use_frames = frames[:usable]

    matched = (tag_groups == tag_groups[:, :1]).all(axis=1)
    m_frames = use_frames[matched]
    m_tags = tag_groups[matched, 0]

    on_frames = m_frames[m_tags == 1]
    off_frames = m_frames[m_tags == 0]
    if len(on_frames) == 0 or len(off_frames) == 0:
        return None, None

    return float(on_frames.mean()), float(off_frames.mean())


def run_trial_pfi12(camera):
    """One trial with PFI12 clock (1 tag per frame, proposed approach)."""
    n_target = int(N_AVERAGES * 2.2) + 10
    wait_s = n_target / 500.0 + 0.05  # 500 Hz → 2ms per frame

    task = make_reader_pfi12()
    task.start()
    camera.start_run_till_abort()

    time.sleep(wait_s)
    frames, n_chunk = camera.get_buffered_frames()
    if n_chunk == 0:
        camera.abort_acquisition()
        task.stop(); task.close()
        return None, None

    # Read all available tags — 1 tag per frame
    n_avail = task.in_stream.avail_samp_per_chan
    if n_avail == 0:
        camera.abort_acquisition()
        task.stop(); task.close()
        return None, None

    tags = np.array(
        task.read(number_of_samples_per_channel=n_avail, timeout=5.0),
        dtype=np.int8,
    )
    camera.abort_acquisition()
    task.stop(); task.close()

    # 1 tag per frame — try both possible alignments (off by 0 or 1)
    # and pick the one with maximum ON/OFF intensity separation.
    orphan = len(tags) - n_chunk
    best_sep = -1
    best_on_mean = best_off_mean = None
    best_shift = 0

    for shift in range(-1, 2):
        start = max(0, orphan + shift)
        end = start + n_chunk
        if end > len(tags):
            continue
        t = tags[start:end]
        f = frames[:len(t)]

        on_f = f[t == 1]
        off_f = f[t == 0]
        if len(on_f) == 0 or len(off_f) == 0:
            continue

        on_m = float(on_f.mean())
        off_m = float(off_f.mean())
        sep = abs(on_m - off_m)
        if sep > best_sep:
            best_sep = sep
            best_on_mean = on_m
            best_off_mean = off_m
            best_shift = shift

    if best_on_mean is None:
        return None, None

    print(f"    frames={n_chunk} tags={len(tags)} orphan={orphan} "
          f"best_shift={best_shift} sep={best_sep:.0f} "
          f"on={best_on_mean:.0f} off={best_off_mean:.0f}")

    return best_on_mean, best_off_mean


def run_test(label, camera, trial_fn):
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")

    results = []
    for trial in range(N_TRIALS):
        on_m, off_m = trial_fn(camera)
        if on_m is None:
            print(f"  Trial {trial+1}: FAILED")
            continue

        on_bright = on_m > off_m
        tag = "ON=bright" if on_bright else "ON=dim"
        print(f"  Trial {trial+1}: ON={on_m:.0f}  OFF={off_m:.0f}  -> {tag}")
        results.append(on_bright)
        time.sleep(0.2)

    if not results:
        print("  RESULT: NO VALID TRIALS")
        return results

    n_b = sum(results)
    n_d = len(results) - n_b
    if n_b == 0 or n_d == 0:
        print(f"  RESULT: PASS — stable ({n_b} bright, {n_d} dim)")
    else:
        print(f"  RESULT: FAIL — flipped {min(n_b, n_d)}/{len(results)} times")
    return results


def main():
    print("PFI12 vs PFI0 Clock Test")
    print(f"Device: {DEVICE}, Trials: {N_TRIALS}, Averages: {N_AVERAGES}")
    print()

    print("Initializing camera...")
    camera = init_camera()

    try:
        results_a = run_test(
            "TEST A: PFI0 clock (1 kHz, spf=2, current)",
            camera, run_trial_pfi0,
        )
        results_b = run_test(
            "TEST B: PFI12 clock (500 Hz, 1 tag/frame, proposed)",
            camera, run_trial_pfi12,
        )

        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        for label, res in [("A (PFI0 1kHz)", results_a), ("B (PFI12 500Hz)", results_b)]:
            if not res:
                print(f"  {label}: no valid results")
                continue
            n_b = sum(res)
            n_d = len(res) - n_b
            stable = (n_b == 0 or n_d == 0)
            status = "STABLE" if stable else f"FLIPPED {min(n_b, n_d)}x"
            print(f"  {label}: {status}  ({n_b} bright, {n_d} dim)")

    finally:
        print("\nShutting down camera...")
        camera.shutdown()


if __name__ == "__main__":
    sys.exit(main())
