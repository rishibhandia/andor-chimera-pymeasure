"""TA scan configuration dataclass and delay list generator functions.

The ``TAScanConfig`` dataclass holds all parameters for a transient absorption
scan. Delay lists can be generated with the helper functions and stored in the
config for serialization.

Delay generator functions are pure (no side effects) and return ``list[float]``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields as dc_fields
from pathlib import Path
from typing import List, Optional

import numpy as np
import yaml

# Speed of light in mm/ps (used for µm ↔ ps conversion)
SPEED_OF_LIGHT_MM_PS = 0.299792458


def um_to_ps(um: float) -> float:
    """Convert stage position in micrometres to optical delay in picoseconds (double-pass)."""
    return 2.0 * (um / 1000.0) / SPEED_OF_LIGHT_MM_PS


def ps_to_um(ps: float) -> float:
    """Convert optical delay in picoseconds to stage position in micrometres (double-pass)."""
    return (ps * SPEED_OF_LIGHT_MM_PS / 2.0) * 1000.0


@dataclass
class TAScanConfig:
    """Configuration for a transient absorption scan.

    Attributes:
        delay_list: Time delays to measure in picoseconds.
        n_averages: Number of pump-on/pump-off pairs averaged per delay point.
        n_scans: Total number of complete scans through all delays.
        acquisition_mode: ``"boxcar"``, ``"shot_to_shot"``, ``"chopper_2x2"``,
            or ``"static_onoff"``.
        scan_direction: ``"forward"`` (always same order) or
            ``"alternating"`` (even scans forward, odd scans reversed).
        sample_name: Name of the sample being measured.
        notes: Free-text notes about the measurement.
    """

    delay_list: List[float]
    n_averages: int = 100
    n_scans: int = 1
    acquisition_mode: str = "boxcar"
    scan_direction: str = "forward"
    sample_name: str = ""
    notes: str = ""
    # NI DAQ hardware phase reader settings
    nidaq_device: str = "Astrella_DAQ"
    nidaq_di_channel: str = "port0/line0"
    nidaq_clock_source: str = "/Astrella_DAQ/PFI0"
    nidaq_clock_rate: float = 1000.0
    # NI DAQ chopper_2x2 trigger generator settings
    nidaq_chopper_sync_source: str = "/Astrella_DAQ/PFI12"
    nidaq_chopper_counter: str = "ctr1"
    # Camera Fire output terminal — used as start trigger for the phase
    # reader so that tag[0] corresponds to frame[0] deterministically.
    nidaq_fire_trigger: str = "/Astrella_DAQ/PFI13"
    stage_axis: int = 2
    # When True, camera trigger is supplied externally (e.g. DG535 or SDG)
    # and NIDAQChopper500Hz is NOT started even in chopper_2x2 mode.
    external_trigger: bool = False
    # Number of laser shots per camera frame. 2 for 500 Hz camera / 250 Hz
    # chopper, 4 for 250 Hz camera / 125 Hz chopper.
    shots_per_frame: int = 2
    # Crop mode height for shot_to_shot mode (rows, anchored to sensor bottom)
    crop_height: int = 50
    # Optional directory to save the HDF5 data file
    save_hdf5_dir: Optional[str] = None
    # Optional directory to save individual spectrum files per delay point
    save_spectra_dir: Optional[str] = None
    # If True, swap the pump-on / pump-off tag assignment. Useful when the
    # chopper REF OUT polarity is reversed relative to the beam path so the
    # GUI tags pump-on frames as "blocked". Polarity is empirical — depends
    # on beam-to-photo-interrupter alignment, not configurable on chopper.
    swap_tags: bool = False

    def ordered_delays(self, scan_index: int) -> list[float]:
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

    def to_yaml(self, path: str | Path) -> None:
        """Serialize config to a YAML file.

        Args:
            path: File path (str or Path).
        """
        data = {f.name: getattr(self, f.name) for f in dc_fields(self)}
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False)

    @classmethod
    def from_yaml(cls, path: str | Path) -> TAScanConfig:
        """Load config from a YAML file.

        Args:
            path: File path (str or Path).

        Returns:
            New ``TAScanConfig`` instance.
        """
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        # Filter unknown keys for forward-compatibility
        known = {f.name for f in dc_fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Delay list generator functions
# ---------------------------------------------------------------------------


def linear_delays(start: float, end: float, step: float) -> list[float]:
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


def log_delays(start: float, end: float, points_per_decade: int) -> list[float]:
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



def linear_delays_um(start_um: float, end_um: float, step_um: float) -> list[float]:
    """Generate a linearly spaced delay list from stage positions in µm.

    Args:
        start_um: Starting stage position in µm.
        end_um: Ending stage position in µm (inclusive).
        step_um: Step size in µm.

    Returns:
        List of delay values in picoseconds.
    """
    if step_um == 0:
        raise ValueError("step_um must be non-zero")
    abs_step = abs(step_um)
    if start_um == end_um:
        return [um_to_ps(start_um)]
    n = math.ceil(abs(end_um - start_um) / abs_step) + 1
    sign = 1.0 if end_um >= start_um else -1.0
    positions = [start_um + i * sign * abs_step for i in range(n)]
    if sign > 0 and positions[-1] > end_um + 1e-6:
        positions = positions[:-1]
    elif sign < 0 and positions[-1] < end_um - 1e-6:
        positions = positions[:-1]
    if abs(positions[-1] - end_um) > 1e-3:
        positions.append(float(end_um))
    return [um_to_ps(p) for p in positions]


def log_delays_um(start_um: float, end_um: float, points_per_decade: int) -> list[float]:
    """Generate a log-spaced delay list from stage positions in µm.

    Converts start/end to ps, then applies log spacing in the time domain.

    Args:
        start_um: Starting stage position in µm.
        end_um: Ending stage position in µm.
        points_per_decade: Number of points per decade of delay.

    Returns:
        List of delay values in picoseconds.
    """
    start_ps = um_to_ps(start_um)
    end_ps = um_to_ps(end_um)
    return log_delays(start_ps, end_ps, points_per_decade)


def parse_manual_um(text: str) -> list[float]:
    """Parse manual delay specification text in µm.

    Accepts:
      - Plain numbers: ``-57000`` or ``-57000, -56000, -55000``
      - ``range(start, stop, step)`` expressions (integer args, like Python range)
      - Multiple entries separated by newlines
      - Comments starting with ``#``

    Returns:
        List of stage positions in µm (floats).
    """
    import re

    values: List[float] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Find all range(...) expressions in the line
        remaining = line
        range_pat = re.compile(r"range\(([^)]+)\)")
        while True:
            m = range_pat.search(remaining)
            if not m:
                break
            # Parse text before the match as plain numbers
            before = remaining[: m.start()].strip().rstrip(",").strip()
            if before:
                for part in before.split(","):
                    part = part.strip()
                    if part:
                        values.append(float(part))
            # Parse the range expression
            args = [s.strip() for s in m.group(1).split(",")]
            if len(args) == 2:
                values.extend(float(x) for x in range(int(args[0]), int(args[1])))
            elif len(args) == 3:
                values.extend(float(x) for x in range(int(args[0]), int(args[1]), int(args[2])))
            else:
                raise ValueError(f"Invalid range expression: {m.group(0)}")
            remaining = remaining[m.end():]

        # Handle any remaining text after last range()
        remaining = remaining.strip().lstrip(",").strip()
        if remaining:
            for part in remaining.split(","):
                part = part.strip()
                if part:
                    values.append(float(part))

    return values


def stage_delays_ps(start_um: float, step_um: float, n_steps: int) -> list[float]:
    """Convert delay stage positions to optical delays in picoseconds.

    Convenience wrapper around ``linear_delays_um`` using start/step/count
    parameterization instead of start/end/step.

    Args:
        start_um: Starting stage position in µm.
        step_um: Step size in µm (positive = increasing delay).
        n_steps: Number of steps (scan points).

    Returns:
        List of delay values in picoseconds.
    """
    end_um = start_um + (n_steps - 1) * step_um
    return linear_delays_um(start_um, end_um, abs(step_um))
