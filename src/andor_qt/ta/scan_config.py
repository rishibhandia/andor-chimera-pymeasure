"""TA scan configuration dataclass and delay list generator functions.

The ``TAScanConfig`` dataclass holds all parameters for a transient absorption
scan. Delay lists can be generated with the helper functions and stored in the
config for serialization.

Delay generator functions are pure (no side effects) and return ``list[float]``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np
import yaml


@dataclass
class TAScanConfig:
    """Configuration for a transient absorption scan.

    Attributes:
        delay_list: Time delays to measure in picoseconds.
        n_averages: Number of pump-on/pump-off pairs averaged per delay point.
        n_scans: Total number of complete scans through all delays.
        acquisition_mode: ``"boxcar"`` or ``"shot_to_shot"``.
        scan_direction: ``"forward"`` (always same order) or
            ``"alternating"`` (even scans forward, odd scans reversed).
        wavelengths: Optional list of wavelengths to record (nm). If None,
            uses full detector range.
        sample_name: Name of the sample being measured.
        notes: Free-text notes about the measurement.
    """

    delay_list: List[float]
    n_averages: int = 3
    n_scans: int = 1
    acquisition_mode: str = "boxcar"
    scan_direction: str = "forward"
    wavelengths: Optional[List[float]] = None
    sample_name: str = ""
    notes: str = ""
    # NI DAQ hardware phase reader settings
    nidaq_device: str = "Dev1"
    nidaq_di_channel: str = "port0/line0"
    nidaq_clock_source: str = "/Dev1/PFI0"
    nidaq_clock_rate: float = 1000.0

    def ordered_delays(self, scan_index: int) -> List[float]:
        """Return delay list in scan order for the given scan index.

        Args:
            scan_index: Zero-based scan index.

        Returns:
            Delay list in forward order for even scans (or ``"forward"`` mode),
            reversed for odd scans in ``"alternating"`` mode.
        """
        if self.scan_direction == "alternating" and scan_index % 2 == 1:
            return list(reversed(self.delay_list))
        return list(self.delay_list)

    def to_yaml(self, path) -> None:
        """Serialize config to a YAML file.

        Args:
            path: File path (str or Path).
        """
        data = {
            "delay_list": self.delay_list,
            "n_averages": self.n_averages,
            "n_scans": self.n_scans,
            "acquisition_mode": self.acquisition_mode,
            "scan_direction": self.scan_direction,
            "wavelengths": self.wavelengths,
            "sample_name": self.sample_name,
            "notes": self.notes,
            "nidaq_device": self.nidaq_device,
            "nidaq_di_channel": self.nidaq_di_channel,
            "nidaq_clock_source": self.nidaq_clock_source,
            "nidaq_clock_rate": self.nidaq_clock_rate,
        }
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False)

    @classmethod
    def from_yaml(cls, path) -> "TAScanConfig":
        """Load config from a YAML file.

        Args:
            path: File path (str or Path).

        Returns:
            New ``TAScanConfig`` instance.
        """
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return cls(**data)


# ---------------------------------------------------------------------------
# Delay list generator functions
# ---------------------------------------------------------------------------


def linear_delays(start: float, end: float, step: float) -> List[float]:
    """Generate a linearly spaced delay list.

    Args:
        start: First delay in ps.
        end: Last delay in ps (inclusive).
        step: Step size in ps.

    Returns:
        List of delay values.
    """
    if step <= 0:
        raise ValueError("step must be positive")
    if start == end:
        return [float(start)]
    n = math.ceil((end - start) / step) + 1
    result = [start + i * step for i in range(n)]
    # Ensure endpoint is included and not exceeded
    if result[-1] > end + 1e-12:
        result = result[:-1]
    if abs(result[-1] - end) > 1e-9:
        result.append(float(end))
    return [float(x) for x in result]


def log_delays(start: float, end: float, points_per_decade: int) -> List[float]:
    """Generate a logarithmically spaced delay list.

    Args:
        start: First delay in ps (must be > 0).
        end: Last delay in ps.
        points_per_decade: Number of points per decade of delay.

    Returns:
        List of delay values including both endpoints.
    """
    if start <= 0:
        raise ValueError("start must be positive for log spacing")
    n_decades = math.log10(end / start)
    n_points = round(n_decades * points_per_decade) + 1
    return list(np.geomspace(start, end, num=n_points).tolist())


def custom_delays(segments: List[dict]) -> List[float]:
    """Generate a delay list from multiple segments.

    Each segment dict has:
    - ``"type"``: ``"linear"`` or ``"log"``
    - ``"start"``: segment start in ps
    - ``"end"``: segment end in ps
    - ``"step"``: step size (linear) or points per decade (log)

    Duplicate boundary points between adjacent segments are removed.

    Args:
        segments: List of segment specification dicts.

    Returns:
        Concatenated, deduplicated delay list.
    """
    result: List[float] = []
    for seg in segments:
        seg_type = seg.get("type", "linear")
        start = float(seg["start"])
        end = float(seg["end"])
        step = seg["step"]

        if seg_type == "linear":
            pts = linear_delays(start, end, float(step))
        elif seg_type == "log":
            pts = log_delays(start, end, int(step))
        else:
            raise ValueError(f"Unknown segment type: {seg_type!r}")

        if result and abs(result[-1] - pts[0]) < 1e-12:
            pts = pts[1:]  # remove duplicate boundary
        result.extend(pts)

    return result


def manual_delays(values: List[float]) -> List[float]:
    """Return a copy of the provided delay list.

    Args:
        values: Arbitrary delay values in ps.

    Returns:
        List of delay values (copy).
    """
    return list(values)
