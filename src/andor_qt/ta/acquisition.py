"""Low-level acquisition helper for TA measurements.

``acquire_delta_signal_at_delay`` moves the delay stage to a given position
and acquires a ΔI/I₀ spectrum by averaging pump-on/pump-off pairs.

This function is used by both ``TransientAbsorptionEngine`` (scan loop) and
``T0Finder`` (t0 search).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from andor_qt.ta.delta_signal import average_delta_signal, background_subtract, compute_delta_signal
from andor_qt.ta.scan_config import TAScanConfig


def acquire_delta_signal_at_delay(
    delay_ps: float,
    hw_manager,
    config: TAScanConfig,
    dark: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Acquire ΔI/I₀ spectrum at a specific time delay.

    Moves the delay stage to ``delay_ps``, then acquires ``n_averages``
    pump-on/pump-off spectrum pairs and returns the averaged ΔI/I₀.

    In ``"boxcar"`` mode: each pair is two sequential spectra alternating
    pump on/off (even=on, odd=off via software chopper).

    Args:
        delay_ps: Target delay in picoseconds.
        hw_manager: Hardware manager with ``.camera``, ``.motion`` attributes.
        config: Scan configuration (``n_averages``, ``acquisition_mode``).
        dark: Optional dark spectrum to subtract before computing ΔI/I₀.

    Returns:
        Averaged ΔI/I₀ spectrum (1-D numpy array).
    """
    # Move stage to target delay
    axis = hw_manager.motion.get_axis("delay")
    if axis is not None:
        axis.position_ps = delay_ps

    delta_signal_list = []
    for _ in range(config.n_averages):
        # Acquire pump-on spectrum
        pumped = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)
        # Acquire pump-off (reference) spectrum
        ref = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)

        if dark is not None:
            pumped = background_subtract(pumped, dark)
            ref = background_subtract(ref, dark)

        delta_signal = compute_delta_signal(pumped, ref)
        delta_signal_list.append(delta_signal)

    mean, _ = average_delta_signal(delta_signal_list)
    return mean
