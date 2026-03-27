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
import time
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
    raw_callback=None,
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
    axis = hw_manager.motion_manager.get_axis("delay")
    if axis is not None:
        axis.position_ps = delay_ps

    # Apply camera settings once before the averaging loop
    if camera_settings is not None:
        apply = getattr(hw_manager.camera, "apply_camera_settings", None)
        if callable(apply):
            apply(camera_settings)

    if config.acquisition_mode == "shot_to_shot" and phase_reader is not None:
        return _acquire_shot_to_shot(hw_manager, config, dark, phase_reader, raw_callback=raw_callback)
    if config.acquisition_mode == "chopper_2x2" and phase_reader is not None:
        return _acquire_chopper_2x2(hw_manager, config, dark, phase_reader, raw_callback=raw_callback)
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


def _acquire_chopper_2x2(hw_manager, config, dark, phase_reader, raw_callback=None) -> np.ndarray:
    """Acquire using chopper_2x2 mode — batch read via Run Till Abort.

    The camera is started in Run Till Abort mode (continuous acquisition on
    each external trigger).  Frames accumulate in the circular buffer while
    the phase reader collects PFI0-clocked tags.  After enough frames have
    arrived, all frames and tags are bulk-read and processed in numpy.

    Tag alignment: 0 or 1 pre-trigger PFI0 samples may arrive between
    ``drain()`` and the first SDG trigger.  We read ``2*N + 1`` tags and
    try both offsets (0 and 1); the offset with more matched pairs wins.
    """
    camera = hw_manager.camera
    # Need ~2 frames per pair (1 ON + 1 OFF), plus ~10% margin for discards
    n_target = int(config.n_averages * 2.2) + 10
    # Use 80% of circular buffer to avoid overflow
    buf_size = getattr(camera, "get_circular_buffer_size", lambda: 12000)()
    max_chunk = max(1000, int(buf_size * 0.8))

    all_frames_list = []
    all_tags_list = []
    remaining = n_target

    while remaining > 0:
        chunk = min(remaining, max_chunk)

        camera.start_run_till_abort()
        phase_reader.drain()

        try:
            wait_s = (chunk * 2.0) / 1000.0 + 0.05
            time.sleep(wait_s)
            chunk_frames, n_chunk = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        if n_chunk == 0:
            break

        chunk_tags = phase_reader.read_tags(n_chunk * 2 + 1)

        # Auto-detect alignment offset for this chunk
        best_offset = 0
        best_matched = -1
        for offset in (0, 1):
            tag_pairs = chunk_tags[offset:offset + n_chunk * 2].reshape(n_chunk, 2)
            n_matched = int((tag_pairs[:, 0] == tag_pairs[:, 1]).sum())
            if n_matched > best_matched:
                best_matched = n_matched
                best_offset = offset

        tag_pairs = chunk_tags[best_offset:best_offset + n_chunk * 2].reshape(n_chunk, 2)
        all_frames_list.append(chunk_frames)
        all_tags_list.append(tag_pairs)
        remaining -= n_chunk

    if not all_frames_list:
        raise RuntimeError("chopper_2x2: no frames acquired — check trigger")

    frames = np.concatenate(all_frames_list)
    tag_pairs = np.concatenate(all_tags_list)
    n_read = len(frames)

    # Separate matched frames by pump state
    matched_mask = tag_pairs[:, 0] == tag_pairs[:, 1]
    n_discarded = int(n_read - matched_mask.sum())
    matched_frames = frames[matched_mask]
    matched_tags = tag_pairs[matched_mask, 0]

    on_frames = matched_frames[matched_tags == 1]
    off_frames = matched_frames[matched_tags == 0]
    n_pairs = min(len(on_frames), len(off_frames), config.n_averages)

    if n_pairs == 0:
        raise RuntimeError(
            f"chopper_2x2: {n_read} frames, {n_discarded} discarded, "
            f"0 valid pairs — check chopper phase sync"
        )

    # Compute ΔI/I₀ (vectorized)
    pumped = on_frames[:n_pairs]
    ref = off_frames[:n_pairs]

    if dark is not None:
        pumped = pumped - dark[np.newaxis, :]
        ref = ref - dark[np.newaxis, :]

    # Per-pair delta signal, then average
    ref_safe = np.where(ref == 0, 1.0, ref)
    delta = (pumped - ref) / ref_safe
    mean = delta.mean(axis=0)

    # Emit averaged pump-ON and pump-OFF spectra for live display
    # Use ALL matched frames (not capped at n_averages)
    if raw_callback is not None:
        raw_callback(on_frames.mean(axis=0), off_frames.mean(axis=0), n_pairs, n_discarded, n_read)

    log.info(
        f"chopper_2x2: collected {n_pairs} pairs, "
        f"{n_discarded} discarded, {n_read} total frames "
        f"({wait_s:.2f}s accumulation, offset={best_offset})"
    )
    return mean


