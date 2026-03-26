"""Test Run Till Abort acquisition mode for chopper_2x2.

Compares Single Scan (current) vs Run Till Abort (proposed) frame rates.
Acquires N_PAIRS pump-on/pump-off pairs and reports:
  - Total time
  - Frames per second
  - Discard rate
  - Phase tag alignment

Run with hardware connected:
    uv run python scripts/test_run_till_abort.py
"""

from __future__ import annotations

import time
import sys
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
N_PAIRS = 100          # number of pump-on/pump-off pairs to collect
SDK_PATH = r"C:\Program Files\Andor SDK"
NIDAQ_DEVICE = "Astrella_DAQ"
NIDAQ_DI_CHANNEL = "port0/line0"
NIDAQ_CLOCK_SOURCE = "/Astrella_DAQ/PFI0"
NIDAQ_CLOCK_RATE = 1000.0


def init_camera(sdk, codes, errors):
    """Initialize camera and return detector size."""
    ret = sdk.Initialize(SDK_PATH)
    if ret != errors.Error_Codes.DRV_SUCCESS:
        print(f"Initialize failed: {ret}")
        sys.exit(1)

    ret, xpixels, ypixels = sdk.GetDetector()
    print(f"Camera: {xpixels}x{ypixels}")

    # Set FVB mode, fast external trigger
    sdk.SetReadMode(codes.Read_Mode.FULL_VERTICAL_BINNING)
    sdk.SetTriggerMode(codes.Trigger_Mode.EXTERNAL)  # fast external
    sdk.SetExposureTime(0.002)  # 2 ms
    sdk.SetVSSpeed(0)  # fastest
    sdk.SetHSSpeed(0, 0)  # 3 MHz
    sdk.SetFVBHBin(1)

    return xpixels


def make_phase_reader():
    """Create and start the NI DAQ phase reader."""
    from andor_qt.ta.nidaq_phase import NIDAQPhaseReader
    reader = NIDAQPhaseReader(
        device=NIDAQ_DEVICE,
        di_channel=NIDAQ_DI_CHANNEL,
        clock_source=NIDAQ_CLOCK_SOURCE,
        clock_rate=NIDAQ_CLOCK_RATE,
    )
    reader.start()
    return reader


def test_single_scan(sdk, codes, errors, xpixels, reader):
    """Current approach: PrepareAcquisition per frame."""
    print("\n--- SINGLE SCAN mode (current) ---")

    acq_ok = {
        errors.Error_Codes.DRV_SUCCESS,
        errors.Error_Codes.DRV_TEMPERATURE_STABILIZED,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_REACHED,
        errors.Error_Codes.DRV_TEMPERATURE_DRIFT,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_STABILIZED,
    }

    sdk.SetAcquisitionMode(codes.Acquisition_Mode.SINGLE_SCAN)

    on_count = 0
    off_count = 0
    discarded = 0
    pairs = 0
    max_frames = N_PAIRS * 6

    reader.drain()
    t0 = time.perf_counter()
    frames = 0

    while pairs < N_PAIRS and frames < max_frames:
        # Arm
        sdk.PrepareAcquisition()
        sdk.StartAcquisition()
        reader.drain()

        # Collect
        ret = sdk.WaitForAcquisition()
        if ret not in acq_ok:
            print(f"WaitForAcquisition failed: {ret}")
            break
        ret, arr, vf, vl = sdk.GetImages16(1, 1, xpixels)
        frames += 1

        # Phase tags
        raw = reader.read_tags(3)
        if raw[0] == raw[1]:
            tags = raw[:2]
        else:
            tags = raw[1:]

        if tags[0] != tags[1]:
            discarded += 1
            continue

        if tags[0] == 1:
            on_count += 1
        else:
            off_count += 1

        if on_count > 0 and off_count > 0:
            on_count -= 1
            off_count -= 1
            pairs += 1

    elapsed = time.perf_counter() - t0
    print(f"  Frames: {frames}")
    print(f"  Pairs:  {pairs}")
    print(f"  Discarded: {discarded}")
    print(f"  Time:   {elapsed:.3f} s")
    print(f"  FPS:    {frames / elapsed:.1f}")
    print(f"  Per pair: {elapsed / max(pairs, 1) * 1000:.1f} ms")


