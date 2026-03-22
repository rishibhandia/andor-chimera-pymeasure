"""Differential signal (ΔI/I₀) computation utilities for TA measurements.

All functions are pure (no side effects) and operate on numpy arrays.

ΔI/I₀ = (I_pumped − I₀) / I₀

Negative values mean decreased transmission (absorption increase / bleach
recovery); positive values mean increased transmission.
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


def compute_delta_signal(
    pumped: np.ndarray,
    ref: np.ndarray,
    epsilon: float = 1e-10,
) -> np.ndarray:
    """Compute ΔI/I₀ = (I_pumped − I₀) / I₀.

    Args:
        pumped: Pump-on spectrum (background-subtracted counts).
        ref: Pump-off reference spectrum (background-subtracted counts).
        epsilon: Minimum absolute value used for the reference to prevent
            division by zero.

    Returns:
        ΔI/I₀ spectrum (no NaN or Inf values).
    """
    i_pumped = np.asarray(pumped, dtype=float)
    i_ref = np.asarray(ref, dtype=float)
    safe_ref = np.where(np.abs(i_ref) < epsilon, epsilon, i_ref)
    return (i_pumped - i_ref) / safe_ref


def average_delta_signal(
    delta_signal_list: List[np.ndarray],
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute mean and standard deviation of multiple ΔI/I₀ spectra.

    Args:
        delta_signal_list: List of ΔI/I₀ arrays (all same shape).

    Returns:
        Tuple of (mean, std) as numpy arrays.
    """
    stack = np.stack(delta_signal_list, axis=0)
    mean = np.mean(stack, axis=0)
    std = np.std(stack, axis=0, ddof=0)
    return mean, std
