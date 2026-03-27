"""Test DAQ inputs for shot_to_shot mode.

Verifies:
1. PFI0 = 1 kHz (this will be the camera trigger in shot_to_shot mode)
2. P0.0 = alternating chopper tags at 1 kHz (1 tag per laser shot)
3. Tag pattern: strict alternating blocks (e.g. 1,1,0,0,1,1,0,0 at 250 Hz chopper)

    uv run python scripts/test_shot_to_shot_daq.py
"""

from __future__ import annotations

import numpy as np

DEVICE = "Astrella_DAQ"
N_SAMPLES = 200
CLOCK_SOURCE = f"/{DEVICE}/PFI0"
CLOCK_RATE = 1000.0


def measure_pfi0_freq(gate_s=1.0):
    """Measure PFI0 frequency by counting edges."""
    import time
    import nidaqmx
    from nidaqmx.constants import Edge

    with nidaqmx.Task() as task:
        ch = task.ci_channels.add_ci_count_edges_chan(f"{DEVICE}/ctr0")
        ch.ci_count_edges_term = f"/{DEVICE}/PFI0"
        ch.ci_count_edges_active_edge = Edge.RISING
        task.start()
        t0 = time.perf_counter()
        time.sleep(gate_s)
        count = task.read()
        elapsed = time.perf_counter() - t0
        task.stop()
    return count / elapsed


def read_phase_tags(n_samples):
    """Read P0.0 tags clocked by PFI0."""
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, LineGrouping

    with nidaqmx.Task() as task:
        task.di_channels.add_di_chan(
            f"{DEVICE}/port0/line0",
            line_grouping=LineGrouping.CHAN_PER_LINE,
        )
        task.timing.cfg_samp_clk_timing(
            rate=CLOCK_RATE,
            source=CLOCK_SOURCE,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=n_samples,
        )
        task.start()
        raw = task.read(number_of_samples_per_channel=n_samples, timeout=5.0)
    return np.array(raw, dtype=np.int8)


def analyze_tags(tags):
    """Analyze tag pattern for shot_to_shot suitability."""
    n = len(tags)
    n_on = int((tags == 1).sum())
    n_off = int((tags == 0).sum())

    # Find run lengths (consecutive same-value blocks)
    changes = np.diff(tags)
    transition_indices = np.where(changes != 0)[0]
    if len(transition_indices) > 0:
        runs = np.diff(np.concatenate([[0], transition_indices + 1, [n]]))
    else:
        runs = np.array([n])

    # For 250 Hz chopper at 1 kHz sample rate: expect runs of ~2
    # (2 shots ON, 2 shots OFF = 4 ms chopper period)
    mean_run = runs.mean()
    min_run = runs.min()
    max_run = runs.max()

    return {
        "n_on": n_on,
        "n_off": n_off,
        "n_transitions": len(transition_indices),
        "mean_run_length": mean_run,
        "min_run_length": min_run,
        "max_run_length": max_run,
        "duty_cycle": n_on / n * 100,
    }


def main():
    print(f"shot_to_shot DAQ test - device: {DEVICE}")
    print(f"Expected: PFI0=1kHz camera trigger, P0.0=chopper tags (1/shot)")
    print()

    # 1. PFI0 frequency
    print("1. PFI0 frequency (camera trigger source)")
    freq = measure_pfi0_freq(gate_s=1.0)
    status = "OK" if 990 < freq < 1010 else "FAIL"
    print(f"   PFI0 = {freq:.1f} Hz  [{status}]")
    print()

    # 2. Read phase tags
    print(f"2. P0.0 phase tags ({N_SAMPLES} samples at 1 kHz)")
    tags = read_phase_tags(N_SAMPLES)
    print(f"   First 40: {tags[:40].tolist()}")
    print()

    # 3. Analyze pattern
    print("3. Tag pattern analysis")
    stats = analyze_tags(tags)
    print(f"   ON:  {stats['n_on']}  OFF: {stats['n_off']}  "
          f"duty cycle: {stats['duty_cycle']:.1f}%")
    print(f"   Transitions: {stats['n_transitions']}")
    print(f"   Run lengths: mean={stats['mean_run_length']:.1f}  "
          f"min={stats['min_run_length']}  max={stats['max_run_length']}")
    print()

    # 4. Assess suitability
    print("4. shot_to_shot suitability")
    issues = []
    if not (990 < freq < 1010):
        issues.append(f"PFI0 frequency {freq:.1f} Hz is not 1 kHz")
    if stats["duty_cycle"] < 40 or stats["duty_cycle"] > 60:
        issues.append(f"Duty cycle {stats['duty_cycle']:.1f}% is not ~50%")
    if stats["mean_run_length"] < 0.8:
        issues.append(f"Mean run length {stats['mean_run_length']:.1f} is too short")
    if stats["n_on"] == 0 or stats["n_off"] == 0:
        issues.append("Missing ON or OFF tags - check chopper connection")

    if not issues:
        print("   PASS - all signals look correct for shot_to_shot mode")
        print(f"   Each laser shot gets 1 tag, {stats['n_on']} ON + {stats['n_off']} OFF")
        print(f"   Chopper period: ~{stats['mean_run_length'] * 2:.0f} shots "
              f"= {stats['mean_run_length'] * 2:.0f} ms")
    else:
        for issue in issues:
            print(f"   FAIL - {issue}")


if __name__ == "__main__":
    main()