def test_run_till_abort(sdk, codes, errors, xpixels, reader):
    """Proposed approach: PrepareAcquisition once, read frames from buffer."""
    print("\n--- RUN TILL ABORT mode (proposed) ---")

    acq_ok = {
        errors.Error_Codes.DRV_SUCCESS,
        errors.Error_Codes.DRV_TEMPERATURE_STABILIZED,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_REACHED,
        errors.Error_Codes.DRV_TEMPERATURE_DRIFT,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_STABILIZED,
    }

    sdk.SetAcquisitionMode(5)  # RUN_TILL_ABORT = 5

    on_count = 0
    off_count = 0
    discarded = 0
    pairs = 0
    max_frames = N_PAIRS * 6

    # Arm once
    ret = sdk.PrepareAcquisition()
    if ret != errors.Error_Codes.DRV_SUCCESS:
        print(f"PrepareAcquisition failed: {ret}")
        return
    ret = sdk.StartAcquisition()
    if ret != errors.Error_Codes.DRV_SUCCESS:
        print(f"StartAcquisition failed: {ret}")
        return

    reader.drain()
    t0 = time.perf_counter()
    frames = 0

    try:
        while pairs < N_PAIRS and frames < max_frames:
            # Wait for next frame
            ret = sdk.WaitForAcquisition()
            if ret not in acq_ok:
                print(f"WaitForAcquisition failed: {ret}")
                break

            # Get oldest frame from circular buffer
            ret, arr = sdk.GetOldestImage16(xpixels)
            if ret not in acq_ok:
                print(f"GetOldestImage16 failed: {ret}")
                break
            frames += 1

            # Phase tags — read 3, take first consecutive matching pair
            raw = reader.read_tags(3)
            if raw[0] == raw[1]:
                tags = raw[:2]
            else:
                tags = raw[1:]

            if tags[0] != tags[1]:
                discarded += 1
                continue

            if tags[0] == 1:
                on_count += 1
            else:
                off_count += 1

            if on_count > 0 and off_count > 0:
                on_count -= 1
                off_count -= 1
                pairs += 1
    finally:
        sdk.AbortAcquisition()

    elapsed = time.perf_counter() - t0
    print(f"  Frames: {frames}")
    print(f"  Pairs:  {pairs}")
    print(f"  Discarded: {discarded}")
    print(f"  Time:   {elapsed:.3f} s")
    print(f"  FPS:    {frames / elapsed:.1f}")
    print(f"  Per pair: {elapsed / max(pairs, 1) * 1000:.1f} ms")


