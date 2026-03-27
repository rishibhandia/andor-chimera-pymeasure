"""Validate readout time formula against SDK GetReadOutTime().

Iterates through all VS speed, HS speed, and hbin combinations in FVB mode,
applies each to the camera, queries GetReadOutTime(), and compares to the
analytical formula.

    uv run python scripts/validate_readout_formula.py
"""

from __future__ import annotations

import sys

SDK_PATH = r"C:\Program Files\Andor SDK"


def main():
    from pyAndorSDK2 import atmcd, atmcd_codes, atmcd_errors

    sdk = atmcd(SDK_PATH)
    codes = atmcd_codes
    errors = atmcd_errors

    ret = sdk.Initialize(SDK_PATH)
    if ret != errors.Error_Codes.DRV_SUCCESS:
        print(f"Initialize failed: {ret}")
        sys.exit(1)

    ret, xpixels, ypixels = sdk.GetDetector()
    print(f"Camera: {xpixels}x{ypixels}")
    print()

    # Import the formula
    from andor_qt.utils.readout_time import (
        VS_SPEEDS_US,
        HS_RATES_HZ,
        calculate_readout_time_ms,
    )

    # Set FVB mode, internal trigger, conventional amplifier
    sdk.SetReadMode(codes.Read_Mode.FULL_VERTICAL_BINNING)
    sdk.SetTriggerMode(codes.Trigger_Mode.INTERNAL)
    sdk.SetAcquisitionMode(codes.Acquisition_Mode.SINGLE_SCAN)
    sdk.SetExposureTime(0.01)

    vs_indices = sorted(VS_SPEEDS_US.keys())
    hs_indices = sorted(HS_RATES_HZ.keys())
    hbin_values = [1, 2, 4, 8, 16]

    print(f"{'VS idx':>6} {'HS idx':>6} {'hbin':>5} {'SDK (ms)':>10} {'Formula (ms)':>13} {'Diff (ms)':>10} {'Diff %':>8} {'Status':>8}")
    print("-" * 80)

    max_diff_pct = 0.0
    n_tests = 0
    n_pass = 0

    for vs_idx in vs_indices:
        sdk.SetVSSpeed(vs_idx)
        for hs_idx in hs_indices:
            sdk.SetHSSpeed(1, hs_idx)  # type=1 for conventional amplifier
            for hbin in hbin_values:
                if xpixels % hbin != 0:
                    continue

                sdk.SetFVBHBin(hbin)
                sdk.PrepareAcquisition()

                ret, t_sdk = sdk.GetReadOutTime()
                if ret != errors.Error_Codes.DRV_SUCCESS:
                    print(f"{vs_idx:>6} {hs_idx:>6} {hbin:>5} {'SDK FAIL':>10}")
                    continue

                t_sdk_ms = t_sdk * 1000.0
                t_formula_ms = calculate_readout_time_ms(
                    "fvb", ypixels, xpixels, vs_idx, hs_idx, hbin
                )

                diff_ms = t_formula_ms - t_sdk_ms
                diff_pct = abs(diff_ms / t_sdk_ms) * 100 if t_sdk_ms > 0 else 0
                max_diff_pct = max(max_diff_pct, diff_pct)
                status = "OK" if diff_pct < 15 else "WARN" if diff_pct < 30 else "FAIL"
                n_tests += 1
                if diff_pct < 15:
                    n_pass += 1

                print(
                    f"{vs_idx:>6} {hs_idx:>6} {hbin:>5} "
                    f"{t_sdk_ms:>10.3f} {t_formula_ms:>13.3f} "
                    f"{diff_ms:>+10.3f} {diff_pct:>7.1f}% {status:>8}"
                )

    print("-" * 80)
    print(f"\n{n_pass}/{n_tests} within 15% tolerance")
    print(f"Max deviation: {max_diff_pct:.1f}%")

    sdk.ShutDown()
    print("\nCamera shut down.")


if __name__ == "__main__":
    main()
