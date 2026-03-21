"""Delta OD (transient absorption signal) computation utilities.

All functions are pure (no side effects) and operate on numpy arrays.

ΔOD = -log10(pump_on / pump_off)

Positive ΔOD means absorption increase (ground state bleach or excited state
absorption depending on sign convention — here: absorption = positive ΔOD).
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np


def background_subtract(spectrum: np.ndarray, dark: np.ndarray) -> np.ndarray:
    """Subtract dark spectrum from signal and clip negative values to zero.

    Args:
        spectrum: Raw signal spectrum (counts or intensity).
        dark: Dark/background spectrum to subtract.

    Returns:
        Background-subtracted spectrum, clipped to ≥ 0.
    """
    result = np.asarray(spectrum, dtype=float) - np.asarray(dark, dtype=float)
    return np.clip(result, 0.0, None)


def compute_delta_od(
    pump_on: np.ndarray,
    pump_off: np.ndarray,
    epsilon: float = 1e-10,
) -> np.ndarray:
    """Compute ΔOD = -log10(pump_on / pump_off).

    Args:
        pump_on: Pump-on spectrum (background-subtracted counts).
        pump_off: Pump-off spectrum (background-subtracted counts).
        epsilon: Small value added to denominators to prevent division by zero.

    Returns:
        ΔOD spectrum (no NaN or Inf values).
    """
    on = np.asarray(pump_on, dtype=float)
    off = np.asarray(pump_off, dtype=float)
    # Add epsilon to both to prevent log(0) and division by zero
    safe_off = np.where(np.abs(off) < epsilon, epsilon, off)
    safe_on = np.where(np.abs(on) < epsilon, epsilon, on)
    ratio = safe_on / safe_off
    return -np.log10(ratio)


def average_delta_od(
    delta_od_list: List[np.ndarray],
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute mean and standard deviation of multiple ΔOD spectra.

    Args:
        delta_od_list: List of ΔOD arrays (all same shape).

    Returns:
        Tuple of (mean, std) as numpy arrays.
    """
    stack = np.stack(delta_od_list, axis=0)
    mean = np.mean(stack, axis=0)
    std = np.std(stack, axis=0, ddof=0)
    return mean, std