def test_batch_read(sdk, codes, errors, xpixels, reader):
    """Batch approach: accumulate frames in buffer, read all at once."""
    print("\n--- BATCH READ mode (proposed v2) ---")

    acq_ok = {
        errors.Error_Codes.DRV_SUCCESS,
        errors.Error_Codes.DRV_TEMPERATURE_STABILIZED,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_REACHED,
        errors.Error_Codes.DRV_TEMPERATURE_DRIFT,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_STABILIZED,
    }

    sdk.SetAcquisitionMode(5)  # RUN_TILL_ABORT

    # We need ~200 frames for 100 pairs. Request more to handle discards.
    n_frames_target = N_PAIRS * 3  # generous buffer

    # Arm once
    ret = sdk.PrepareAcquisition()
    if ret != errors.Error_Codes.DRV_SUCCESS:
        print(f"PrepareAcquisition failed: {ret}")
        return
    ret = sdk.StartAcquisition()
    if ret != errors.Error_Codes.DRV_SUCCESS:
        print(f"StartAcquisition failed: {ret}")
        return

    reader.drain()
    t0 = time.perf_counter()

    # Wait for frames to accumulate
    # At 500 Hz, n_frames_target frames take n_frames_target * 2 ms
    wait_s = (n_frames_target * 2.0) / 1000.0 + 0.1  # add 100 ms margin
    time.sleep(wait_s)

    # Check how many frames are available
    ret, first, last = sdk.GetNumberNewImages()
    if ret != errors.Error_Codes.DRV_SUCCESS:
        print(f"GetNumberNewImages failed: {ret}")
        sdk.AbortAcquisition()
        return

    n_available = last - first + 1
    print(f"  Waited {wait_s:.3f} s, {n_available} frames available (first={first}, last={last})")

    # Read all frames in one bulk call
    total_pixels = n_available * xpixels
    t_read_start = time.perf_counter()
    ret, arr, validfirst, validlast = sdk.GetImages16(first, last, total_pixels)
    t_read_end = time.perf_counter()

    sdk.AbortAcquisition()

    if ret not in acq_ok:
        print(f"GetImages16 failed: {ret}")
        return

    n_read = validlast - validfirst + 1
    print(f"  Bulk read {n_read} frames in {(t_read_end - t_read_start)*1000:.1f} ms")

    # Read 2*N + 1 tags — one extra to handle 0 or 1 pre-trigger offset
    n_tags = n_read * 2 + 1
    t_tags_start = time.perf_counter()
    all_tags = reader.read_tags(n_tags)
    t_tags_end = time.perf_counter()
    print(f"  Bulk read {len(all_tags)} tags in {(t_tags_end - t_tags_start)*1000:.1f} ms")

    # Try both alignments (offset 0 and 1), pick the one with fewer discards
    frames = np.array(arr, dtype=np.float64).reshape(n_read, xpixels)
    best_offset = 0
    best_matched = 0
    for offset in (0, 1):
        pairs_view = all_tags[offset:offset + n_read * 2].reshape(n_read, 2)
        n_matched = int((pairs_view[:, 0] == pairs_view[:, 1]).sum())
        print(f"  Offset {offset}: {n_matched}/{n_read} matched ({n_read - n_matched} discards)")
        if n_matched > best_matched:
            best_matched = n_matched
            best_offset = offset

    tag_pairs = all_tags[best_offset:best_offset + n_read * 2].reshape(n_read, 2)
    print(f"  Using offset {best_offset}")

    # Process: matched pairs only
    matched_mask = tag_pairs[:, 0] == tag_pairs[:, 1]
    matched_frames = frames[matched_mask]
    matched_tags = tag_pairs[matched_mask, 0]
    discarded = n_read - matched_mask.sum()

    on_frames = matched_frames[matched_tags == 1]
    off_frames = matched_frames[matched_tags == 0]

    n_pairs = min(len(on_frames), len(off_frames), N_PAIRS)

    elapsed = time.perf_counter() - t0
    print(f"  Total frames: {n_read}")
    print(f"  Matched: {matched_mask.sum()} ({len(on_frames)} ON, {len(off_frames)} OFF)")
    print(f"  Pairs:  {n_pairs}")
    print(f"  Discarded: {discarded}")
    print(f"  Total time: {elapsed:.3f} s (including {wait_s:.3f} s accumulation)")
    print(f"  Read+process: {(t_read_end - t_read_start + t_tags_end - t_tags_start)*1000:.1f} ms")
    print(f"  FPS (effective): {n_read / elapsed:.1f}")

    if n_pairs > 0:
        delta = (on_frames[:n_pairs] - off_frames[:n_pairs]) / np.maximum(off_frames[:n_pairs], 1.0)
        mean_delta = delta.mean(axis=0)
        print(f"  Mean delta-OD range: [{mean_delta.min():.6f}, {mean_delta.max():.6f}]")


def main():
    from pyAndorSDK2 import atmcd, atmcd_codes, atmcd_errors

    sdk = atmcd(SDK_PATH)
    codes = atmcd_codes
    errors = atmcd_errors

    xpixels = init_camera(sdk, codes, errors)
    reader = make_phase_reader()

    try:
        test_single_scan(sdk, codes, errors, xpixels, reader)

        # Small pause between tests
        time.sleep(1)

        test_run_till_abort(sdk, codes, errors, xpixels, reader)

        time.sleep(1)

        test_batch_read(sdk, codes, errors, xpixels, reader)
    finally:
        reader.stop()
        sdk.ShutDown()
        print("\nCamera shut down.")


if __name__ == "__main__":
    main()
