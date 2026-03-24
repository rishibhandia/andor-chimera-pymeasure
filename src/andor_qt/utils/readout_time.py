"""Readout time calculator for Andor DU970P Newton EMCCD.

``calculate_readout_time_ms`` estimates the sensor readout time from the
current camera settings.  It is used to display the readout time in the
camera settings widget and to warn when the readout would exceed a
laser-period budget.

Formula
-------
FVB (Full Vertical Binning):
    t = n_rows * vs_us * 1e-3  +  (n_pixels / hbin) / hs_hz * 1e3   [ms]

Image / Crop mode:
    t = n_rows * vs_us * 1e-3  +  (n_rows / vbin) * (n_pixels / hbin) / hs_hz * 1e3

The VS term covers the time to shift all rows into the horizontal register.
The HS term covers all horizontal readout cycles (one per vbin group).
"""

from __future__ import annotations

# DU970P default VS speeds in µs/row (index → µs)
VS_SPEEDS_US: dict[int, float] = {
    0: 4.9,
    1: 9.8,
    2: 19.0,
    3: 38.0,
    4: 57.0,
}

# DU970P HS pixel rates in Hz (index → Hz)
HS_RATES_HZ: dict[int, float] = {
    0: 3_000_000.0,   # 3 MHz
    1: 1_000_000.0,   # 1 MHz
    2:    50_000.0,   # 50 kHz
}


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
        mode: ``"fvb"`` or ``"image"`` (also used for crop/single-track).
        n_rows: Number of rows to read out (full CCD = 200, crop = cropheight).
        n_pixels: Number of horizontal pixels (full CCD = 1600, crop = cropwidth).
        vs_idx: VS speed index (0 = fastest 4.9 µs, 4 = slowest 57 µs).
        hs_idx: HS speed index (0 = 3 MHz, 1 = 1 MHz, 2 = 50 kHz).
        hbin: Horizontal binning factor (default 1 = no binning).
        vbin: Vertical binning factor (default 1 = no binning). Ignored for FVB.

    Returns:
        Estimated readout time in milliseconds.
    """
    vs_us = VS_SPEEDS_US.get(vs_idx, 9.8)
    hs_hz = HS_RATES_HZ.get(hs_idx, 1_000_000.0)

    eff_pixels = max(1, n_pixels // max(1, hbin))

    # Vertical shift time is the same for both modes
    vs_time_ms = n_rows * vs_us / 1000.0

    if mode in ("fvb", "crop", "single_track"):
        # FVB / isolated crop / single track: all rows binned into the shift
        # register, then one horizontal readout.  hbin reduces pixel count;
        # vbin within crop further bins before readout but does not add cycles.
        hs_time_ms = eff_pixels / hs_hz * 1000.0
    else:
        # Image mode: one horizontal readout per vbin group of rows
        eff_vbin = max(1, vbin)
        n_readouts = max(1, n_rows // eff_vbin)
        hs_time_ms = n_readouts * eff_pixels / hs_hz * 1000.0

    return vs_time_ms + hs_time_ms
