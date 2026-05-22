"""From a chopper sweep CSV, extract per-pair contrast noise and extrapolate
to predict precision at any choice of (samples_per_phase, pairs_per_sample).

The CSV has columns: contrast_mean_pct, contrast_std_pct, samples_used,
pairs_per_sample_target. Each row gave us 10 sample-means, each averaged over
200 pairs. The std across those 10 sample-means tells us the spread of a
200-pair mean.

We use the central-limit relationship:
    σ_per_pair  =  σ_200_pair_mean × sqrt(200)
and then for any N pairs in a single sample:
    σ_N_pair_mean = σ_per_pair / sqrt(N)
and for K samples averaged:
    σ_total = σ_N_pair_mean / sqrt(K)

We restrict to "locked" rows (low std) to avoid contaminating the per-pair
variance estimate with chopper-transition noise.
"""

import csv
import sys
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = Path("chopper_fine_sweep_final.csv")

    if not csv_path.exists():
        # fall back to the previous run's CSV
        alt = Path("chopper_fine_sweep.csv")
        if alt.exists():
            csv_path = alt
            print(f"Note: using {alt} (final not present)")
        else:
            print(f"ERROR: no CSV at {csv_path} or {alt}")
            return 1

    rows = []
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            try:
                rows.append({
                    "phase": float(r["phase_deg"]),
                    "c_mean": float(r["contrast_mean_pct"]),
                    "c_std": float(r["contrast_std_pct"]),
                    "n_samples": int(r["samples_used"]),
                    "n_pairs": int(r["pairs_per_sample_target"]),
                })
            except (ValueError, KeyError):
                continue

    if not rows:
        print(f"ERROR: no usable rows in {csv_path}")
        return 1

    # Locked rows: contrast_std_pct < 2% AND contrast magnitude > 5% (real signal)
    locked = [r for r in rows
              if r["c_std"] > 0 and r["c_std"] < 2.0
              and abs(r["c_mean"]) > 5.0
              and r["n_samples"] >= 5]

    print(f"\nLoaded {len(rows)} rows from {csv_path}")
    print(f"Locked rows (std<2%, |C|>5%, n>=5): {len(locked)}")

    if not locked:
        print("Not enough locked rows.")
        return 1

    pairs_each = locked[0]["n_pairs"]
    stds = np.array([r["c_std"] for r in locked])

    # σ of a single N-pair sample-mean = σ_per_pair / sqrt(N)
    # The recorded c_std is std of K such sample-means, but since each sample
    # is already a mean of N pairs, the c_std itself IS the σ_N_pair_mean
    # (not divided by sqrt(K)). The K-sample averaging would further divide it.
    sigma_per_sample = float(np.median(stds))   # median of 200-pair sample stds
    sigma_per_pair = sigma_per_sample * np.sqrt(pairs_each)

    print(f"\nMedian σ across 10 samples (each = mean of {pairs_each} pairs): {sigma_per_sample:.3f}% contrast")
    print(f"Extracted σ for a SINGLE PAIR (1 ON+OFF pair):              {sigma_per_pair:.2f}% contrast")
    print()
    print(f"{'='*70}")
    print(f"Predicted precision σ at different (N pairs, K samples)")
    print(f"{'='*70}")
    print(f"{'pairs N':>8s}  {'samples K':>10s}  {'σ contrast%':>14s}  {'acq time/phase':>15s}")
    print("-" * 70)
    for n_pairs in [20, 50, 100, 200, 500, 1000]:
        for k_samples in [1, 3, 10]:
            # Std of K averaged samples each averaging N pairs
            sigma_total = sigma_per_pair / np.sqrt(n_pairs * k_samples)
            acq_s = k_samples * n_pairs * 0.004  # 4 ms per pair at 250 Hz chopper
            print(f"{n_pairs:8d}  {k_samples:10d}  {sigma_total:13.3f}%   {acq_s:14.2f} s")
    print()
    print(f"Time-per-phase budget includes dwell + lock-wait (~3-5 s)")
    print(f"on top of the acquisition time above.")
    print()
    print(f"For a 0.25° sweep (1440 points), full sweep time estimates:")
    print(f"{'='*70}")
    print(f"{'pairs':>8s}  {'samples':>8s}  {'σ%':>8s}  {'per-phase':>10s}  {'total time':>12s}")
    print("-" * 70)
    for n_pairs, k_samples in [(50,1), (100,1), (200,1), (50,3), (100,3), (200,3)]:
        sigma_total = sigma_per_pair / np.sqrt(n_pairs * k_samples)
        acq_s = k_samples * n_pairs * 0.004
        # Assume 4 s dwell+lock with continuous streaming
        per_phase = acq_s + 4.0
        total_s = per_phase * 1440
        if total_s < 3600:
            total_str = f"{total_s/60:.0f} min"
        else:
            total_str = f"{total_s/3600:.1f} h"
        print(f"{n_pairs:8d}  {k_samples:8d}  {sigma_total:7.2f}%  {per_phase:9.1f}s  {total_str:>12s}")

    # Practical recommendation
    print()
    print("=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    target_sigma = 1.0  # 1% contrast precision
    # Solve for N (with K=1): sigma_per_pair / sqrt(N) <= target_sigma
    # → N >= (sigma_per_pair / target_sigma)^2
    n_required = int(np.ceil((sigma_per_pair / target_sigma)**2))
    acq_required = n_required * 0.004
    print(f"To achieve σ ≤ {target_sigma}% contrast with K=1 sample:")
    print(f"  N ≥ {n_required} pairs ({acq_required:.2f} s acquisition)")
    print()
    target_sigma_2 = 2.0
    n_required_2 = int(np.ceil((sigma_per_pair / target_sigma_2)**2))
    print(f"To achieve σ ≤ {target_sigma_2}% contrast with K=1 sample:")
    print(f"  N ≥ {n_required_2} pairs ({n_required_2 * 0.004:.2f} s acquisition)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
