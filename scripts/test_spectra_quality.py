"""Quick test: acquire a few spectra and plot them.

Compares Single Scan vs Run Till Abort to check if readout speed affects signal.

    uv run python scripts/test_spectra_quality.py
"""

from __future__ import annotations

import time
import sys
import numpy as np
import matplotlib.pyplot as plt

SDK_PATH = r"C:\Program Files\Andor SDK"


def init_camera(sdk, codes, errors):
    ret = sdk.Initialize(SDK_PATH)
    if ret != errors.Error_Codes.DRV_SUCCESS:
        print(f"Initialize failed: {ret}")
        sys.exit(1)

    ret, xpixels, ypixels = sdk.GetDetector()
    print(f"Camera: {xpixels}x{ypixels}")

    sdk.SetReadMode(codes.Read_Mode.FULL_VERTICAL_BINNING)
    sdk.SetTriggerMode(codes.Trigger_Mode.EXTERNAL)
    sdk.SetExposureTime(0.002)
    sdk.SetVSSpeed(0)
    sdk.SetHSSpeed(0, 0)  # 3 MHz
    sdk.SetFVBHBin(1)

    return xpixels


def acquire_single_scan(sdk, codes, errors, xpixels, n_frames=10):
    """Acquire n_frames using Single Scan mode (one PrepareAcquisition per frame)."""
    print(f"\n--- Single Scan: {n_frames} frames ---")
    acq_ok = {
        errors.Error_Codes.DRV_SUCCESS,
        errors.Error_Codes.DRV_TEMPERATURE_STABILIZED,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_REACHED,
        errors.Error_Codes.DRV_TEMPERATURE_DRIFT,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_STABILIZED,
    }

    sdk.SetAcquisitionMode(codes.Acquisition_Mode.SINGLE_SCAN)
    spectra = []

    for i in range(n_frames):
        sdk.PrepareAcquisition()
        sdk.StartAcquisition()
        ret = sdk.WaitForAcquisition()
        if ret not in acq_ok:
            print(f"  Frame {i}: WaitForAcquisition failed: {ret}")
            break
        ret, arr, vf, vl = sdk.GetImages16(1, 1, xpixels)
        spectra.append(np.array(arr, dtype=np.float64))

    spectra = np.array(spectra)
    print(f"  Shape: {spectra.shape}")
    print(f"  Mean intensity: {spectra.mean():.1f}")
    print(f"  Min: {spectra.min():.1f}, Max: {spectra.max():.1f}")
    return spectra


def acquire_rta_batch(sdk, codes, errors, xpixels, n_frames=10):
    """Acquire n_frames using Run Till Abort + batch read."""
    print(f"\n--- Run Till Abort batch: {n_frames} frames ---")
    acq_ok = {
        errors.Error_Codes.DRV_SUCCESS,
        errors.Error_Codes.DRV_TEMPERATURE_STABILIZED,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_REACHED,
        errors.Error_Codes.DRV_TEMPERATURE_DRIFT,
        errors.Error_Codes.DRV_TEMPERATURE_NOT_STABILIZED,
    }

    sdk.SetAcquisitionMode(5)  # RUN_TILL_ABORT
    sdk.PrepareAcquisition()
    sdk.StartAcquisition()

    # Wait for frames
    wait_s = (n_frames * 2.0) / 1000.0 + 0.1
    time.sleep(wait_s)

    ret, first, last = sdk.GetNumberNewImages()
    n_avail = last - first + 1 if ret == errors.Error_Codes.DRV_SUCCESS else 0
    print(f"  {n_avail} frames available after {wait_s:.3f}s wait")

    n_read = min(n_avail, n_frames)
    ret, arr, vf, vl = sdk.GetImages16(first, first + n_read - 1, n_read * xpixels)
    sdk.AbortAcquisition()

    if ret not in acq_ok:
        print(f"  GetImages16 failed: {ret}")
        return np.empty((0, xpixels))

    spectra = np.array(arr, dtype=np.float64).reshape(n_read, xpixels)
    print(f"  Shape: {spectra.shape}")
    print(f"  Mean intensity: {spectra.mean():.1f}")
    print(f"  Min: {spectra.min():.1f}, Max: {spectra.max():.1f}")
    return spectra


def main():
    from pyAndorSDK2 import atmcd, atmcd_codes, atmcd_errors
    sdk = atmcd(SDK_PATH)
    codes = atmcd_codes
    errors = atmcd_errors

    xpixels = init_camera(sdk, codes, errors)

    try:
        ss_spectra = acquire_single_scan(sdk, codes, errors, xpixels, n_frames=10)
        time.sleep(0.5)
        rta_spectra = acquire_rta_batch(sdk, codes, errors, xpixels, n_frames=10)
    finally:
        sdk.ShutDown()
        print("\nCamera shut down.")

    # Plot comparison
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))

    # Individual spectra
    ax = axes[0, 0]
    for i, s in enumerate(ss_spectra[:5]):
        ax.plot(s, alpha=0.7, label=f"frame {i}")
    ax.set_title("Single Scan — individual frames")
    ax.set_xlabel("Pixel")
    ax.set_ylabel("Counts")
    ax.legend(fontsize=7)

    ax = axes[0, 1]
    for i, s in enumerate(rta_spectra[:5]):
        ax.plot(s, alpha=0.7, label=f"frame {i}")
    ax.set_title("Run Till Abort — individual frames")
    ax.set_xlabel("Pixel")
    ax.set_ylabel("Counts")
    ax.legend(fontsize=7)

    # Mean comparison
    ax = axes[1, 0]
    if len(ss_spectra) > 0:
        ax.plot(ss_spectra.mean(axis=0), label=f"Single Scan mean (n={len(ss_spectra)})")
    if len(rta_spectra) > 0:
        ax.plot(rta_spectra.mean(axis=0), label=f"RTA batch mean (n={len(rta_spectra)})")
    ax.set_title("Mean spectra comparison")
    ax.set_xlabel("Pixel")
    ax.set_ylabel("Counts")
    ax.legend()

    # Difference
    ax = axes[1, 1]
    if len(ss_spectra) > 0 and len(rta_spectra) > 0:
        diff = rta_spectra.mean(axis=0) - ss_spectra.mean(axis=0)
        ax.plot(diff)
        ax.axhline(0, color="gray", ls="--", alpha=0.5)
        ax.set_title(f"RTA - Single Scan (max |diff| = {np.abs(diff).max():.1f})")
    ax.set_xlabel("Pixel")
    ax.set_ylabel("Counts difference")

    plt.tight_layout()
    plt.savefig("scripts/spectra_comparison.png", dpi=150)
    print("\nPlot saved to scripts/spectra_comparison.png")
    plt.show()


if __name__ == "__main__":
    main()
