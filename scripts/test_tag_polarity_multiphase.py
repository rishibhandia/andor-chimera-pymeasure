"""Test tag-polarity stability at multiple chopper phases.

For each requested chopper phase:
  1. Send phase=N to MC2000B over COM4
  2. Wait for PLL lock (poll locked? until 1 or timeout)
  3. Run N_TRIALS Fire-trigger-synchronized acquisitions
  4. Record ON/OFF means and which one is brighter
  5. Verify the parity is stable across trials

Camera settings match the user's monitor config:
  trigger_mode: fast_external
  exposure_time: 0.4 ms
  vs/hs speed: 0 (fastest)
  amplifier: conventional
  preamp gain: 0
  hbin: 8
  spectrograph: grating=1, wavelength=650 nm

Run:
  uv run python scripts/test_tag_polarity_multiphase.py --phases 19,20,21,12,14,32
"""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
import time

import numpy as np
import serial

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ["ANDOR_MOCK"] = ""

DEVICE = "Astrella_DAQ"
SDK_PATH = r"C:\Program Files\Andor SDK"
SHOTS_PER_FRAME = 2
N_AVERAGES = 50
BAUD = 115200

# Module-level dict — populated from CLI args in main().
CAMERA_SETTINGS: dict = {}

# Bulletproof camera shutdown
_camera_for_cleanup = None


def _emergency_shutdown():
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


atexit.register(_emergency_shutdown)


def _sig(signum, _frame):
    print(f"\n[!] signal {signum}", flush=True)
    raise KeyboardInterrupt()


for _n in ("SIGINT", "SIGBREAK", "SIGTERM"):
    _s = getattr(signal, _n, None)
    if _s is not None:
        try:
            signal.signal(_s, _sig)
        except (ValueError, OSError):
            pass


# ---------- Chopper helpers ----------

def cs_send(s: serial.Serial, cmd: str) -> str:
    s.reset_input_buffer()
    s.write((cmd + "\r").encode("ascii"))
    buf = b""
    deadline = time.time() + 1.5
    while time.time() < deadline:
        chunk = s.read(256)
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


def wait_lock(s: serial.Serial, timeout_s: float = 10.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if cs_send(s, "locked?") == "1":
            return True
        time.sleep(0.1)
    return False


# ---------- Camera / DAQ ----------

def init_camera():
    global _camera_for_cleanup
    from andor_pymeasure.instruments.andor_camera import AndorCamera
    cam = AndorCamera(sdk_path=SDK_PATH)
    cam.initialize()
    _camera_for_cleanup = cam
    cam.apply_camera_settings(CAMERA_SETTINGS)
    print(f"Camera ready: {cam._info.xpixels}x{cam._info.ypixels}")
    return cam


def init_spectrograph(wavelength_nm: float, grating: int):
    from andor_pymeasure.instruments.andor_spectrograph import AndorSpectrograph
    sp = AndorSpectrograph(sdk_path=SDK_PATH)
    sp.initialize()
    print(f"Spectrograph ready: {sp.info}")
    print(f"Setting grating={grating}...")
    sp.grating = grating
    print(f"Setting wavelength={wavelength_nm} nm...")
    sp.wavelength = wavelength_nm
    actual_wl = sp.wavelength
    actual_g = sp.grating
    print(f"  actual: grating={actual_g}, wavelength={actual_wl}")
    return sp


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
        samps_per_chan=200000,
    )
    task.triggers.start_trigger.cfg_dig_edge_start_trig(
        trigger_source=f"/{DEVICE}/PFI13",
        trigger_edge=Edge.RISING,
    )
    return task


