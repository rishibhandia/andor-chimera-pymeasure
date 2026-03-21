"""Chopper synchronization for pump-probe TA experiments.

``ChopperSync`` sorts acquired spectra into pump-on and pump-off lists using
either software timing (alternating even/odd frames) or an external hardware
tag array.

``phase_check()`` uses a variance test to detect whether the chopper is
correctly synchronized: if all rows are similar (low inter-frame variance),
the pump modulation is absent or the phase is wrong.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np


class ChopperSync:
    """Sort spectra into pump-on / pump-off pairs.

    Args:
        mode: ``"software"`` (even = pump-on, odd = pump-off) or
            ``"hardware"`` (external tag array with 1=on, 0=off).
        phase_threshold: Minimum normalized inter-frame variance ratio to
            consider the phase correct. Default 0.01.
    """

    def __init__(self, mode: str = "software", phase_threshold: float = 0.01):
        if mode not in ("software", "hardware"):
            raise ValueError(f"Unknown chopper mode: {mode!r}")
        self.mode = mode
        self.phase_threshold = phase_threshold

    def tag_shots(
        self,
        spectra: np.ndarray,
        tags: Optional[np.ndarray] = None,
    ) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """Split spectra into pump-on and pump-off lists.

        Args:
            spectra: 2-D array of shape (n_shots, n_pixels).
            tags: External tag array of shape (n_shots,) with 1=pump-on,
                0=pump-off. Required when ``mode="hardware"``, ignored
                otherwise.

        Returns:
            Tuple of (pump_on_list, pump_off_list).
        """
        spectra = np.asarray(spectra)

        if self.mode == "software":
            on_list = [spectra[i] for i in range(0, len(spectra), 2)]
            off_list = [spectra[i] for i in range(1, len(spectra), 2)]
        else:
            if tags is None:
                raise ValueError("tags array required for hardware mode")
            tags = np.asarray(tags)
            on_list = [spectra[i] for i in range(len(spectra)) if tags[i] == 1]
            off_list = [spectra[i] for i in range(len(spectra)) if tags[i] == 0]

        # Drop unmatched trailing shots
        n = min(len(on_list), len(off_list))
        return on_list[:n], off_list[:n]

    def phase_check(self, recent_spectra: np.ndarray) -> bool:
        """Check if chopper phase is correct using a variance test.

        Computes the ratio of inter-frame variance (variance of row means)
        to intra-frame variance (mean of row variances). A high ratio indicates
        that frames alternate significantly, which is expected with correct sync.

        Args:
            recent_spectra: Array of shape (n_shots, n_pixels).

        Returns:
            ``True`` if the inter-frame modulation exceeds the threshold,
            ``False`` otherwise (phase likely wrong or chopper not running).
        """
        spectra = np.asarray(recent_spectra, dtype=float)
        if spectra.shape[0] < 2:
            return False

        row_means = spectra.mean(axis=1)
        inter_var = np.var(row_means)

        pixel_vars = spectra.var(axis=1)
        intra_var = pixel_vars.mean()

        if intra_var < 1e-12:
            # No within-frame noise — check inter_var against signal magnitude
            mean_signal = float(np.abs(spectra).mean())
            if mean_signal < 1e-12:
                return False
            return float(inter_var) > self.phase_threshold * mean_signal ** 2

        ratio = inter_var / intra_var
        return float(ratio) > self.phase_threshold
