"""Low-level acquisition helper for TA measurements.

``acquire_delta_signal_at_delay`` moves the delay stage to a given position
and acquires a ΔI/I₀ spectrum by averaging pump-on/pump-off pairs.

Hardware chopper mode (recommended)
------------------------------------
Pass a ``phase_reader`` (``NIDAQPhaseReader`` or ``MockNIDAQPhaseReader``).
For each shot pair the phase reader supplies a tag from the NI DAQ digital
input line (1 = pump-on, 0 = pump-off), so pump-on/off assignment is
determined by the chopper hardware rather than by shot ordering.

Software fallback (``phase_reader=None``)
-----------------------------------------
Two sequential spectra are acquired per pair; the first is treated as
pump-on and the second as pump-off.  This is kept for backward compatibility
but is less robust than hardware tagging.

This function is used by both ``TransientAbsorptionEngine`` (scan loop) and
``T0Finder`` (t0 search).
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from andor_qt.ta.chopper import ChopperSync
from andor_qt.ta.delta_signal import average_delta_signal, background_subtract, compute_delta_signal
from andor_qt.ta.scan_config import TAScanConfig

log = logging.getLogger(__name__)


def acquire_delta_signal_at_delay(
    delay_ps: float,
    hw_manager,
    config: TAScanConfig,
    dark: Optional[np.ndarray] = None,
    camera_settings: Optional[dict] = None,
    phase_reader=None,
) -> np.ndarray:
    """Acquire ΔI/I₀ spectrum at a specific time delay.

    Moves the delay stage to ``delay_ps``, then acquires ``n_averages``
    pump-on/pump-off spectrum pairs and returns the averaged ΔI/I₀.

    Args:
        delay_ps: Target delay in picoseconds.
        hw_manager: Hardware manager with ``.camera``, ``.motion`` attributes.
        config: Scan configuration (``n_averages``, ``acquisition_mode``).
        dark: Optional dark spectrum to subtract before computing ΔI/I₀.
        camera_settings: Optional dict passed to camera.apply_camera_settings()
            before acquisition. If None, current camera settings are unchanged.
        phase_reader: Optional NIDAQPhaseReader (or mock).  When provided,
            each shot is tagged by reading one sample from the NI DAQ digital
            input, and ``ChopperSync`` assigns pump-on/off accordingly.
            When ``None``, the first spectrum of each pair is taken as pump-on
            and the second as pump-off (software fallback).

    Returns:
        Averaged ΔI/I₀ spectrum (1-D numpy array).
    """
    # Move stage to target delay
    axis = hw_manager.motion.get_axis("delay")
    if axis is not None:
        axis.position_ps = delay_ps

    # Apply camera settings once before the averaging loop
    if camera_settings is not None:
        apply = getattr(hw_manager.camera, "apply_camera_settings", None)
        if callable(apply):
            apply(camera_settings)

    if config.acquisition_mode == "chopper_2x2" and phase_reader is not None:
        return _acquire_chopper_2x2(hw_manager, config, dark, phase_reader)
    if phase_reader is not None:
        return _acquire_hardware(hw_manager, config, dark, phase_reader)
    return _acquire_software(hw_manager, config, dark)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _acquire_hardware(hw_manager, config, dark, phase_reader) -> np.ndarray:
    """Acquire using NI DAQ hardware phase tags."""
    chopper = ChopperSync(mode="hardware")
    delta_signal_list = []

    for _ in range(config.n_averages):
        s1 = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)
        t1 = phase_reader.read_one()
        s2 = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)
        t2 = phase_reader.read_one()

        spectra = np.array([s1, s2])
        tags = np.array([t1, t2])
        on_list, off_list = chopper.tag_shots(spectra, tags)

        if not on_list or not off_list:
            log.warning("Phase mismatch: both shots have the same tag, skipping pair")
            continue

        pumped = on_list[0]
        ref = off_list[0]

        if dark is not None:
            pumped = background_subtract(pumped, dark)
            ref = background_subtract(ref, dark)

        delta_signal_list.append(compute_delta_signal(pumped, ref))

    if not delta_signal_list:
        raise RuntimeError("No valid pump-on/pump-off pairs acquired — check chopper sync")

    mean, _ = average_delta_signal(delta_signal_list)
    return mean


def _acquire_chopper_2x2(hw_manager, config, dark, phase_reader) -> np.ndarray:
    """Acquire using chopper_2x2 mode (500 Hz camera trigger, 2 shots per frame).

    Each ``get_spectrum()`` call returns one camera frame integrating 2 laser
    shots.  ``read_tags(2)`` reads the chopper state for both shots from P0.0;
    matched tags ([1,1] = pump-on, [0,0] = pump-off) confirm the frame type.
    Mixed tags indicate a chopper transition and the frame is discarded.

    ``n_averages`` pump-on / pump-off pairs are accumulated before returning
    the averaged ΔI/I₀.
    """
    delta_signal_list = []
    on_buf = []
    off_buf = []
    max_frames = config.n_averages * 6  # safety: allow up to 6× expected frames
    frames = 0

    while len(delta_signal_list) < config.n_averages:
        if frames >= max_frames:
            raise RuntimeError(
                f"chopper_2x2: {frames} frames acquired without completing "
                f"{config.n_averages} pairs — check chopper phase sync"
            )

        spectrum = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)
        tags = phase_reader.read_tags(2)
        frames += 1

        if tags[0] != tags[1]:
            log.debug(f"chopper_2x2: mixed tags {tags.tolist()}, discarding transition frame")
            continue

        if tags[0] == 1:
            on_buf.append(spectrum)
        else:
            off_buf.append(spectrum)

        if on_buf and off_buf:
            pumped = on_buf.pop(0)
            ref = off_buf.pop(0)
            if dark is not None:
                pumped = background_subtract(pumped, dark)
                ref = background_subtract(ref, dark)
            delta_signal_list.append(compute_delta_signal(pumped, ref))

    mean, _ = average_delta_signal(delta_signal_list)
    return mean


def _acquire_software(hw_manager, config, dark) -> np.ndarray:
    """Acquire using software alternation (first shot = pump-on)."""
    delta_signal_list = []

    for _ in range(config.n_averages):
        pumped = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)
        ref = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)

        if dark is not None:
            pumped = background_subtract(pumped, dark)
            ref = background_subtract(ref, dark)

        delta_signal_list.append(compute_delta_signal(pumped, ref))

    mean, _ = average_delta_signal(delta_signal_list)
    return mean
