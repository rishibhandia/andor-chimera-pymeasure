"""Direct unit tests for _process_chopper_frames.

This function is the core chopper_2x2 data processing pipeline:
  raw frames + phase tags -> tag alignment -> ON/OFF separation -> delta-I/I0

Tests cover tag alignment offset detection, frame grouping, dark subtraction,
division-by-zero protection, n_averages capping, callback invocation, and
the module-level last_acquisition_stats dict.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from andor_qt.ta.acquisition import _process_chopper_frames, last_acquisition_stats
from andor_qt.ta.scan_config import TAScanConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(n_averages: int = 100, shots_per_frame: int = 2) -> TAScanConfig:
    """Create a minimal TAScanConfig for chopper_2x2 tests."""
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=n_averages,
        acquisition_mode="chopper_2x2",
        scan_direction="forward",
        sample_name="test",
        shots_per_frame=shots_per_frame,
    )


def _make_frames_and_tags(
    on_value: float,
    off_value: float,
    n_on: int,
    n_off: int,
    n_pixels: int = 10,
    spf: int = 2,
    offset: int = 0,
    interleave: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Build synthetic frames and matching phase tags.

    When ``interleave=True`` frames alternate ON/OFF (the common case).
    Tags are constructed so that matched groups align at the given ``offset``.

    Args:
        on_value: Constant intensity for pump-ON frames.
        off_value: Constant intensity for pump-OFF frames.
        n_on: Number of ON frames to produce.
        n_off: Number of OFF frames to produce.
        n_pixels: Number of spectral pixels per frame.
        spf: shots_per_frame (tag group size).
        offset: Number of junk tags prepended to shift the alignment.
        interleave: If True, alternate ON/OFF; otherwise ON block then OFF block.

    Returns:
        (frames, tags) ready for _process_chopper_frames.
    """
    if interleave:
        # Alternate ON, OFF, ON, OFF, ...
        n_total = n_on + n_off
        frames = []
        group_tags = []
        idx_on = 0
        idx_off = 0
        for i in range(n_total):
            if i % 2 == 0 and idx_on < n_on:
                frames.append(np.full(n_pixels, on_value, dtype=np.float64))
                group_tags.append(1)
                idx_on += 1
            elif idx_off < n_off:
                frames.append(np.full(n_pixels, off_value, dtype=np.float64))
                group_tags.append(0)
                idx_off += 1
            else:
                # Remaining ON if OFF exhausted
                frames.append(np.full(n_pixels, on_value, dtype=np.float64))
                group_tags.append(1)
                idx_on += 1
    else:
        frames = (
            [np.full(n_pixels, on_value, dtype=np.float64)] * n_on
            + [np.full(n_pixels, off_value, dtype=np.float64)] * n_off
        )
        group_tags = [1] * n_on + [0] * n_off

    frames_arr = np.array(frames)

    # Build per-shot tags: each frame's tag repeated ``spf`` times (matched group).
    per_shot = []
    for t in group_tags:
        per_shot.extend([t] * spf)

    # Prepend ``offset`` junk alternating tags so the real alignment starts later.
    prefix = [((i + 1) % 2) for i in range(offset)]  # mismatched junk
    tags_arr = np.array(prefix + per_shot, dtype=np.int32)

    return frames_arr, tags_arr


# ---------------------------------------------------------------------------
# Fixture: clear stats before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_stats():
    """Ensure last_acquisition_stats is clean before and after each test."""
    last_acquisition_stats.clear()
    yield
    last_acquisition_stats.clear()


# ===========================================================================
# 1. Basic correctness
# ===========================================================================


