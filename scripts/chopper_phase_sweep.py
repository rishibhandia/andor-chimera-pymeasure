"""End-to-end phase sweep for chopper_2x2 setup.

At each phase point: set chopper phase, then start camera + phase reader (Fire
trigger), collect N samples of M pairs each in sequence, then abort. Move to
the next phase and repeat with a fresh camera+DAQ session. Each phase is its
own stream session — no continuous streaming across phases.

CSV is written incrementally so partial data survives Ctrl+C. Close andor_qt
GUI before running — the camera SDK locks exclusively.

Example:
  uv run python scripts/chopper_phase_sweep.py \\
      --sweep-port COM4 --slave-port COM3 \\
      --from 0 --to 357.5 --step 2.5 \\
      --samples-per-phase 10 --pairs-per-sample 200 \\
      --dwell 1.0 --out chopper_fine_sweep.csv
"""

from __future__ import annotations

import argparse
import atexit
import csv
import os
import signal
import sys
import time
from pathlib import Path

import numpy as np
import serial

# Force UTF-8 stdout on Windows so degree signs etc. don't crash the script.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ["ANDOR_MOCK"] = ""


# ---------------------------------------------------------------------------
# Bulletproof camera shutdown.
# The Andor camera SDK locks the DLL exclusively — if a Python process exits
# without calling .shutdown(), the SDK is wedged until reboot/replug. So:
#   1. Stash the camera object in a module global as soon as it's initialized.
#   2. atexit.register() a cleanup that runs at ANY interpreter exit path —
#      clean return, sys.exit, uncaught exception, signal-induced exit.
#   3. Install signal handlers for SIGINT, SIGBREAK, SIGTERM that raise
#      KeyboardInterrupt so the main loop unwinds and try/finally runs.
# ---------------------------------------------------------------------------

_camera_for_cleanup = None


def _emergency_camera_shutdown():
    global _camera_for_cleanup
    cam = _camera_for_cleanup
    if cam is None:
        return
    _camera_for_cleanup = None  # avoid double-shutdown
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
    print(f"\n[!] Received signal {signum}, attempting graceful shutdown...",
          flush=True)
    raise KeyboardInterrupt()


for _sig_name in ("SIGINT", "SIGBREAK", "SIGTERM"):
    _s = getattr(signal, _sig_name, None)
    if _s is not None:
        try:
            signal.signal(_s, _signal_handler)
        except (ValueError, OSError):
            pass

DEVICE = "Astrella_DAQ"
SDK_PATH = r"C:\Program Files\Andor SDK"
SHOTS_PER_FRAME = 2
BAUD = 115200

# Camera settings are now built from CLI args (see build_parser).
# Module-level dict kept for the init_camera helper; populated in main().
CAMERA_SETTINGS: dict = {}


# ---------------------------------------------------------------------------
# Chopper serial
# ---------------------------------------------------------------------------

def chopper_send(ser: serial.Serial, cmd: str) -> str:
    ser.reset_input_buffer()
    ser.write((cmd + "\r").encode("ascii"))
    buf = b""
    deadline = time.time() + 2.0
    while time.time() < deadline:
        chunk = ser.read(256)
        if chunk:
            buf += chunk
            if buf.endswith(b"> "):
                break
        else:
            time.sleep(0.005)
    text = buf.decode("ascii", errors="replace")
    lines = [ln for ln in text.replace("\r", "\n").split("\n") if ln.strip()]
    if lines and lines[0].strip() == cmd:
        lines = lines[1:]
    if lines and lines[-1].strip() == ">":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def open_chopper(port: str) -> serial.Serial:
    s = serial.Serial(port, BAUD, bytesize=8, parity="N", stopbits=1,
                      timeout=0.5, write_timeout=0.5)
    time.sleep(0.05)
    s.reset_input_buffer()
    return s


def wait_for_lock(ser: serial.Serial, max_wait_s: float = 5.0,
                  poll_interval_s: float = 0.1,
                  min_consecutive: int = 1) -> bool:
    """Poll `locked?` until the chopper reports locked, or timeout.

    Per the lock-dynamics test, the PLL flickers briefly after locking, so
    requiring multiple consecutive locks can time out unnecessarily. Default
    to requiring 1 lock — the locked streak that follows is typically ~3 s,
    plenty for a ~0.8 s acquisition.
    """
    deadline = time.time() + max_wait_s
    streak = 0
    while time.time() < deadline:
        resp = chopper_send(ser, "locked?")
        if resp == "1":
            streak += 1
            if streak >= min_consecutive:
                return True
        else:
            streak = 0
        time.sleep(poll_interval_s)
    return False


