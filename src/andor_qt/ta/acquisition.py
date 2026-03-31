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
import threading
import time
from typing import Any, Callable, Optional

import numpy as np

from andor_qt.ta.delta_signal import average_delta_signal, background_subtract, compute_delta_signal
from andor_qt.ta.scan_config import TAScanConfig

log = logging.getLogger(__name__)

# Last acquisition statistics — populated after each acquisition call.
# Keys: pump_mean, pump_std, ref_mean, ref_std, delta_std, n_on, n_off
last_acquisition_stats: dict = {}


def acquire_delta_signal_at_delay(
    delay_ps: float,
    hw_manager: Any,
    config: TAScanConfig,
    dark: Optional[np.ndarray] = None,
    camera_settings: Optional[dict[str, Any]] = None,
    phase_reader: Any = None,
    raw_callback: Optional[Callable[[np.ndarray, np.ndarray, int, int, int], None]] = None,
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
    # Clear stale stats so they don't leak from a previous call on error
    last_acquisition_stats.clear()

    # Move stage to target delay
    mm = getattr(hw_manager, "motion_manager", None)
    axis = mm.get_axis("delay") if mm is not None else None
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
    return _acquire_software(hw_manager, config, dark, raw_callback=raw_callback)


# ---------------------------------------------------------------------------
# Chopper frame processing (used by both _acquire_chopper_2x2 and monitor)
# ---------------------------------------------------------------------------

def _process_chopper_frames(
    frames: np.ndarray,
    tags: np.ndarray,
    config: TAScanConfig,
    dark: Optional[np.ndarray] = None,
    raw_callback: Optional[Callable] = None,
) -> np.ndarray:
    """Process pre-read frames and tags into a delta-I/I0 spectrum.

    This is the core computation shared by both the chopper_2x2 acquisition
    (which starts/stops the camera) and the continuous monitor mode (which
    keeps the camera running).

    Args:
        frames: 2-D array of shape (n_frames, n_pixels).
        tags: 1-D array of phase tags (one per laser shot).
        config: Scan config with shots_per_frame, n_averages.
        dark: Optional dark spectrum to subtract.
        raw_callback: Optional callback for raw pump/ref display.

    Returns:
        Averaged delta-I/I0 spectrum (1-D array).
    """
    spf = getattr(config, "shots_per_frame", 2)
    n_frames = len(frames)

    # Group tags by shots_per_frame and detect alignment offset
    best_offset = 0
    best_matched = -1
    for offset in range(spf):
        usable = (len(tags) - offset) // spf
        if usable < 1:
            continue
        grp = tags[offset:offset + usable * spf].reshape(usable, spf)
        n_matched = int((grp == grp[:, :1]).all(axis=1).sum())
        if n_matched > best_matched:
            best_matched = n_matched
            best_offset = offset

    usable = min(n_frames, (len(tags) - best_offset) // spf)
    tag_groups = tags[best_offset:best_offset + usable * spf].reshape(usable, spf)
    frames = frames[:usable]
    n_read = len(frames)

    # Separate matched frames by pump state
    matched_mask = (tag_groups == tag_groups[:, :1]).all(axis=1)
    n_discarded = int(n_read - matched_mask.sum())
    matched_frames = frames[matched_mask]
    matched_tags = tag_groups[matched_mask, 0]

    on_frames = matched_frames[matched_tags == 1]
    off_frames = matched_frames[matched_tags == 0]
    n_pairs = min(len(on_frames), len(off_frames), config.n_averages)

    log.info(
        f"chopper_2x2 tag stats: {n_read} frames, {n_discarded} discarded, "
        f"{len(on_frames)} ON, {len(off_frames)} OFF, {n_pairs} pairs  |  "
        f"ON mean={on_frames.mean():.1f}, OFF mean={off_frames.mean():.1f}"
        if len(on_frames) > 0 and len(off_frames) > 0 else
        f"chopper_2x2 tag stats: {n_read} frames, {n_discarded} discarded, "
        f"{len(on_frames)} ON, {len(off_frames)} OFF"
    )

    if n_pairs == 0:
        raise RuntimeError(
            f"chopper_2x2: {n_read} frames, {n_discarded} discarded, "
            f"0 valid pairs -- check chopper phase sync"
        )

    pumped = on_frames[:n_pairs]
    ref = off_frames[:n_pairs]

    if dark is not None:
        pumped = pumped - dark[np.newaxis, :]
        ref = ref - dark[np.newaxis, :]

    ref_safe = np.where(ref == 0, 1.0, ref)
    delta = (pumped - ref) / ref_safe
    mean = delta.mean(axis=0)

    last_acquisition_stats.update({
        "pump_mean": on_frames.mean(axis=0),
        "pump_std": on_frames.std(axis=0),
        "ref_mean": off_frames.mean(axis=0),
        "ref_std": off_frames.std(axis=0),
        "delta_std": delta.std(axis=0),
        "n_on": len(on_frames),
        "n_off": len(off_frames),
    })

    if raw_callback is not None:
        raw_callback(on_frames.mean(axis=0), off_frames.mean(axis=0),
                     n_pairs, n_discarded, n_read)

    return mean


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _acquire_chopper_2x2(
    hw_manager: Any,
    config: TAScanConfig,
    dark: Optional[np.ndarray],
    phase_reader: Any,
    raw_callback: Optional[Callable[[np.ndarray, np.ndarray, int, int, int], None]] = None,
) -> np.ndarray:
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
    spf = getattr(config, "shots_per_frame", 2)  # laser shots per camera frame
    # Need ~2 frames per pair (1 ON + 1 OFF), plus ~10% margin for discards
    n_target = int(config.n_averages * 2.2) + 10
    # Use 80% of circular buffer to avoid overflow
    buf_size = getattr(camera, "get_circular_buffer_size", lambda: 12000)()
    max_chunk = max(1000, int(buf_size * 0.8))

    # Frame period: spf laser shots at 1 kHz = spf ms per frame
    frame_period_ms = spf  # 2 ms for 500 Hz, 4 ms for 250 Hz

    all_frames_list = []
    all_tags_list = []
    remaining = n_target

    # Start camera once — keep it running for the entire acquisition.
    # This preserves the phase relationship between the counter output
    # and the camera frames, preventing random ON/OFF flipping.
    camera.start_run_till_abort()
    phase_reader.drain()

    try:
        while remaining > 0:
            chunk = min(remaining, max_chunk)

            wait_s = (chunk * frame_period_ms) / 1000.0 + 0.05
            time.sleep(wait_s)
            chunk_frames, n_chunk = camera.get_buffered_frames()

            if n_chunk == 0:
                break

            # Read spf tags per frame + 1 for alignment detection
            chunk_tags = phase_reader.read_tags(n_chunk * spf + 1)

            # Auto-detect alignment offset for this chunk
            best_offset = 0
            best_matched = -1
            for offset in range(spf):
                usable = (len(chunk_tags) - offset) // spf
                if usable < 1:
                    continue
                tag_groups = chunk_tags[offset:offset + usable * spf].reshape(usable, spf)
                # A frame is "matched" if all tags in the group are the same
                n_matched = int((tag_groups == tag_groups[:, :1]).all(axis=1).sum())
                if n_matched > best_matched:
                    best_matched = n_matched
                    best_offset = offset

            usable = min(n_chunk, (len(chunk_tags) - best_offset) // spf)
            tag_groups = chunk_tags[best_offset:best_offset + usable * spf].reshape(usable, spf)
            all_frames_list.append(chunk_frames[:usable])
            all_tags_list.append(tag_groups)
            remaining -= usable
    finally:
        camera.abort_acquisition()

    if not all_frames_list:
        raise RuntimeError("chopper_2x2: no frames acquired — check trigger")

    frames = np.concatenate(all_frames_list)
    tag_groups = np.concatenate(all_tags_list)
    n_read = len(frames)

    # A frame is "matched" if all spf tags in its group are the same value
    matched_mask = (tag_groups == tag_groups[:, :1]).all(axis=1)
    n_discarded = int(n_read - matched_mask.sum())
    matched_frames = frames[matched_mask]
    matched_tags = tag_groups[matched_mask, 0]  # use first tag as the label

    # P0.0=1 means pump chopper open (pump-ON), P0.0=0 means closed (pump-OFF).
    # The camera runs continuously (no restart between cycles), so the phase
    # relationship with P0.0 is stable throughout the acquisition.
    on_frames = matched_frames[matched_tags == 1]
    off_frames = matched_frames[matched_tags == 0]

    n_pairs = min(len(on_frames), len(off_frames), config.n_averages)

    log.info(
        f"chopper_2x2 tag stats: {n_read} frames, {n_discarded} discarded, "
        f"{len(on_frames)} ON, {len(off_frames)} OFF, {n_pairs} pairs  |  "
        f"ON mean={on_frames.mean():.1f}, OFF mean={off_frames.mean():.1f}"
        if len(on_frames) > 0 and len(off_frames) > 0 else
        f"chopper_2x2 tag stats: {n_read} frames, {n_discarded} discarded, "
        f"{len(on_frames)} ON, {len(off_frames)} OFF"
    )

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

    # Store statistics for external access
    last_acquisition_stats.update({
        "pump_mean": on_frames.mean(axis=0),
        "pump_std": on_frames.std(axis=0),
        "ref_mean": off_frames.mean(axis=0),
        "ref_std": off_frames.std(axis=0),
        "delta_std": delta.std(axis=0),
        "n_on": len(on_frames),
        "n_off": len(off_frames),
    })

    if raw_callback is not None:
        raw_callback(on_frames.mean(axis=0), off_frames.mean(axis=0), n_pairs, n_discarded, n_read)

    log.info(
        f"chopper_2x2: collected {n_pairs} pairs, "
        f"{n_discarded} discarded, {n_read} total frames "
        f"({wait_s:.2f}s accumulation, offset={best_offset})"
    )
    return mean


def _acquire_shot_to_shot(
    hw_manager: Any,
    config: TAScanConfig,
    dark: Optional[np.ndarray],
    phase_reader: Any,
    raw_callback: Optional[Callable[[np.ndarray, np.ndarray, int, int, int], None]] = None,
) -> np.ndarray:
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
    log.info(f"shot_to_shot: n_target={n_target}, buf_size={buf_size}, max_chunk={max_chunk}")

    hbin = getattr(camera, "_current_hbin", 1)
    all_frames = []
    all_tags = []
    remaining = n_target
    chunk_idx = 0

    while remaining > 0:
        chunk = min(remaining, max_chunk)

        camera.start_run_till_abort_crop(
            crop_height=config.crop_height,
            hbin=hbin,
        )
        phase_reader.drain()

        try:
            # Wait for frames: 1 ms/frame at 1 kHz (with overlap mode) + 20% margin
            wait_s = (chunk * 1.0) / 1000.0 * 1.2 + 0.05
            time.sleep(wait_s)
            frames, n_read = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        log.info(f"  chunk {chunk_idx}: requested={chunk}, got={n_read}, wait={wait_s:.2f}s, remaining={remaining}")
        chunk_idx += 1

        if n_read == 0:
            break

        # Read available tags — may be slightly more or fewer than n_read
        read_avail = getattr(phase_reader, "read_available_tags", None)
        tags = read_avail() if callable(read_avail) else np.array([], dtype=np.int8)
        if len(tags) == 0:
            # Fallback: blocking read for exactly n_read tags
            tags = phase_reader.read_tags(n_read)
        if len(tags) == 0:
            # No tags available from any source — abort to prevent infinite loop
            break

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

    last_acquisition_stats.update({
        "pump_mean": on_frames.mean(axis=0),
        "pump_std": on_frames.std(axis=0),
        "ref_mean": off_frames.mean(axis=0),
        "ref_std": off_frames.std(axis=0),
        "delta_std": delta.std(axis=0),
        "n_on": len(on_frames),
        "n_off": len(off_frames),
    })

    if raw_callback is not None:
        raw_callback(on_frames.mean(axis=0), off_frames.mean(axis=0),
                     n_pairs, 0, 2 * n_pairs)

    log.info(
        f"shot_to_shot: {n_pairs} pairs from {n_read} frames "
        f"({int(on_mask.sum())} ON, {int(off_mask.sum())} OFF, "
        f"{wait_s:.2f}s accumulation)"
    )
    return mean


def _acquire_software(
    hw_manager: Any,
    config: TAScanConfig,
    dark: Optional[np.ndarray],
    raw_callback: Optional[Callable[[np.ndarray, np.ndarray, int, int, int], None]] = None,
) -> np.ndarray:
    """Acquire using software alternation (first shot = pump-on)."""
    delta_signal_list = []
    pump_sum = None
    ref_sum = None

    for i in range(config.n_averages):
        pumped = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)
        ref = np.asarray(hw_manager.camera.get_spectrum(), dtype=float)

        if dark is not None:
            pumped = background_subtract(pumped, dark)
            ref = background_subtract(ref, dark)

        # Accumulate running averages for raw callback and stats
        if pump_sum is None:
            pump_sum = pumped.copy()
            ref_sum = ref.copy()
        else:
            pump_sum += pumped
            ref_sum += ref

        delta_signal_list.append(compute_delta_signal(pumped, ref))

    n = config.n_averages
    pump_avg = pump_sum / n if pump_sum is not None else np.array([])
    ref_avg = ref_sum / n if ref_sum is not None else np.array([])

    # Populate stats with per-pixel arrays (consistent with hardware modes)
    mean, _ = average_delta_signal(delta_signal_list)
    delta_std = np.std(np.stack(delta_signal_list), axis=0) if len(delta_signal_list) > 1 else np.zeros_like(mean)
    last_acquisition_stats.update({
        "pump_mean": pump_avg,
        "pump_std": pump_avg,  # single-pair std not tracked; use pump_avg as placeholder
        "ref_mean": ref_avg,
        "ref_std": ref_avg,
        "delta_std": delta_std,
        "n_on": n,
        "n_off": n,
    })

    if raw_callback is not None and len(pump_avg) > 0:
        raw_callback(pump_avg, ref_avg, n, 0, 2 * n)

    return mean


# ---------------------------------------------------------------------------
# Long-average utility (shared by scan and monitor engines)
# ---------------------------------------------------------------------------

def acquire_long_average(
    camera: Any,
    n_target: int,
    abort_event: threading.Event,
    progress_cb: Optional[Callable[[np.ndarray, int, int], None]] = None,
    frame_period_s: float = 0.002,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Acquire many frames and return running-mean statistics.

    Uses chunked ``start_run_till_abort`` + ``get_buffered_frames`` with
    incremental sum / sum-of-squares for memory-efficient statistics.

    Args:
        camera: Camera object with ``start_run_till_abort()``,
            ``get_buffered_frames()``, ``abort_acquisition()``, and
            ``get_circular_buffer_size()`` methods.
        n_target: Number of frames to accumulate.
        abort_event: Set this event to abort early.
        progress_cb: Optional ``(running_mean, collected, n_target)`` callback
            invoked after each chunk for live progress updates.
        frame_period_s: Expected time per frame in seconds. Used to calculate
            how long to wait for a chunk of frames. Default 2 ms (500 Hz).
            For external trigger at 1 kHz, pass 0.001.

    Returns:
        ``(mean, std, count)`` where ``mean`` and ``std`` are 1-D arrays.

    Raises:
        RuntimeError: If no frames were acquired.
    """
    buf_size = getattr(camera, "get_circular_buffer_size", lambda: 12000)()
    max_chunk = max(1000, int(buf_size * 0.8))

    running_sum = None
    running_sum_sq = None
    collected = 0

    while collected < n_target and not abort_event.is_set():
        chunk = min(n_target - collected, max_chunk)

        camera.start_run_till_abort()
        try:
            wait_s = chunk * frame_period_s * 1.2 + 0.05
            time.sleep(wait_s)
            frames, n_read = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        if n_read == 0:
            break

        chunk_sum = frames.sum(axis=0)
        chunk_sum_sq = (frames.astype(np.float64) ** 2).sum(axis=0)
        if running_sum is None:
            running_sum = chunk_sum
            running_sum_sq = chunk_sum_sq
        else:
            running_sum += chunk_sum
            running_sum_sq += chunk_sum_sq
        collected += n_read

        if progress_cb is not None and collected > 0:
            progress_cb(running_sum / collected, collected, n_target)

    if running_sum is None or collected == 0:
        raise RuntimeError("Long average: no frames acquired")

    mean = running_sum / collected
    variance = running_sum_sq / collected - mean ** 2
    std = np.sqrt(np.maximum(variance, 0.0))
    return mean, std, collected


# ---------------------------------------------------------------------------
# Frame period estimation
# ---------------------------------------------------------------------------

def _compute_frame_period_s(camera_settings: Optional[dict] = None) -> float:
    """Estimate the time per frame from camera settings.

    For external trigger modes, the frame period is determined by the trigger
    source (e.g. 1 kHz laser sync → 1 ms, 500 Hz chopper → 2 ms), not by
    the camera's internal exposure + readout. For internal trigger, uses
    exposure_time + readout_time.

    Returns:
        Seconds per frame.
    """
    if camera_settings is None:
        return 0.002

    trigger_mode = camera_settings.get("trigger_mode", "internal")

    # External trigger: frame rate set by trigger source, not camera internals
    if trigger_mode == "fast_external":
        # Fast external with overlap: limited by trigger rate (typically 1 kHz)
        return 0.001  # 1 ms at 1 kHz laser sync
    elif trigger_mode == "external":
        # Non-fast external: exposure + readout (no overlap)
        pass  # fall through to calculation below

    exposure_s = camera_settings.get("exposure_time", 0.002)

    try:
        from andor_qt.utils.readout_time import calculate_readout_time_ms
        vs_idx = camera_settings.get("vs_speed", 1)
        hs_idx = camera_settings.get("hs_speed", 1)
        hbin = camera_settings.get("hbin", 1)
        if isinstance(hbin, str):
            hbin = int(hbin.replace("x", ""))
        readout_s = calculate_readout_time_ms("fvb", 200, 1600, vs_idx, hs_idx, hbin) / 1000.0
    except Exception:
        readout_s = 0.001

    return exposure_s + readout_s


# ---------------------------------------------------------------------------
# Static (bulk) acquisition — shared by scan and monitor static paths
# ---------------------------------------------------------------------------

def acquire_static_at_delay(
    hw_manager: Any,
    n_frames: int,
    abort_event: "threading.Event",
    dark: Optional[np.ndarray] = None,
    camera_settings: Optional[dict[str, Any]] = None,
    progress_cb: Optional[Callable[[np.ndarray, int, int], None]] = None,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Acquire bulk frames at the current position for static ON/OFF mode.

    Handles camera settings, dark subtraction, and stats population.
    The caller is responsible for moving the stage before calling this.

    Args:
        hw_manager: Hardware manager with ``.camera`` attribute.
        n_frames: Number of frames to average.
        abort_event: Set to abort early.
        dark: Optional dark spectrum to subtract from the mean.
        camera_settings: Optional dict passed to ``apply_camera_settings()``.
        progress_cb: Optional ``(running_mean, collected, n_target)`` callback.

    Returns:
        ``(mean, std, count)`` — dark-subtracted mean, std, and frame count.
    """
    # Apply camera settings
    if camera_settings is not None:
        apply = getattr(hw_manager.camera, "apply_camera_settings", None)
        if callable(apply):
            apply(camera_settings)

    # Compute frame period from camera settings for accurate wait time
    frame_period_s = _compute_frame_period_s(camera_settings)

    # Acquire
    mean, std, count = acquire_long_average(
        hw_manager.camera, n_frames, abort_event,
        progress_cb=progress_cb, frame_period_s=frame_period_s,
    )

    # Dark subtraction
    if dark is not None:
        mean = background_subtract(mean, dark)

    # Populate stats with per-pixel arrays (consistent with hardware modes)
    last_acquisition_stats.update({
        "pump_mean": mean,
        "pump_std": std,
        "ref_mean": np.zeros_like(mean),
        "ref_std": np.zeros_like(std),
        "n_on": count,
        "n_off": 0,
    })

    return mean, std, count


# ---------------------------------------------------------------------------
# AcquisitionSession — unified camera lifecycle for scan and monitor
# ---------------------------------------------------------------------------


class AcquisitionSession:
    """Context manager owning the camera lifecycle across multiple acquisitions.

    For ``chopper_2x2``: camera starts once in ``__enter__``, reads buffered
    frames per ``acquire_one_cycle()``, stops in ``__exit__``.  This
    preserves the phase relationship between camera frames and chopper tags.

    For ``shot_to_shot``: delegates to ``_acquire_shot_to_shot`` per cycle
    (which manages its own crop-mode camera start/stop).

    For ``boxcar``/software: delegates to ``_acquire_software`` per cycle
    (which uses ``get_spectrum()`` per shot, no RTA).

    Usage::

        with AcquisitionSession(hw, config, camera_settings, phase_reader) as s:
            for delay_ps in delays:
                axis.position_ps = delay_ps
                delta = s.acquire_one_cycle(dark=dark, raw_callback=cb)

    Args:
        hw_manager: Hardware manager with ``.camera`` attribute.
        config: Scan configuration (``acquisition_mode``, ``n_averages``, etc.).
        camera_settings: Optional dict passed to ``apply_camera_settings()``.
        phase_reader: Optional phase reader for hardware-tagged modes.
    """

    def __init__(
        self,
        hw_manager: Any,
        config: TAScanConfig,
        camera_settings: Optional[dict[str, Any]] = None,
        phase_reader: Any = None,
    ) -> None:
        self._hw = hw_manager
        self._config = config
        self._camera_settings = camera_settings
        self._phase_reader = phase_reader
        self._camera_running = False
        self._is_chopper = (
            config.acquisition_mode == "chopper_2x2"
            and phase_reader is not None
        )

    def __enter__(self) -> "AcquisitionSession":
        # Apply camera settings once
        if self._camera_settings is not None:
            apply = getattr(self._hw.camera, "apply_camera_settings", None)
            if callable(apply):
                apply(self._camera_settings)

        if self._is_chopper:
            self._hw.camera.start_run_till_abort()
            self._camera_running = True
            self._phase_reader.start()
            self._phase_reader.drain()

        return self

    def __exit__(self, *exc: object) -> None:
        if self._camera_running:
            self._hw.camera.abort_acquisition()
            self._camera_running = False

    def acquire_one_cycle(
        self,
        dark: Optional[np.ndarray] = None,
        raw_callback: Optional[Callable] = None,
    ) -> np.ndarray:
        """Acquire one delta-signal measurement at the current position.

        For ``chopper_2x2``, reads frames from the already-running camera.
        For other modes, delegates to the existing mode-specific functions.

        Args:
            dark: Optional dark spectrum to subtract.
            raw_callback: Optional ``(pumped, ref, n_matched, n_discarded,
                n_frames)`` callback for live display.

        Returns:
            Averaged ΔI/I₀ spectrum (1-D numpy array).
        """
        config = self._config

        if self._is_chopper:
            return self._acquire_chopper_cycle(dark, raw_callback)
        if config.acquisition_mode == "shot_to_shot" and self._phase_reader is not None:
            return _acquire_shot_to_shot(
                self._hw, config, dark, self._phase_reader,
                raw_callback=raw_callback,
            )
        return _acquire_software(self._hw, config, dark, raw_callback=raw_callback)

    def _acquire_chopper_cycle(
        self,
        dark: Optional[np.ndarray],
        raw_callback: Optional[Callable],
    ) -> np.ndarray:
        """Read one cycle of frames from the already-running camera."""
        camera = self._hw.camera
        config = self._config
        spf = getattr(config, "shots_per_frame", 2)
        n_target = int(config.n_averages * 2.2) + 10

        frame_period_ms = spf  # 2 ms for 500 Hz, 4 ms for 250 Hz
        wait_s = (n_target * frame_period_ms) / 1000.0 + 0.05
        time.sleep(wait_s)

        frames, n_chunk = camera.get_buffered_frames()
        if n_chunk == 0:
            raise RuntimeError(
                "chopper_2x2: no frames in cycle — check trigger"
            )

        tags = self._phase_reader.read_tags(n_chunk * spf)
        return _process_chopper_frames(
            frames, tags, config, dark, raw_callback,
        )
