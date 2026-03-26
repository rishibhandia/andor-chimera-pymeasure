"""Verify chopper_2x2 DAQ wiring.

Expected connections:
  PFI0   ← 1 kHz laser sync
  PFI12  ← SDG 500 Hz camera trigger (divide-by-2 of laser)
  P0.0   ← Chopper controller output (1 = pump-ON, 0 = pump-OFF)

Run:
  uv run python scripts/verify_daq_wiring.py
  uv run python scripts/verify_daq_wiring.py --device Astrella_DAQ
"""

from __future__ import annotations

import argparse
import time

import numpy as np

DEVICE = "Astrella_DAQ"
N_PHASE_SAMPLES = 40
GATE_TIME = 1.0  # seconds for frequency measurement


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def measure_frequency(device: str, pfi: str, gate_time: float = GATE_TIME) -> float:
    """Count rising edges on *pfi* over *gate_time* seconds → Hz."""
    import nidaqmx
    from nidaqmx.constants import Edge

    with nidaqmx.Task() as task:
        ch = task.ci_channels.add_ci_count_edges_chan(f"{device}/ctr0")
        ch.ci_count_edges_term = f"/{device}/{pfi}"
        ch.ci_count_edges_active_edge = Edge.RISING
        task.start()
        t0 = time.perf_counter()
        time.sleep(gate_time)
        count = task.read()
        elapsed = time.perf_counter() - t0
        task.stop()
    return count / elapsed


def read_phase_tags(device: str, n: int = N_PHASE_SAMPLES) -> np.ndarray:
    """Read *n* samples from P0.0 clocked by PFI0 (1 kHz laser sync)."""
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge

    with nidaqmx.Task() as task:
        task.di_channels.add_di_chan(f"{device}/port0/line0")
        task.timing.cfg_samp_clk_timing(
            rate=1000.0,
            source=f"/{device}/PFI0",
            active_edge=Edge.RISING,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=n,
        )
        task.start()
        task.wait_until_done(timeout=5.0)
        data = task.read(number_of_samples_per_channel=n)
    return np.array(data, dtype=np.int8)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_frequencies(device: str) -> bool:
    print("-" * 50)
    print("1. Frequency check")
    ok = True

    print(f"   Measuring PFI0  (expect ~1000 Hz, gate={GATE_TIME:.0f}s) ...", end=" ", flush=True)
    f0 = measure_frequency(device, "PFI0")
    s0 = "OK" if 950 < f0 < 1050 else "FAIL"
    print(f"{f0:.1f} Hz  [{s0}]")
    if s0 == "FAIL":
        ok = False

    print(f"   Measuring PFI12 (expect ~500 Hz,  gate={GATE_TIME:.0f}s) ...", end=" ", flush=True)
    f12 = measure_frequency(device, "PFI12")
    s12 = "OK" if 475 < f12 < 525 else "FAIL"
    print(f"{f12:.1f} Hz  [{s12}]")
    if s12 == "FAIL":
        ok = False

    ratio = f0 / f12 if f12 > 0 else 0.0
    sr = "OK" if 1.98 < ratio < 2.02 else "FAIL"
    print(f"   PFI0 / PFI12 ratio = {ratio:.4f}  (expect exactly 2.0000)  [{sr}]")
    if sr == "FAIL":
        ok = False

    return ok


def check_phase_tags(device: str) -> bool:
    print("-" * 50)
    print(f"2. Phase tags on P0.0  ({N_PHASE_SAMPLES} samples clocked by PFI0)")

    tags = read_phase_tags(device, N_PHASE_SAMPLES)
    print(f"   Raw: {tags.tolist()}")

    transitions = int(np.sum(np.abs(np.diff(tags.astype(int)))))
    n_on  = int(np.sum(tags == 1))
    n_off = int(np.sum(tags == 0))
    print(f"   ON frames: {n_on}  OFF frames: {n_off}  Transitions: {transitions}")

    ok = True
    # Expect roughly equal ON/OFF and ~N/2 transitions (alternating pattern)
    if transitions < N_PHASE_SAMPLES // 4:
        print("   WARN: very few transitions — is the chopper running and P0.0 connected?")
        ok = False
    else:
        print("   Alternating pattern: OK")

    # Check for stuck-high or stuck-low
    if n_on == 0:
        print("   FAIL: P0.0 always LOW — chopper signal absent or wiring issue")
        ok = False
    elif n_off == 0:
        print("   FAIL: P0.0 always HIGH — chopper signal absent or wiring issue")
        ok = False

    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify chopper_2x2 DAQ wiring")
    parser.add_argument("--device", default=DEVICE, help=f"NI DAQ device name (default: {DEVICE})")
    args = parser.parse_args()
    device = args.device

    print(f"\nDAQ wiring verification — device: {device}")
    print(f"Expected: PFI0=1kHz laser, PFI12=500Hz SDG, P0.0=chopper\n")

    try:
        freq_ok = check_frequencies(device)
    except Exception as exc:
        print(f"   ERROR during frequency check: {exc}")
        freq_ok = False

    try:
        phase_ok = check_phase_tags(device)
    except Exception as exc:
        print(f"   ERROR during phase tag check: {exc}")
        phase_ok = False

    print("-" * 50)
    if freq_ok and phase_ok:
        print("PASS -- wiring looks correct for chopper_2x2 mode")
    else:
        print("FAIL -- check connections above")
    print()


if __name__ == "__main__":
    main()