class TestBasicCorrectness:
    """Given known ON/OFF intensities, verify delta-I/I0."""

    def test_uniform_on_off_returns_expected_delta(self):
        """ON=1200, OFF=1000 -> delta = (1200-1000)/1000 = 0.2."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=10, n_off=10, n_pixels=5, spf=2,
        )

        result = _process_chopper_frames(frames, tags, config)

        assert result.shape == (5,)
        np.testing.assert_allclose(result, 0.2, atol=1e-12)

    def test_negative_delta_when_on_less_than_off(self):
        """ON=800, OFF=1000 -> delta = (800-1000)/1000 = -0.2."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=800.0, off_value=1000.0,
            n_on=5, n_off=5, n_pixels=4, spf=2,
        )

        result = _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(result, -0.2, atol=1e-12)

    def test_zero_delta_when_on_equals_off(self):
        """ON=OFF -> delta = 0."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=500.0, off_value=500.0,
            n_on=6, n_off=6, n_pixels=3, spf=2,
        )

        result = _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(result, 0.0, atol=1e-12)


# ===========================================================================
# 2. Tag alignment offset detection
# ===========================================================================


class TestOffsetDetection:
    """With spf=2 and a non-zero offset, the function should auto-detect alignment."""

    def test_offset_1_correctly_detected(self):
        """Tags [0, 1,1, 0,0, 1,1, ...] (offset=1) should still work."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=8, n_off=8, n_pixels=5, spf=2, offset=1,
        )

        result = _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(result, 0.2, atol=1e-12)

    def test_offset_0_with_perfect_alignment(self):
        """Tags [1,1, 0,0, 1,1, ...] (offset=0) -- simplest case."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=6, n_off=6, n_pixels=4, spf=2, offset=0,
        )

        result = _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(result, 0.2, atol=1e-12)

    def test_offset_with_spf4(self):
        """spf=4, offset=2: tags start with 2 junk then groups of 4."""
        config = _make_config(n_averages=100, shots_per_frame=4)
        frames, tags = _make_frames_and_tags(
            on_value=1500.0, off_value=1000.0,
            n_on=4, n_off=4, n_pixels=3, spf=4, offset=2,
        )

        result = _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(result, 0.5, atol=1e-12)


# ===========================================================================
# 3. All-mismatched tags -> RuntimeError
# ===========================================================================


class TestAllMismatchedTags:
    """Tags like [1,0,1,0,...] with spf=2 produce 0 matched groups."""

    def test_alternating_tags_raise_runtime_error(self):
        """Every group has mixed tags -> 0 valid pairs -> RuntimeError."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_frames = 10
        n_pixels = 5
        frames = np.ones((n_frames, n_pixels), dtype=np.float64) * 1000.0
        # Every group of 2 is [1,0] -- no matched group
        tags = np.tile([1, 0], n_frames).astype(np.int32)

        with pytest.raises(RuntimeError, match="0 valid pairs"):
            _process_chopper_frames(frames, tags, config)

    def test_single_frame_mismatched_raises(self):
        """Only 1 frame with mismatched tag pair -> RuntimeError."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames = np.ones((1, 4), dtype=np.float64) * 500.0
        tags = np.array([1, 0], dtype=np.int32)

        with pytest.raises(RuntimeError, match="0 valid pairs"):
            _process_chopper_frames(frames, tags, config)


# ===========================================================================
# 4. Division by zero protection
# ===========================================================================


class TestDivisionByZeroProtection:
    """OFF frames with all-zero pixels should not crash (ref_safe guard)."""

    def test_zero_off_frames_do_not_crash(self):
        """OFF=0 everywhere. ref_safe replaces 0 with 1.0 so delta = (ON-0)/1 = ON."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=500.0, off_value=0.0,
            n_on=4, n_off=4, n_pixels=6, spf=2,
        )

        result = _process_chopper_frames(frames, tags, config)

        # delta = (500 - 0) / max(0, 1.0) = 500.0
        assert result.shape == (6,)
        np.testing.assert_allclose(result, 500.0, atol=1e-12)

    def test_partial_zero_pixels_in_off(self):
        """Some pixels zero in OFF, others non-zero. Mixed behavior per pixel."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_pixels = 4
        n_pairs = 3

        on_data = np.full(n_pixels, 1000.0)
        off_data = np.array([0.0, 500.0, 0.0, 200.0])

        frames = []
        group_tags = []
        for _ in range(n_pairs):
            frames.append(on_data.copy())
            group_tags.append(1)
            frames.append(off_data.copy())
            group_tags.append(0)

        frames_arr = np.array(frames)
        per_shot = []
        for t in group_tags:
            per_shot.extend([t, t])  # spf=2
        tags_arr = np.array(per_shot, dtype=np.int32)

        result = _process_chopper_frames(frames_arr, tags_arr, config)

        # pixel 0: (1000-0)/1.0 = 1000 (zero replaced by 1)
        # pixel 1: (1000-500)/500 = 1.0
        # pixel 2: (1000-0)/1.0 = 1000
        # pixel 3: (1000-200)/200 = 4.0
        expected = np.array([1000.0, 1.0, 1000.0, 4.0])
        np.testing.assert_allclose(result, expected, atol=1e-12)


# ===========================================================================
# 5. Dark subtraction
# ===========================================================================


class TestDarkSubtraction:
    """Verify dark frame is subtracted from both pump and ref before delta."""

    def test_dark_subtracted_from_both(self):
        """ON=1200, OFF=1000, dark=200 -> (1000-800)/800 = 0.25."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_pixels = 5
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=6, n_off=6, n_pixels=n_pixels, spf=2,
        )
        dark = np.full(n_pixels, 200.0)

        result = _process_chopper_frames(frames, tags, config, dark=dark)

        # pumped = 1200 - 200 = 1000, ref = 1000 - 200 = 800
        # delta = (1000 - 800) / 800 = 0.25
        np.testing.assert_allclose(result, 0.25, atol=1e-12)

    def test_dark_none_means_no_subtraction(self):
        """dark=None should give the same result as no dark at all."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=6, n_off=6, n_pixels=4, spf=2,
        )

        result_no_dark = _process_chopper_frames(frames, tags, config, dark=None)

        np.testing.assert_allclose(result_no_dark, 0.2, atol=1e-12)

    def test_dark_equal_to_off_triggers_ref_safe(self):
        """If dark == OFF, ref becomes all zero -> ref_safe guard kicks in."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_pixels = 3
        frames, tags = _make_frames_and_tags(
            on_value=1000.0, off_value=500.0,
            n_on=4, n_off=4, n_pixels=n_pixels, spf=2,
        )
        dark = np.full(n_pixels, 500.0)  # dark == OFF

        result = _process_chopper_frames(frames, tags, config, dark=dark)

        # pumped = 1000 - 500 = 500, ref = 500 - 500 = 0 -> ref_safe = 1
        # delta = (500 - 0) / 1 = 500
        np.testing.assert_allclose(result, 500.0, atol=1e-12)