# ---------------------------------------------------------------------------
# Camera + DAQ
# ---------------------------------------------------------------------------

def init_camera():
    """Initialize camera and register it with the atexit cleanup handler so it
    is always shut down, even on KeyboardInterrupt or uncaught exceptions."""
    global _camera_for_cleanup
    from andor_pymeasure.instruments.andor_camera import AndorCamera
    cam = AndorCamera(sdk_path=SDK_PATH)
    cam.initialize()
    _camera_for_cleanup = cam  # register BEFORE apply_camera_settings can fail
    cam.apply_camera_settings(CAMERA_SETTINGS)
    print(f"Camera ready: {cam._info.xpixels}x{cam._info.ypixels}")
    return cam


def make_phase_reader():
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge
    task = nidaqmx.Task("phase_reader")
    task.di_channels.add_di_chan(f"{DEVICE}/port0/line0")
    task.timing.cfg_samp_clk_timing(
        rate=1000.0,
        source=f"/{DEVICE}/PFI0",
        active_edge=Edge.RISING,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=400000,
    )
    task.triggers.start_trigger.cfg_dig_edge_start_trig(
        trigger_source=f"/{DEVICE}/PFI13",
        trigger_edge=Edge.RISING,
    )
    return task


# ---------------------------------------------------------------------------
# Frame/tag processing — use the SAME function as the andor_qt program
# so the metric is guaranteed identical.
# ---------------------------------------------------------------------------

from andor_qt.ta.acquisition import _process_chopper_frames, last_acquisition_stats
from andor_qt.ta.scan_config import TAScanConfig

def _make_config(n_pairs: int, spf: int) -> TAScanConfig:
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=n_pairs,
        acquisition_mode="chopper_2x2",
        scan_direction="forward",
        sample_name="phase_sweep",
        shots_per_frame=spf,
    )