def _acquire_shot_to_shot(hw_manager, config, dark, phase_reader, raw_callback=None) -> np.ndarray:
    """Acquire using shot-to-shot mode — 1 kHz single-shot crop-mode acquisition.

    The camera runs in isolated crop mode (reduced rows for <1 ms readout)
    with a 1 kHz external trigger (one frame per laser shot).  Each frame
    gets a single P0.0 tag: 1 = pump-ON, 0 = pump-OFF.  Frames are sorted
    by pump state and paired for ΔI/I₀ computation.

    For large n_averages, acquisition is split into chunks to avoid
    overflowing the camera circular buffer.
    """
    camera = hw_manager.camera
    n_target = int(config.n_averages * 2.2) + 10
    # Max frames per chunk — stay well below circular buffer limit (~15000 frames)
    buf_size = getattr(camera, "get_circular_buffer_size", lambda: 12000)()
    max_chunk = max(1000, int(buf_size * 0.8))

    hbin = getattr(camera, "_current_hbin", 1)
    all_frames = []
    all_tags = []
    remaining = n_target

    while remaining > 0:
        chunk = min(remaining, max_chunk)

        camera.start_run_till_abort_crop(
            crop_height=config.crop_height,
            hbin=hbin,
        )
        phase_reader.drain()

        try:
            wait_s = chunk / 1000.0 + 0.05
            time.sleep(wait_s)
            frames, n_read = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        if n_read == 0:
            break

        # Read available tags — may be slightly more or fewer than n_read
        read_avail = getattr(phase_reader, "read_available_tags", None)
        if callable(read_avail):
            tags = read_avail()
        else:
            tags = phase_reader.read_tags(n_read)

        # Align frame and tag counts
        n_use = min(n_read, len(tags))
        if n_use > 0:
            all_frames.append(frames[:n_use])
            all_tags.append(tags[:n_use])
        remaining -= n_use

    if not all_frames:
        raise RuntimeError("shot_to_shot: no frames acquired — check trigger")

    frames = np.concatenate(all_frames)
    tags = np.concatenate(all_tags)
    # Align: use the shorter of frames and tags
    n_read = min(len(frames), len(tags))
    frames = frames[:n_read]
    tags = tags[:n_read]

    if n_read == 0:
        raise RuntimeError("shot_to_shot: no frames acquired — check trigger")

    # Separate by pump state
    on_mask = tags == 1
    off_mask = tags == 0
    on_frames = frames[on_mask]
    off_frames = frames[off_mask]
    n_pairs = min(len(on_frames), len(off_frames), config.n_averages)

    if n_pairs == 0:
        raise RuntimeError(
            f"shot_to_shot: {n_read} frames, "
            f"{int(on_mask.sum())} ON, {int(off_mask.sum())} OFF — "
            f"0 valid pairs"
        )

    pumped = on_frames[:n_pairs]
    ref = off_frames[:n_pairs]

    if dark is not None:
        pumped = pumped - dark[np.newaxis, :]
        ref = ref - dark[np.newaxis, :]

    ref_safe = np.where(ref == 0, 1.0, ref)
    delta = (pumped - ref) / ref_safe
    mean = delta.mean(axis=0)

    if raw_callback is not None:
        raw_callback(on_frames.mean(axis=0), off_frames.mean(axis=0),
                     n_pairs, 0, 2 * n_pairs)

    log.info(
        f"shot_to_shot: {n_pairs} pairs from {n_read} frames "
        f"({int(on_mask.sum())} ON, {int(off_mask.sum())} OFF, "
        f"{wait_s:.2f}s accumulation)"
    )
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
