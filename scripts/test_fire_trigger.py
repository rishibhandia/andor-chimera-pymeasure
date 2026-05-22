#!/usr/bin/env python
"""Test Camera Fire signal on PFI13 as start trigger for phase reader.

Wiring:
  PFI0:  1 kHz laser sync (sample clock)
  PFI12: SDG 500 Hz (camera trigger)
  PFI13: Camera Fire output (start trigger for phase reader)
  P0.0:  Chopper REF OUT (tag signal)

The phase reader uses PFI0 as sample clock (2 tags/frame) and PFI13
(Fire) as start trigger. The reader arms but doesn't sample until the
camera actually starts exposing. This eliminates orphan tags entirely.

Run from project root (close GUI first):
    uv run python scripts/test_fire_trigger.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

os.environ["ANDOR_MOCK"] = ""

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


def make_reader_fire_trigger():
    """Phase reader: PFI0 clock (1 kHz), PFI13 Fire start trigger."""
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge

    task = nidaqmx.Task("phase_fire")
    task.di_channels.add_di_chan(f"{DEVICE}/port0/line0")
    task.timing.cfg_samp_clk_timing(
        rate=1000.0,
        source=f"/{DEVICE}/PFI0",
        active_edge=Edge.RISING,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=100000,
    )
    # Start trigger: wait for Camera Fire rising edge on PFI13
    task.triggers.start_trigger.cfg_dig_edge_start_trig(
        trigger_source=f"/{DEVICE}/PFI13",
        trigger_edge=Edge.RISING,
    )
    return task


def make_reader_no_trigger():
    """Phase reader: PFI0 clock (1 kHz), no start trigger (control)."""
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


def process_tags(frames, tags, spf=2, n_averages=50):
    """Process frames + tags using offset detection. Returns (on_mean, off_mean)."""
    n_frames = len(frames)

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

    usable = min(n_frames, (len(tags) - best_offset) // spf)
    tag_groups = tags[best_offset:best_offset + usable * spf].reshape(usable, spf)
    use_frames = frames[:usable]

    matched = (tag_groups == tag_groups[:, :1]).all(axis=1)
    m_frames = use_frames[matched]
    m_tags = tag_groups[matched, 0]

    on_frames = m_frames[m_tags == 1]
    off_frames = m_frames[m_tags == 0]
    n_disc = int(usable - matched.sum())

    return on_frames, off_frames, n_disc, best_offset


def run_trial(camera, make_reader_fn, label=""):
    """Run one acquisition cycle."""
    spf = SHOTS_PER_FRAME
    n_target = int(N_AVERAGES * 2.2) + 10
    wait_s = (n_target * spf) / 1000.0 + 0.05

    # 1. Create + arm phase reader (Fire-triggered: waits for camera)
    task = make_reader_fn()
    task.start()

    # 2. Start camera — Fire signal triggers the phase reader
    camera.start_run_till_abort()

    # 3. Wait for data
    time.sleep(wait_s)
    frames, n_chunk = camera.get_buffered_frames()

    if n_chunk == 0:
        camera.abort_acquisition()
        task.stop(); task.close()
        return None

    # 4. Read tags
    n_avail = task.in_stream.avail_samp_per_chan
    if n_avail == 0:
        camera.abort_acquisition()
        task.stop(); task.close()
        return None

    tags = np.array(
        task.read(number_of_samples_per_channel=n_avail, timeout=5.0),
        dtype=np.int8,
    )

    # 5. Stop
    camera.abort_acquisition()
    task.stop(); task.close()

    # 6. Process
    on_frames, off_frames, n_disc, offset = process_tags(frames, tags, spf)

    if len(on_frames) == 0 or len(off_frames) == 0:
        return None

    on_mean = float(on_frames.mean())
    off_mean = float(off_frames.mean())
    on_bright = on_mean > off_mean

    print(f"    frames={n_chunk} tags={len(tags)} ratio={len(tags)/n_chunk:.2f} "
          f"offset={offset} disc={n_disc} "
          f"on={len(on_frames)} off={len(off_frames)}")

    return {"on": on_mean, "off": off_mean, "bright": on_bright,
            "tags": len(tags), "frames": n_chunk, "disc": n_disc}


def run_test(label, camera, make_reader_fn):
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")

    results = []
    for trial in range(N_TRIALS):
        r = run_trial(camera, make_reader_fn)
        if r is None:
            print(f"  Trial {trial+1}: FAILED")
            continue

        tag = "ON=bright" if r["bright"] else "ON=dim"
        print(f"  Trial {trial+1}: ON={r['on']:.0f}  OFF={r['off']:.0f}  -> {tag}")
        results.append(r["bright"])
        delay = 5.0 if "Fire" in label else 0.2
        time.sleep(delay)

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
    print("Camera Fire Trigger Test")
    print(f"Device: {DEVICE}, Trials: {N_TRIALS}")
    print(f"PFI0=1kHz clock, PFI13=Camera Fire start trigger, P0.0=chopper tags")
    print()

    print("Initializing camera...")
    camera = init_camera()

    try:
        results_a = run_test(
            "TEST A: No start trigger (control)",
            camera, make_reader_no_trigger,
        )
        results_b = run_test(
            "TEST B: Camera Fire start trigger on PFI13",
            camera, make_reader_fire_trigger,
        )

        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        for label, res in [("A (no trigger)", results_a),
                           ("B (Fire trigger)", results_b)]:
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