def split_on_off(frames, tags, spf=2):
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
    usable = min(len(frames), (len(tags) - best_offset) // spf)
    tag_groups = tags[best_offset:best_offset + usable * spf].reshape(usable, spf)
    f = frames[:usable]
    matched = (tag_groups == tag_groups[:, :1]).all(axis=1)
    on = f[matched & (tag_groups[:, 0] == 1)]
    off = f[matched & (tag_groups[:, 0] == 0)]
    return on, off


def run_trial(camera, n_averages=N_AVERAGES, spf=SHOTS_PER_FRAME):
    """One Fire-trigger acquisition with fresh DAQ task."""
    task = make_phase_reader()
    task.start()
    camera.start_run_till_abort()

    target_frames = n_averages * 2 + 10
    time.sleep(target_frames * spf / 1000.0 + 0.05)
    frames, n_chunk = camera.get_buffered_frames()
    if n_chunk == 0:
        camera.abort_acquisition()
        task.stop(); task.close()
        return None

    n_avail = task.in_stream.avail_samp_per_chan
    if n_avail < spf:
        camera.abort_acquisition()
        task.stop(); task.close()
        return None
    tags = np.array(task.read(number_of_samples_per_channel=n_avail, timeout=5.0),
                    dtype=np.int8)
    camera.abort_acquisition()
    task.stop(); task.close()

    on, off = split_on_off(frames, tags, spf)
    if len(on) == 0 or len(off) == 0:
        return None
    return {"on": float(on.mean()), "off": float(off.mean()),
            "n_on": len(on), "n_off": len(off)}


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--phases", default="19,20,21,12,14,32",
                        help="Comma-separated phase values")
    parser.add_argument("--trials", type=int, default=5,
                        help="Trials per phase (default 5)")
    parser.add_argument("--wavelength", type=float, default=650.0)
    parser.add_argument("--grating", type=int, default=1)
    parser.add_argument("--chopper-port", default="COM4")
    # Camera settings (default to monitor configuration)
    parser.add_argument("--exposure", type=float, default=0.0004,
                        help="Exposure time in seconds (default 0.4 ms)")
    parser.add_argument("--vs-speed", type=int, default=0)
    parser.add_argument("--hs-speed", type=int, default=0)
    parser.add_argument("--amp-type", type=int, default=1)
    parser.add_argument("--preamp-gain", type=int, default=0)
    parser.add_argument("--hbin", type=int, default=8)
    parser.add_argument("--vbin", type=int, default=1)
    parser.add_argument("--trigger-mode", default="fast_external")
    args = parser.parse_args()

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

    phases = [int(p) for p in args.phases.split(",")]
    print(f"Testing phases: {phases}")
    print(f"  Trials per phase: {args.trials}")
    print(f"  Camera settings: {CAMERA_SETTINGS}")
    print(f"  Spectrograph: grating={args.grating}, wavelength={args.wavelength} nm")
    print()

    ch = serial.Serial(args.chopper_port, BAUD, timeout=0.5)
    time.sleep(0.05)
    ch.reset_input_buffer()
    print(f"Chopper: {cs_send(ch, 'id?')}")
    print()

    print("Initializing camera + spectrograph...")
    camera = init_camera()
    spec = init_spectrograph(args.wavelength, args.grating)

    print()
    header = f"{'phase':>5s}  {'trial':>5s}  {'ON':>8s}  {'OFF':>8s}  {'diff':>10s}  {'C%':>8s}  {'verdict':<10s}"
    print(header)
    print("-" * len(header))

    summary = []
    try:
        for ph in phases:
            cs_send(ch, f"phase={ph}")
            time.sleep(0.5)
            locked = wait_lock(ch, timeout_s=10.0)
            if not locked:
                print(f"{ph:>5d}    LOCK FAILED -- skipping")
                continue

            on_bright_count = 0
            off_bright_count = 0
            trial_data = []
            for t in range(args.trials):
                r = run_trial(camera)
                if r is None:
                    print(f"{ph:>5d}  {t+1:>5d}    no data")
                    continue
                diff = r["on"] - r["off"]
                denom = (r["on"] + r["off"]) / 2
                contrast = (diff / denom * 100) if denom else 0
                bright = "ON" if r["on"] > r["off"] else "OFF"
                if bright == "ON":
                    on_bright_count += 1
                else:
                    off_bright_count += 1
                print(f"{ph:>5d}  {t+1:>5d}  {r['on']:8.1f}  {r['off']:8.1f}  "
                      f"{diff:+10.1f}  {contrast:+8.2f}  {bright + ' bright':<10s}",
                      flush=True)
                trial_data.append((r["on"], r["off"], contrast))
                time.sleep(0.5)

            if not trial_data:
                continue
            on_arr = np.array([d[0] for d in trial_data])
            off_arr = np.array([d[1] for d in trial_data])
            c_arr = np.array([d[2] for d in trial_data])
            stable = (on_bright_count == args.trials) or (off_bright_count == args.trials)
            verdict = ("STABLE ON-bright" if on_bright_count == args.trials
                       else "STABLE OFF-bright" if off_bright_count == args.trials
                       else f"FLIPPED ({on_bright_count}/{off_bright_count})")
            print(f"  -> phase={ph}: {verdict}  "
                  f"mean C={c_arr.mean():+.2f}% +/- {c_arr.std():.2f}%")
            print()
            summary.append({
                "phase": ph,
                "n_trials": len(trial_data),
                "n_on_bright": on_bright_count,
                "n_off_bright": off_bright_count,
                "stable": stable,
                "verdict": verdict,
                "mean_contrast": float(c_arr.mean()),
                "std_contrast": float(c_arr.std()),
                "mean_on": float(on_arr.mean()),
                "mean_off": float(off_arr.mean()),
            })
    finally:
        print()
        print("Shutting down camera + spectrograph...")
        try:
            spec.shutdown()
        except Exception as e:
            print(f"  spec shutdown error: {e}")
        # camera handled by atexit
        ch.close()

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'phase':>5s}  {'verdict':<22s}  {'mean C%':>9s}  {'std%':>6s}  "
          f"{'ON':>8s}  {'OFF':>8s}")
    for s in summary:
        print(f"{s['phase']:>5d}  {s['verdict']:<22s}  "
              f"{s['mean_contrast']:+9.2f}  {s['std_contrast']:6.2f}  "
              f"{s['mean_on']:8.1f}  {s['mean_off']:8.1f}")


if __name__ == "__main__":
    sys.exit(main())
