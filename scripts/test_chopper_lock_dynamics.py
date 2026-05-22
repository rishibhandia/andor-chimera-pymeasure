"""Probe how MC2000B PLL lock behaves after a phase change.

For each test phase: send phase=X, then immediately start polling `locked?` at
~10 Hz for 30 seconds. Record (timestamp, locked) pairs. Compute:
  - time-to-first-lock from the phase-change command
  - fraction of polling time the chopper reported locked
  - number of lock loss events and average lock streak duration

This helps choose minimum dwell + lock-wait parameters for the sweep.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import serial

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BAUD = 115200


def send(s: serial.Serial, cmd: str) -> str:
    s.reset_input_buffer()
    s.write((cmd + "\r").encode("ascii"))
    buf = b""
    deadline = time.time() + 1.0
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


def monitor_one_phase(s: serial.Serial, target: int, duration_s: float,
                      poll_hz: float):
    """Send phase=target, then poll locked? at poll_hz for duration_s."""
    interval = 1.0 / poll_hz
    send(s, f"phase={target}")
    t0 = time.time()
    samples = []  # list of (t_relative, locked_bool)
    while time.time() - t0 < duration_s:
        resp = send(s, "locked?")
        locked = resp == "1"
        samples.append((time.time() - t0, locked))
        time.sleep(max(0, interval - 0.05))  # account for serial round-trip
    return samples


def analyze(samples):
    """Return dict of statistics."""
    if not samples:
        return {}
    times = [s[0] for s in samples]
    locks = [s[1] for s in samples]
    n = len(samples)

    # Time-to-first-lock
    first_lock = next((t for t, l in samples if l), None)

    # Fraction of time reporting locked
    lock_frac = sum(locks) / n

    # Find lock streaks (consecutive Trues) and unlock streaks
    streaks_locked = []
    streaks_unlocked = []
    current_streak = 1
    for i in range(1, n):
        if locks[i] == locks[i - 1]:
            current_streak += 1
        else:
            if locks[i - 1]:
                streaks_locked.append(current_streak)
            else:
                streaks_unlocked.append(current_streak)
            current_streak = 1
    # Final streak
    if locks[-1]:
        streaks_locked.append(current_streak)
    else:
        streaks_unlocked.append(current_streak)

    n_loss_events = sum(1 for i in range(1, n) if locks[i - 1] and not locks[i])

    duration = times[-1] - times[0] if n > 1 else 0

    return {
        "n_samples": n,
        "duration_s": duration,
        "first_lock_s": first_lock,
        "lock_fraction": lock_frac,
        "n_lock_loss_events": n_loss_events,
        "loss_rate_per_s": n_loss_events / duration if duration > 0 else 0,
        "median_locked_streak_s": (sorted(streaks_locked)[len(streaks_locked) // 2] / poll_hz
                                   if streaks_locked else 0),
        "median_unlocked_streak_s": (sorted(streaks_unlocked)[len(streaks_unlocked) // 2] / poll_hz
                                     if streaks_unlocked else 0),
        "max_locked_streak_s": max(streaks_locked) / poll_hz if streaks_locked else 0,
        "max_unlocked_streak_s": max(streaks_unlocked) / poll_hz if streaks_unlocked else 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", default="COM4", help="Chopper COM port")
    parser.add_argument("--phases", default="0,45,90,135,180,225,270,315",
                        help="Comma-separated phase values to test")
    parser.add_argument("--duration", type=float, default=20.0,
                        help="Seconds to monitor each phase (default 20)")
    parser.add_argument("--poll-hz", type=float, default=10.0,
                        help="Lock-query rate in Hz (default 10)")
    parser.add_argument("--out", default="chopper_lock_dynamics.csv")
    args = parser.parse_args()

    global poll_hz
    poll_hz = args.poll_hz
    phases = [int(p) for p in args.phases.split(",")]
    print(f"Testing {len(phases)} phases on {args.port}: {phases}")
    print(f"  Monitor {args.duration} s per phase at {args.poll_hz} Hz poll rate")
    print()

    s = serial.Serial(args.port, BAUD, bytesize=8, parity="N", stopbits=1,
                      timeout=0.5, write_timeout=0.5)
    time.sleep(0.05)
    s.reset_input_buffer()
    print(f"Connected to: {send(s, 'id?')}")
    print()

    headers = ["phase", "n_samples", "duration_s", "first_lock_s",
               "lock_fraction", "n_lock_loss_events", "loss_rate_per_s",
               "median_locked_streak_s", "median_unlocked_streak_s",
               "max_locked_streak_s", "max_unlocked_streak_s"]
    out_path = Path(args.out)
    fh = out_path.open("w", newline="")
    writer = csv.DictWriter(fh, fieldnames=headers)
    writer.writeheader()

    header = f"{'phase':>6s} {'1st-lock':>9s} {'lock-frac':>10s} {'loss-events':>11s} {'med-lock':>9s} {'med-unl':>9s} {'max-lock':>9s} {'max-unl':>9s}"
    print(header)
    print("-" * len(header))

    try:
        for ph in phases:
            samples = monitor_one_phase(s, ph, args.duration, args.poll_hz)
            stats = analyze(samples)
            row = {"phase": ph, **{k: v for k, v in stats.items() if k in headers}}
            writer.writerow(row)
            fh.flush()
            print(f"{ph:6d} "
                  f"{(stats['first_lock_s'] or float('nan')):9.2f} "
                  f"{stats['lock_fraction']:10.2%} "
                  f"{stats['n_lock_loss_events']:11d} "
                  f"{stats['median_locked_streak_s']:9.2f} "
                  f"{stats['median_unlocked_streak_s']:9.2f} "
                  f"{stats['max_locked_streak_s']:9.2f} "
                  f"{stats['max_unlocked_streak_s']:9.2f}",
                  flush=True)
    finally:
        fh.close()
        s.close()

    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
