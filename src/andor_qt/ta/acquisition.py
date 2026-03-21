"""Low-level acquisition helper for TA measurements.

``acquire_delta_od_at_delay`` moves the delay stage to a given position and
acquires a ΔOD spectrum by averaging pump-on/pump-off pairs.

This function is used by both ``TransientAbsorptionEngine`` (scan loop) and
``T0Finder`` (t0 search).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from andor_qt.ta.delta_od import average_delta_od, background_subtract, compute_delta_od
from andor_qt.ta.scan_config import TAScanConfig


def acquire_delta_od_at_delay(
    delay_ps: float,
    hw_manager,
    config: TAScanConfig,
    dark: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Acquire ΔOD spectrum at a specific time delay.

    Moves the delay stage to ``delay_ps``, then acquires ``n_averages``
    pump-on/pump-off spectrum pairs and returns the averaged ΔOD.

    In ``"boxcar"`` mode: each pair is two sequential spectra alternating
    pump on/off (even=on, odd=off via software chopper).

    Args:
        delay_ps: Target delay in picoseconds.
        hw_manager: Hardware manager with ``.camera``, ``.motion`` attributes.
        config: Scan configuration (``n_averages``, ``acquisition_mode``).
        dark: Optional dark spectrum to subtract before computing ΔOD.

    Returns:
        Averaged ΔOD spectrum (1-D numpy array).
    """
    # Move stage to target delay
    axis = hw_manager.motion.get_axis("delay")
    if axis is not None:
        axis.position_ps = delay_ps

    delta_od_list = []
    for _ in range(config.n_averages):
        # Acquire pump-on spectrum
        pump_on = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)
        # Acquire pump-off spectrum
        pump_off = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)

        if dark is not None:
            pump_on = background_subtract(pump_on, dark)
            pump_off = background_subtract(pump_off, dark)

        delta_od = compute_delta_od(pump_on, pump_off)
        delta_od_list.append(delta_od)

    mean, _ = average_delta_od(delta_od_list)
    return mean
