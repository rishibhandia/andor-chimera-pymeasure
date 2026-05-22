"""Acquire a dark spectrum at the same camera settings as the phase sweep.

Block the probe beam at the source BEFORE running this. The camera will sit in
fast_external trigger mode (so the SDG 500 Hz trigger must still be active) and
collect N frames, then average them per pixel and save to a .npy file.

Usage:
  uv run python scripts/acquire_dark_frame.py --frames 500 --out dark.npy
"""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
import time
from pathlib import Path

import numpy as np

# Force UTF-8 stdout so degree signs etc. don't crash on cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ["ANDOR_MOCK"] = ""

# Bulletproof camera shutdown — see scripts/chopper_phase_sweep.py for rationale.
_camera_for_cleanup = None


def _emergency_camera_shutdown():
    global _camera_for_cleanup
    cam = _camera_for_cleanup
    if cam is None:
        return
    _camera_for_cleanup = None
    try:
        cam.abort_acquisition()
    except Exception:
        pass
    try:
        cam.shutdown()
        print("[atexit] camera shutdown OK", flush=True)
    except Exception as e:
        print(f"[atexit] camera shutdown error: {e}", flush=True)


atexit.register(_emergency_camera_shutdown)


def _signal_handler(signum, _frame):
    print(f"\n[!] Received signal {signum}, shutting down...", flush=True)
    raise KeyboardInterrupt()


for _sig_name in ("SIGINT", "SIGBREAK", "SIGTERM"):
    _s = getattr(signal, _sig_name, None)
    if _s is not None:
        try:
            signal.signal(_s, _signal_handler)
        except (ValueError, OSError):
            pass

SDK_PATH = r"C:\Program Files\Andor SDK"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--frames", type=int, default=500,
                        help="Number of frames to average (default 500 = 1 s at 500 Hz)")
    parser.add_argument("--out", default="dark.npy",
                        help="Output .npy path (default dark.npy)")
    parser.add_argument("--exposure", type=float, default=0.0004,
                        help="Exposure time in seconds (default 0.4 ms)")
    parser.add_argument("--vs-speed", type=int, default=0,
                        help="VS speed index (default 0 = fastest)")
    parser.add_argument("--hs-speed", type=int, default=0,
                        help="HS speed index (default 0 = fastest)")
    parser.add_argument("--amp-type", type=int, default=1,
                        help="Amplifier type (default 1 = conventional CCD)")
    parser.add_argument("--preamp-gain", type=int, default=0,
                        help="Pre-amp gain index (default 0)")
    parser.add_argument("--hbin", type=int, default=8,
                        help="Horizontal binning (default 8, matches monitor)")
    parser.add_argument("--vbin", type=int, default=1,
                        help="Vertical binning (default 1)")
    parser.add_argument("--trigger-mode", default="fast_external",
                        help="Trigger mode (default fast_external)")
    args = parser.parse_args()

    camera_settings = {
        "trigger_mode": args.trigger_mode,
        "exposure_time": args.exposure,
        "vs_speed_index": args.vs_speed,
        "hs_speed_index": args.hs_speed,
        "amplifier_type": args.amp_type,
        "preamp_gain_index": args.preamp_gain,
        "hbin": args.hbin,
        "vbin": args.vbin,
    }

    from andor_pymeasure.instruments.andor_camera import AndorCamera

    global _camera_for_cleanup
    print("Initializing camera...")
    cam = AndorCamera(sdk_path=SDK_PATH)
    cam.initialize()
    _camera_for_cleanup = cam  # register for atexit cleanup
    cam.apply_camera_settings(camera_settings)
    print(f"Camera ready: {cam._info.xpixels}x{cam._info.ypixels}")
    print(f"Settings: {camera_settings}")
    print()
    print("**** PROBE BEAM MUST BE BLOCKED RIGHT NOW ****")
    print("(camera is in fast_external trigger — SDG must still be running)")
    print()

    try:
        cam.start_run_till_abort()
        time.sleep(0.3)
        cam.get_buffered_frames()  # drain pre-trigger junk

        target_time = args.frames / 500.0 + 0.5
        print(f"Acquiring ~{args.frames} frames (~{target_time:.1f} s)...")
        time.sleep(target_time)

        frames, n = cam.get_buffered_frames()
        if n == 0:
            print("ERROR: no frames acquired. Check camera trigger and SDG.")
            return 2

        print(f"Got {n} frames, shape {frames.shape}")
        dark = frames.astype(np.float64).mean(axis=0)
        print(f"Dark spectrum mean = {dark.mean():.1f}  std = {dark.std():.1f}  min = {dark.min():.0f}  max = {dark.max():.0f}")

        out_path = Path(args.out)
        np.save(out_path, dark)
        print(f"Wrote {out_path}  ({out_path.stat().st_size} bytes)")

    finally:
        global _camera_for_cleanup
        try:
            cam.abort_acquisition()
        except Exception:
            pass
        print("Shutting down camera...")
        try:
            cam.shutdown()
            print("  camera shutdown OK")
        except Exception as e:
            print(f"  camera shutdown error: {e}")
        _camera_for_cleanup = None  # avoid atexit double-call

    return 0


if __name__ == "__main__":
    sys.exit(main())