# ===========================================================================
# 6. shots_per_frame = 4
# ===========================================================================


class TestShotsPerFrame4:
    """Verify 4-tag grouping: [1,1,1,1]=ON, [0,0,0,0]=OFF."""

    def test_spf4_basic(self):
        """Standard spf=4 case."""
        config = _make_config(n_averages=100, shots_per_frame=4)
        frames, tags = _make_frames_and_tags(
            on_value=1500.0, off_value=1000.0,
            n_on=5, n_off=5, n_pixels=4, spf=4,
        )

        result = _process_chopper_frames(frames, tags, config)

        # delta = (1500 - 1000) / 1000 = 0.5
        np.testing.assert_allclose(result, 0.5, atol=1e-12)

    def test_spf4_partial_group_discarded(self):
        """If tags have a partial group of 3 (not 4), it should be ignored."""
        config = _make_config(n_averages=100, shots_per_frame=4)
        n_pixels = 3
        n_on, n_off = 4, 4
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=n_on, n_off=n_off, n_pixels=n_pixels, spf=4,
        )
        # Append 3 extra tags that do not form a complete group
        tags = np.append(tags, [1, 1, 1])

        result = _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(result, 0.2, atol=1e-12)

    def test_spf4_mixed_group_discarded(self):
        """A group like [1,1,0,1] should be discarded as mismatched."""
        config = _make_config(n_averages=100, shots_per_frame=4)
        n_pixels = 3
        # Manually craft frames and tags with one mismatched group
        frames = np.array([
            np.full(n_pixels, 1200.0),  # frame 0: ON
            np.full(n_pixels, 1000.0),  # frame 1: OFF
            np.full(n_pixels, 999.0),   # frame 2: will be mismatched
            np.full(n_pixels, 1200.0),  # frame 3: ON
            np.full(n_pixels, 1000.0),  # frame 4: OFF
        ])
        # Tags: group 0 = [1,1,1,1] ON, group 1 = [0,0,0,0] OFF,
        #        group 2 = [1,1,0,1] MISMATCH, group 3 = [1,1,1,1] ON,
        #        group 4 = [0,0,0,0] OFF
        tags = np.array([
            1, 1, 1, 1,  # frame 0 -> ON
            0, 0, 0, 0,  # frame 1 -> OFF
            1, 1, 0, 1,  # frame 2 -> discarded
            1, 1, 1, 1,  # frame 3 -> ON
            0, 0, 0, 0,  # frame 4 -> OFF
        ], dtype=np.int32)

        result = _process_chopper_frames(frames, tags, config)

        # ON frames: [1200, 1200], OFF frames: [1000, 1000]
        # delta = (1200 - 1000) / 1000 = 0.2
        np.testing.assert_allclose(result, 0.2, atol=1e-12)