def read_one_sample(camera, task, n_pairs: int, spf: int, timeout_s: float = 3.0):
    """Wait briefly for ~n_pairs of frames, read them and the matching tags."""
    target_frames = n_pairs * 2
    expected_time = target_frames / 500.0 + 0.05
    time.sleep(expected_time)

    frames, n_chunk = camera.get_buffered_frames()
    if n_chunk == 0:
        time.sleep(0.1)
        frames, n_chunk = camera.get_buffered_frames()
        if n_chunk == 0:
            return None, None

    n_avail = task.in_stream.avail_samp_per_chan
    if n_avail < spf:
        time.sleep(0.05)
        n_avail = task.in_stream.avail_samp_per_chan
        if n_avail < spf:
            return None, None
    n_tags = min(n_chunk * spf, n_avail)
    tags = np.array(
        task.read(number_of_samples_per_channel=n_tags, timeout=timeout_s),
        dtype=np.int8,
    )
    return frames, tags


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def sweep(args):
    print(f"Opening choppers: sweep={args.sweep_port}, slave={args.slave_port}")
    sweep_ch = open_chopper(args.sweep_port)
    slave_ch = open_chopper(args.slave_port) if args.slave_port else None

    print(f"Verifying choppers...")
    print(f"  {args.sweep_port}: {chopper_send(sweep_ch, 'id?')}")
    if slave_ch:
        print(f"  {args.slave_port}: {chopper_send(slave_ch, 'id?')}")

    if args.touch_slave and slave_ch:
        print(f"Setting slave ({args.slave_port}) phase=0 (kept fixed)")
        chopper_send(slave_ch, "phase=0")
    else:
        print(f"Slave ({args.slave_port}) left untouched.")

    # Load dark spectrum if provided — subtracted from ON/OFF means before
    # computing contrast. Acquire it first with scripts/acquire_dark_frame.py
    # while the probe beam is blocked at the source.
    dark = None
    if args.dark_frame:
        dark_path = Path(args.dark_frame)
        if not dark_path.exists():
            print(f"ERROR: dark frame file not found: {dark_path}")
            return
        dark = np.load(dark_path).astype(np.float64)
        print(f"Loaded dark frame: {dark.shape}  mean={dark.mean():.1f}  std={dark.std():.1f}")

    print("Initializing camera (once)...")
    camera = init_camera()

    phases = []
    p = float(args.from_)
    while p <= args.to + 1e-9:
        phases.append(p)
        p += args.step
    n_phases = len(phases)

    spf = SHOTS_PER_FRAME
    out_path = Path(args.out)
    fieldnames = [
        "phase_deg", "on_mean", "on_std", "off_mean", "off_std",
        "contrast_mean_pct", "contrast_std_pct",
        "samples_used", "pairs_per_sample_target",
    ]
    fh = out_path.open("w", newline="")
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    writer.writeheader()
    fh.flush()

    per_phase_acq_s = args.samples_per_phase * args.pairs_per_sample * 2 / 500.0
    est_total_min = n_phases * (args.dwell + per_phase_acq_s + 0.6) / 60.0
    print(f"\nSweep: {n_phases} phase points from {args.from_}° to {args.to}° step {args.step}°")
    print(f"  per phase: {args.samples_per_phase} samples × {args.pairs_per_sample} pairs "
          f"(≈{per_phase_acq_s:.1f}s acq + {args.dwell}s dwell, fresh camera session)")
    print(f"  estimated total: ~{est_total_min:.1f} min")
    print(f"  output: {out_path}\n")

    header = f"{'phase':>7s}  {'ON mean':>9s}  {'OFF mean':>9s}  {'C mean%':>9s}  {'C std%':>8s}  {'n':>4s}"
    print(header)
    print("-" * len(header))

    try:
        sweep_start = time.time()

        for idx, phase in enumerate(phases):
            phase_set = int(round(phase)) % 360
            chopper_send(sweep_ch, f"phase={phase_set}")
            time.sleep(args.dwell)
            # Wait for the chopper PLL to relock (also wait for the slave to
            # follow). Skip the phase if it never locks.
            locked_sweep = wait_for_lock(sweep_ch, max_wait_s=args.lock_timeout)
            locked_slave = True
            if slave_ch is not None:
                locked_slave = wait_for_lock(slave_ch, max_wait_s=args.lock_timeout)
            if not (locked_sweep and locked_slave):
                row = {k: 0 for k in fieldnames}
                row["phase_deg"] = phase
                row["pairs_per_sample_target"] = args.pairs_per_sample
                writer.writerow(row); fh.flush()
                print(f"{phase:7.1f}  SKIPPED — chopper did not lock within {args.lock_timeout}s",
                      flush=True)
                continue

            # Fresh camera + DAQ session for this phase
            task = make_phase_reader()
            task.start()
            camera.start_run_till_abort()
            time.sleep(0.2)
            # Drain any pre-trigger junk
            camera.get_buffered_frames()
            n_avail = task.in_stream.avail_samp_per_chan
            if n_avail > 0:
                task.read(number_of_samples_per_channel=n_avail, timeout=2.0)

            on_means = []
            off_means = []
            cfg = _make_config(args.pairs_per_sample, spf)
            for _ in range(args.samples_per_phase):
                frames, tags = read_one_sample(camera, task, args.pairs_per_sample, spf)
                if frames is None or tags is None or len(tags) < spf:
                    continue
                try:
                    _process_chopper_frames(frames, tags, cfg)
                except RuntimeError:
                    continue
                pump_mean = last_acquisition_stats.get("pump_mean")
                ref_mean = last_acquisition_stats.get("ref_mean")
                if pump_mean is None or ref_mean is None:
                    continue
                pump_arr = np.asarray(pump_mean, dtype=np.float64)
                ref_arr = np.asarray(ref_mean, dtype=np.float64)
                if dark is not None and pump_arr.shape == dark.shape:
                    pump_arr = pump_arr - dark
                    ref_arr = ref_arr - dark
                on_means.append(float(pump_arr.mean()))
                off_means.append(float(ref_arr.mean()))

            # End session
            try:
                camera.abort_acquisition()
            except Exception:
                pass
            try:
                task.stop()
                task.close()
            except Exception:
                pass

            if not on_means:
                row = {k: 0 for k in fieldnames}
                row["phase_deg"] = phase
                row["pairs_per_sample_target"] = args.pairs_per_sample
                writer.writerow(row); fh.flush()
                print(f"{phase:7.1f}  FAILED — no usable frames at this phase")
                continue

            on_arr = np.array(on_means)
            off_arr = np.array(off_means)
            contrasts = (on_arr - off_arr) / ((on_arr + off_arr) / 2) * 100

            row = {
                "phase_deg": phase,
                "on_mean": float(on_arr.mean()),
                "on_std": float(on_arr.std()),
                "off_mean": float(off_arr.mean()),
                "off_std": float(off_arr.std()),
                "contrast_mean_pct": float(contrasts.mean()),
                "contrast_std_pct": float(contrasts.std()),
                "samples_used": len(on_means),
                "pairs_per_sample_target": args.pairs_per_sample,
            }
            writer.writerow(row); fh.flush()

            elapsed = time.time() - sweep_start
            print(f"{phase:7.1f}  {row['on_mean']:9.1f}  {row['off_mean']:9.1f}  "
                  f"{row['contrast_mean_pct']:+9.2f}  {row['contrast_std_pct']:8.2f}  "
                  f"{row['samples_used']:4d}  "
                  f"[{idx+1}/{n_phases} elapsed {elapsed/60:.1f}m]",
                  flush=True)

    finally:
        global _camera_for_cleanup
        fh.close()
        print("\nShutting down camera...")
        try:
            camera.abort_acquisition()
        except Exception:
            pass
        try:
            camera.shutdown()
            print("  camera shutdown OK")
        except Exception as e:
            print(f"  camera shutdown error: {e}")
        _camera_for_cleanup = None  # already shut down — prevent atexit double-call
        sweep_ch.close()
        if slave_ch:
            slave_ch.close()

    print(f"\nResults at {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sweep-port", required=True)
    p.add_argument("--slave-port", default=None)
    p.add_argument("--touch-slave", action="store_true",
                   help="Set slave phase to 0 at startup (default: leave alone)")
    p.add_argument("--from", dest="from_", type=float, default=0.0)
    p.add_argument("--to", type=float, default=357.5)
    p.add_argument("--step", type=float, default=2.5)
    p.add_argument("--samples-per-phase", type=int, default=10)
    p.add_argument("--pairs-per-sample", type=int, default=200)
    p.add_argument("--dwell", type=float, default=1.0)
    p.add_argument("--lock-timeout", type=float, default=5.0,
                   help="Max seconds to wait for the chopper PLL to relock "
                        "after a phase change (default 5s). Skip the phase if "
                        "it never locks.")
    p.add_argument("--dark-frame", default=None,
                   help="Path to a .npy dark spectrum (acquire with "
                        "scripts/acquire_dark_frame.py while probe is blocked). "
                        "If provided, ON/OFF means are dark-subtracted before "
                        "computing contrast.")
    # Camera settings (defaults match the andor_qt monitor configuration)
    p.add_argument("--exposure", type=float, default=0.0004,
                   help="Exposure time in seconds (default 0.4 ms)")
    p.add_argument("--vs-speed", type=int, default=0,
                   help="VS speed index (default 0 = fastest)")
    p.add_argument("--hs-speed", type=int, default=0,
                   help="HS speed index (default 0 = fastest)")
    p.add_argument("--amp-type", type=int, default=1,
                   help="Amplifier type (default 1 = conventional CCD)")
    p.add_argument("--preamp-gain", type=int, default=0,
                   help="Pre-amp gain index (default 0)")
    p.add_argument("--hbin", type=int, default=8,
                   help="Horizontal binning (default 8)")
    p.add_argument("--vbin", type=int, default=1,
                   help="Vertical binning (default 1)")
    p.add_argument("--trigger-mode", default="fast_external",
                   help="Camera trigger mode (default fast_external)")
    p.add_argument("--out", default="chopper_fine_sweep.csv")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    # Populate the module-level CAMERA_SETTINGS dict that init_camera reads.
    global CAMERA_SETTINGS
    CAMERA_SETTINGS = {
        "trigger_mode": args.trigger_mode,
        "exposure_time": args.exposure,
        "vs_speed_index": args.vs_speed,
        "hs_speed_index": args.hs_speed,
        "amplifier_type": args.amp_type,
        "preamp_gain_index": args.preamp_gain,
        "hbin": args.hbin,
        "vbin": args.vbin,
    }
    sweep(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
