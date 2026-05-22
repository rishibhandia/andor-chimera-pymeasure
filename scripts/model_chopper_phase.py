"""Model the chopper / laser / camera timing system.

System:
  Chopper:   250 Hz square wave, 50% duty.  Probe transmission = 1 (open) / 0 (closed).
  Laser:     1 kHz pulse train (delta functions, instantaneous).
  Camera:    500 Hz trigger (locked to chopper * 2).
             Exposure window = 0.4 ms per frame.

We sweep the RELATIVE PHASE of the chopper relative to the laser/camera clock
and compute, for each phase, the mean intensity in tag=1 (chopper-says-open)
frames vs tag=0 (chopper-says-closed) frames, then the Michelson contrast.

The tag is derived from sampling the chopper square wave at the same 1 kHz rate
as the laser (PFI0). Two laser pulses fall within each 2 ms camera frame; we
sample the chopper at both — they should agree (matched pair) or be discarded.

This script is pure simulation, no hardware. Outputs a table and a plot PNG.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# --- Constants ---
LASER_HZ = 1000.0
CHOPPER_HZ = 250.0
CAMERA_HZ = 500.0
EXPOSURE_S = 0.0004   # 0.4 ms

# How many chopper cycles to simulate per phase point — enough for statistics.
N_CHOPPER_CYCLES = 500

# Chopper period, camera frame period, laser period
T_CHOPPER = 1.0 / CHOPPER_HZ   # 4 ms
T_FRAME = 1.0 / CAMERA_HZ      # 2 ms
T_LASER = 1.0 / LASER_HZ       # 1 ms


def chopper_value(t: np.ndarray, phase_deg: float, edge_width_us: float = 0.0) -> np.ndarray:
    """Square wave: 1 if in 'open' half-cycle, 0 if 'closed'.

    The phase argument is in degrees of CHOPPER CYCLE (so 360° = 4 ms).
    Optional ``edge_width_us`` (microseconds) gives the slot edge a finite
    rise/fall time (linear transition) to model the optical finite-aperture
    smearing. Default 0 → ideal square wave.
    """
    phase_s = (phase_deg / 360.0) * T_CHOPPER
    # Phase within current chopper cycle, mapped to [0, 1).
    u = ((t - phase_s) / T_CHOPPER) % 1.0
    if edge_width_us <= 0.0:
        return (u < 0.5).astype(float)
    # Linear ramp at edges. Half cycle is 'open'; centered around u=0.25.
    w = edge_width_us * 1e-6 / T_CHOPPER  # edge width in fractional cycle units
    val = np.zeros_like(u)
    # Rising edge from 0 -> w
    rising = u < w
    val[rising] = u[rising] / w
    # Open plateau: w to 0.5 - w/2 (approx)
    open_plateau = (u >= w) & (u < 0.5)
    val[open_plateau] = 1.0
    # Falling edge from 0.5 to 0.5+w
    falling = (u >= 0.5) & (u < 0.5 + w)
    val[falling] = 1.0 - (u[falling] - 0.5) / w
    # Closed plateau: 0.5+w to 1.0
    # already zero
    return val


def simulate_one_phase(phase_deg: float, edge_width_us: float = 0.0):
    """Return (on_mean, off_mean, n_pairs) for one phase point.

    Camera triggers at t = 0, T_FRAME, 2*T_FRAME, ... The exposure window
    of frame k is [k*T_FRAME, k*T_FRAME + EXPOSURE_S]. The laser fires at
    t = m*T_LASER for m=0,1,... — instantaneous delta functions.

    For each camera frame, find which laser pulses fall inside the exposure
    window, and compute the *signal* as the chopper transmission at each
    pulse arrival time (since the laser pulse is instantaneous, the camera
    integrates chopper(t_pulse) * laser_intensity).

    The tag is derived from sampling chopper(t) at the same 1 kHz rate as
    the laser (PFI0). For each frame we take the 2 samples that occur during
    that frame (in 2 ms there are 2 laser/PFI0 events). If the 2 tags agree,
    the frame is "matched" and assigned to ON (tag=1) or OFF (tag=0).
    """
    total_time = N_CHOPPER_CYCLES * T_CHOPPER
    n_frames = int(total_time / T_FRAME)
    # Camera frame starts
    frame_starts = np.arange(n_frames) * T_FRAME

    # Laser pulse times (1 kHz, starting at t=0)
    n_laser = int(total_time / T_LASER)
    laser_times = np.arange(n_laser) * T_LASER

    # PFI0 sample times: same as laser times
    pfi0_times = laser_times

    # Chopper value at each PFI0 sample → tags (0 or 1, ideal square wave)
    pfi0_tags = (chopper_value(pfi0_times, phase_deg, 0.0) > 0.5).astype(int)

    # For each frame: find the PFI0 samples within its 2 ms span (2 samples each)
    # AND find which laser pulses are within the 0.4 ms exposure window
    on_signals = []
    off_signals = []
    n_discarded = 0
    for k in range(n_frames):
        t0 = frame_starts[k]
        t1 = t0 + T_FRAME
        exp_end = t0 + EXPOSURE_S

        # PFI0 samples within [t0, t1)
        pfi_in_frame = np.where((pfi0_times >= t0) & (pfi0_times < t1))[0]
        if len(pfi_in_frame) != 2:
            n_discarded += 1
            continue
        tags_this = pfi0_tags[pfi_in_frame]
        if tags_this[0] != tags_this[1]:
            n_discarded += 1
            continue
        tag = int(tags_this[0])

        # Laser pulses within exposure window [t0, exp_end)
        las_in_exp = np.where((laser_times >= t0) & (laser_times < exp_end))[0]
        # Camera signal = sum of chopper transmission values at each pulse
        signal = float(np.sum(
            chopper_value(laser_times[las_in_exp], phase_deg, edge_width_us)
        ))

        if tag == 1:
            on_signals.append(signal)
        else:
            off_signals.append(signal)

    n_on = len(on_signals)
    n_off = len(off_signals)
    if n_on == 0 or n_off == 0:
        return None, None, 0, n_discarded
    return float(np.mean(on_signals)), float(np.mean(off_signals)), min(n_on, n_off), n_discarded


def sweep(args):
    phases = np.arange(args.from_, args.to + 1e-9, args.step)
    print(f"Modeling chopper phase sweep: {len(phases)} points "
          f"from {args.from_}° to {args.to}° step {args.step}°")
    print(f"  Edge width: {args.edge_width_us} us (0 = ideal square wave)")
    print(f"  Chopper {CHOPPER_HZ} Hz, Laser {LASER_HZ} Hz, Camera {CAMERA_HZ} Hz, "
          f"exposure {EXPOSURE_S*1e6:.0f} us")
    print()
    print(f"{'phase':>7s}  {'ON mean':>9s}  {'OFF mean':>9s}  {'contrast%':>10s}  "
          f"{'pairs':>6s}  {'disc':>5s}")
    print("-" * 60)

    rows = []
    for p in phases:
        on_m, off_m, n_pairs, n_disc = simulate_one_phase(p, args.edge_width_us)
        if on_m is None:
            print(f"{p:7.2f}  no pairs")
            continue
        denom = (on_m + off_m) / 2.0
        c = 100.0 * (on_m - off_m) / denom if denom > 0 else 0.0
        rows.append((p, on_m, off_m, c, n_pairs, n_disc))
        print(f"{p:7.2f}  {on_m:9.3f}  {off_m:9.3f}  {c:+10.2f}  "
              f"{n_pairs:6d}  {n_disc:5d}")

    if args.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            arr = np.array(rows)
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(arr[:, 0], arr[:, 3], marker="o", markersize=3, linewidth=0.8)
            ax.axhline(0, color="k", linewidth=0.4, alpha=0.3)
            ax.set_xlabel("Chopper phase (deg)")
            ax.set_ylabel("Michelson contrast (%)")
            ax.set_title(f"Modeled contrast: {CHOPPER_HZ} Hz square + {LASER_HZ} Hz "
                          f"deltas, exposure {EXPOSURE_S*1e6:.0f} us, "
                          f"edge {args.edge_width_us:.1f} us")
            ax.grid(True, alpha=0.3)
            out_png = Path(args.plot)
            fig.tight_layout()
            fig.savefig(out_png, dpi=100)
            print(f"\nSaved plot: {out_png}")
        except ImportError:
            print("\n(matplotlib not available, skipping plot)")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--from", dest="from_", type=float, default=0.0)
    p.add_argument("--to", type=float, default=357.5)
    p.add_argument("--step", type=float, default=2.5)
    p.add_argument("--edge-width-us", type=float, default=0.0,
                   help="Slot edge rise/fall time in microseconds (default 0 = ideal)")
    p.add_argument("--plot", default="model_chopper_phase.png",
                   help="Output PNG path (default model_chopper_phase.png)")
    args = p.parse_args(argv)
    sweep(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