# ===========================================================================
# 7. Raw callback invoked
# ===========================================================================


class TestRawCallback:
    """Verify the raw_callback receives correct arguments."""

    def test_callback_receives_correct_args(self):
        """Callback should get (pump_mean, ref_mean, n_pairs, n_discarded, n_read)."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_pixels = 4
        n_on, n_off = 5, 5
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=n_on, n_off=n_off, n_pixels=n_pixels, spf=2,
        )

        callback = MagicMock()

        _process_chopper_frames(frames, tags, config, raw_callback=callback)

        callback.assert_called_once()
        args = callback.call_args[0]
        pump_mean, ref_mean, n_pairs, n_discarded, n_read = args

        np.testing.assert_allclose(pump_mean, 1200.0, atol=1e-12)
        np.testing.assert_allclose(ref_mean, 1000.0, atol=1e-12)
        assert n_pairs == min(n_on, n_off)
        assert n_discarded == 0
        assert n_read == n_on + n_off

    def test_callback_not_called_when_none(self):
        """No crash when raw_callback is None."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=4, n_off=4, n_pixels=3, spf=2,
        )

        # Should not raise
        result = _process_chopper_frames(frames, tags, config, raw_callback=None)
        assert result is not None

    def test_callback_reports_discarded_count(self):
        """When some groups are mismatched, n_discarded should be non-zero."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_pixels = 3
        # 4 frames: ON, OFF, mismatched, ON
        frames = np.array([
            np.full(n_pixels, 1200.0),
            np.full(n_pixels, 1000.0),
            np.full(n_pixels, 1100.0),
            np.full(n_pixels, 1200.0),
        ])
        # Tags at offset=0: group0=[1,1] ON, group1=[0,0] OFF,
        #                    group2=[1,0] MISMATCH, group3=[1,1] ON
        tags = np.array([1, 1, 0, 0, 1, 0, 1, 1], dtype=np.int32)

        callback = MagicMock()
        _process_chopper_frames(frames, tags, config, raw_callback=callback)

        args = callback.call_args[0]
        _, _, n_pairs, n_discarded, n_read = args
        assert n_discarded == 1  # the [1,0] group
        assert n_read == 4


# ===========================================================================
# 8. n_averages capping
# ===========================================================================


class TestNAveragesCapping:
    """If more ON/OFF frames exist than n_averages, only n_averages pairs are used."""

    def test_capped_at_n_averages(self):
        """100 ON, 100 OFF, but n_averages=50 -> only 50 pairs used."""
        n_averages = 50
        config = _make_config(n_averages=n_averages, shots_per_frame=2)
        n_on, n_off = 100, 100
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=n_on, n_off=n_off, n_pixels=4, spf=2,
        )

        callback = MagicMock()
        result = _process_chopper_frames(frames, tags, config, raw_callback=callback)

        # Result should still be correct
        np.testing.assert_allclose(result, 0.2, atol=1e-12)

        # n_pairs should be capped at n_averages
        args = callback.call_args[0]
        _, _, n_pairs, _, _ = args
        assert n_pairs == n_averages

    def test_fewer_pairs_than_n_averages_uses_all(self):
        """Only 5 ON, 5 OFF but n_averages=100 -> 5 pairs used."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_on, n_off = 5, 5
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=n_on, n_off=n_off, n_pixels=4, spf=2,
        )

        callback = MagicMock()
        _process_chopper_frames(frames, tags, config, raw_callback=callback)

        args = callback.call_args[0]
        _, _, n_pairs, _, _ = args
        assert n_pairs == 5

    def test_n_averages_1_uses_single_pair(self):
        """n_averages=1 -> only 1 pair, even with many frames."""
        config = _make_config(n_averages=1, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=20, n_off=20, n_pixels=3, spf=2,
        )

        callback = MagicMock()
        result = _process_chopper_frames(frames, tags, config, raw_callback=callback)

        args = callback.call_args[0]
        _, _, n_pairs, _, _ = args
        assert n_pairs == 1
        np.testing.assert_allclose(result, 0.2, atol=1e-12)


