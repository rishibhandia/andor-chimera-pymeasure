"""Readout time calculator for Andor DU970P Newton EMCCD.

``calculate_readout_time_ms`` estimates the sensor readout time from the
current camera settings.  Coefficients were fitted to 75 SDK
``GetReadOutTime()`` measurements across all VS speed, HS speed, and hbin
combinations on a DU970P (FVB mode, conventional amplifier).

Model (FVB)::

    t = a * n_rows * vs_us / 1000
      + b * eff_pixels / hs_hz * 1000
      + c * n_binshifts / 1e6
      + d * n_binshifts / hs_hz * 1000
      + e

Where ``eff_pixels = n_pixels / hbin`` and ``n_binshifts = n_pixels - eff_pixels``.

Accuracy: 75/75 within 10%, 69/75 within 5% vs SDK GetReadOutTime().
"""

from __future__ import annotations

# DU970P default VS speeds in us/row (index -> us)
VS_SPEEDS_US: dict[int, float] = {
    0: 4.9,
    1: 9.8,
    2: 19.0,
    3: 38.0,
    4: 57.0,
}

# DU970P HS pixel rates in Hz (index -> Hz)
HS_RATES_HZ: dict[int, float] = {
    0: 3_000_000.0,   # 3 MHz
    1: 1_000_000.0,   # 1 MHz
    2:    50_000.0,   # 50 kHz
}

# Fitted coefficients (DU970P, conventional amplifier, FVB)
_A_VS = 0.974206       # VS time scaling
_B_ADC = 1.035160      # ADC readout time scaling
_C_BINSHIFT = 336.803  # CCD charge shift time per binning shift (ns equiv)
_D_BINSHIFT_HS = 0.119078  # HS-rate-dependent binning overhead scaling
_E_OVERHEAD = 0.026239     # fixed overhead (ms)


def calculate_readout_time_ms(
    mode: str,
    n_rows: int,
    n_pixels: int,
    vs_idx: int,
    hs_idx: int,
    hbin: int = 1,
    vbin: int = 1,
) -> float:
    """Calculate estimated readout time in milliseconds.

    Args:
        mode: ``"fvb"``, ``"crop"``, ``"single_track"``, or ``"image"``.
        n_rows: Number of rows to read out (full CCD = 200, crop = cropheight).
        n_pixels: Number of horizontal pixels (full CCD = 1600).
        vs_idx: VS speed index (0 = fastest 4.9 us, 4 = slowest 57 us).
        hs_idx: HS speed index (0 = 3 MHz, 1 = 1 MHz, 2 = 50 kHz).
        hbin: Horizontal binning factor (default 1).
        vbin: Vertical binning factor (default 1). Ignored for FVB.

    Returns:
        Estimated readout time in milliseconds.
    """
    vs_us = VS_SPEEDS_US.get(vs_idx, 9.8)
    hs_hz = HS_RATES_HZ.get(hs_idx, 1_000_000.0)

    eff_pixels = max(1, n_pixels // max(1, hbin))
    n_binshifts = n_pixels - eff_pixels

    vs_ms = n_rows * vs_us / 1000.0
    adc_ms = eff_pixels / hs_hz * 1000.0
    binshift_fixed_ms = n_binshifts / 1e6 * _C_BINSHIFT
    binshift_hs_ms = n_binshifts / hs_hz * 1000.0

    if mode in ("fvb", "crop", "single_track"):
        # One horizontal readout cycle
        return (
            _A_VS * vs_ms
            + _B_ADC * adc_ms
            + binshift_fixed_ms
            + _D_BINSHIFT_HS * binshift_hs_ms
            + _E_OVERHEAD
        )
    else:
        # Image mode: one horizontal readout per vbin group
        eff_vbin = max(1, vbin)
        n_readouts = max(1, n_rows // eff_vbin)
        return (
            _A_VS * vs_ms
            + n_readouts * (
                _B_ADC * (eff_pixels / hs_hz * 1000.0)
                + binshift_fixed_ms
                + _D_BINSHIFT_HS * binshift_hs_ms
            )
            + _E_OVERHEAD
        )