# ===========================================================================
# 9. Empty frames input
# ===========================================================================


class TestEmptyFrames:
    """Zero frames should raise RuntimeError."""

    def test_zero_frames_raises(self):
        """Empty frames array -> 0 valid pairs -> RuntimeError."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames = np.empty((0, 5), dtype=np.float64)
        tags = np.array([], dtype=np.int32)

        with pytest.raises(RuntimeError, match="0 valid pairs"):
            _process_chopper_frames(frames, tags, config)

    def test_frames_but_no_tags_raises(self):
        """Frames exist but tags array is empty -> 0 usable -> RuntimeError."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames = np.ones((5, 4), dtype=np.float64) * 1000.0
        tags = np.array([], dtype=np.int32)

        with pytest.raises(RuntimeError, match="0 valid pairs"):
            _process_chopper_frames(frames, tags, config)

    def test_too_few_tags_for_single_group(self):
        """Only 1 tag with spf=2 -> not enough for a group -> RuntimeError."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames = np.ones((1, 4), dtype=np.float64) * 1000.0
        tags = np.array([1], dtype=np.int32)

        with pytest.raises(RuntimeError, match="0 valid pairs"):
            _process_chopper_frames(frames, tags, config)


# ===========================================================================
# 10. last_acquisition_stats updated
# ===========================================================================


class TestLastAcquisitionStats:
    """Verify the module-level stats dict is populated correctly."""

    def test_stats_populated_after_processing(self):
        """All expected keys should be present and correct."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_on, n_off = 8, 8
        n_pixels = 5
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=n_on, n_off=n_off, n_pixels=n_pixels, spf=2,
        )

        _process_chopper_frames(frames, tags, config)

        assert "pump_mean" in last_acquisition_stats
        assert "pump_std" in last_acquisition_stats
        assert "ref_mean" in last_acquisition_stats
        assert "ref_std" in last_acquisition_stats
        assert "delta_std" in last_acquisition_stats
        assert "n_on" in last_acquisition_stats
        assert "n_off" in last_acquisition_stats

    def test_stats_n_on_n_off_counts(self):
        """n_on and n_off reflect ALL matched frames, not just used pairs."""
        config = _make_config(n_averages=50, shots_per_frame=2)
        n_on, n_off = 10, 10
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=n_on, n_off=n_off, n_pixels=4, spf=2,
        )

        _process_chopper_frames(frames, tags, config)

        assert last_acquisition_stats["n_on"] == n_on
        assert last_acquisition_stats["n_off"] == n_off

    def test_stats_pump_mean_shape(self):
        """pump_mean should be a 1-D array with n_pixels elements."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_pixels = 7
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=6, n_off=6, n_pixels=n_pixels, spf=2,
        )

        _process_chopper_frames(frames, tags, config)

        assert last_acquisition_stats["pump_mean"].shape == (n_pixels,)
        np.testing.assert_allclose(
            last_acquisition_stats["pump_mean"], 1200.0, atol=1e-12,
        )
        np.testing.assert_allclose(
            last_acquisition_stats["ref_mean"], 1000.0, atol=1e-12,
        )

    def test_stats_delta_std_zero_for_uniform_data(self):
        """When all ON and OFF frames are identical, delta_std should be 0."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=6, n_off=6, n_pixels=4, spf=2,
        )

        _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(
            last_acquisition_stats["delta_std"], 0.0, atol=1e-12,
        )

    def test_stats_pump_std_zero_for_uniform_on_frames(self):
        """When all ON frames are identical, pump_std should be 0."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=6, n_off=6, n_pixels=4, spf=2,
        )

        _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(
            last_acquisition_stats["pump_std"], 0.0, atol=1e-12,
        )
        np.testing.assert_allclose(
            last_acquisition_stats["ref_std"], 0.0, atol=1e-12,
        )


# ===========================================================================
# Edge cases and additional coverage
# ===========================================================================


class TestEdgeCases:
    """Additional boundary conditions and edge cases."""

    def test_single_pair(self):
        """Exactly 1 ON frame and 1 OFF frame -> 1 valid pair."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=1, n_off=1, n_pixels=4, spf=2,
        )

        result = _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(result, 0.2, atol=1e-12)

    def test_unequal_on_off_counts(self):
        """More ON than OFF frames. n_pairs = min(ON, OFF, n_averages)."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=10, n_off=3, n_pixels=4, spf=2,
            interleave=False,
        )

        callback = MagicMock()
        result = _process_chopper_frames(frames, tags, config, raw_callback=callback)

        np.testing.assert_allclose(result, 0.2, atol=1e-12)
        args = callback.call_args[0]
        _, _, n_pairs, _, _ = args
        assert n_pairs == 3  # min(10, 3, 100)

    def test_only_on_frames_no_off_raises(self):
        """All tags are 1 (pump-ON), zero OFF -> 0 valid pairs -> RuntimeError."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_frames = 6
        n_pixels = 4
        frames = np.ones((n_frames, n_pixels), dtype=np.float64) * 1000.0
        # All matched groups are ON: [1,1, 1,1, 1,1, ...]
        tags = np.ones(n_frames * 2, dtype=np.int32)

        with pytest.raises(RuntimeError, match="0 valid pairs"):
            _process_chopper_frames(frames, tags, config)

    def test_only_off_frames_no_on_raises(self):
        """All tags are 0 (pump-OFF), zero ON -> 0 valid pairs -> RuntimeError."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_frames = 6
        n_pixels = 4
        frames = np.ones((n_frames, n_pixels), dtype=np.float64) * 1000.0
        tags = np.zeros(n_frames * 2, dtype=np.int32)

        with pytest.raises(RuntimeError, match="0 valid pairs"):
            _process_chopper_frames(frames, tags, config)

    def test_large_number_of_frames(self):
        """Performance sanity: 1000 frames should still compute correctly."""
        config = _make_config(n_averages=500, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=500, n_off=500, n_pixels=100, spf=2,
        )

        result = _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(result, 0.2, atol=1e-12)
        assert result.shape == (100,)

    def test_single_pixel(self):
        """n_pixels=1: scalar-like spectrum should work."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=5, n_off=5, n_pixels=1, spf=2,
        )

        result = _process_chopper_frames(frames, tags, config)

        assert result.shape == (1,)
        np.testing.assert_allclose(result, 0.2, atol=1e-12)

    def test_more_tags_than_frames_uses_frame_count(self):
        """Tags array longer than needed -- only n_frames groups used."""
        config = _make_config(n_averages=100, shots_per_frame=2)
        n_pixels = 4
        n_on, n_off = 4, 4
        frames, tags = _make_frames_and_tags(
            on_value=1200.0, off_value=1000.0,
            n_on=n_on, n_off=n_off, n_pixels=n_pixels, spf=2,
        )
        # Append extra tags beyond what frames need
        extra_tags = np.array([1, 1, 0, 0, 1, 1, 0, 0], dtype=np.int32)
        tags = np.concatenate([tags, extra_tags])

        result = _process_chopper_frames(frames, tags, config)

        np.testing.assert_allclose(result, 0.2, atol=1e-12)
