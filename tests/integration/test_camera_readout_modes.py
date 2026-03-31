"""Integration test: compare camera readout modes.

Tests Run Till Abort batch read vs single-frame reads.  Verifies frame
rates and data integrity.

Run with::

    uv run pytest tests/integration/test_camera_readout_modes.py --hardware -v
"""

from __future__ import annotations

import time

import numpy as np
import pytest

pytestmark = pytest.mark.hardware

CAMERA_SETTINGS = {
    "trigger_mode": "fast_external",
    "exposure_time": 0.0004,
    "vs_speed_index": 0,
    "hs_speed_index": 0,
    "amplifier_type": 1,
    "preamp_gain_index": 0,
    "hbin": 1,
    "vbin": 1,
}


class TestRunTillAbortBatch:
    """Run Till Abort mode with batch read via get_buffered_frames."""

    def test_batch_read_returns_frames(self, camera):
        camera.apply_camera_settings(CAMERA_SETTINGS)
        camera.start_run_till_abort()

        try:
            # Wait for frames to accumulate (500 Hz × 0.5 s ≈ 250 frames)
            time.sleep(0.5)
            frames, n_chunk = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        assert n_chunk > 50, f"Expected >50 frames, got {n_chunk}"
        assert frames.shape[0] == n_chunk
        assert frames.shape[1] > 0  # at least 1 pixel

    def test_frame_rate_above_400hz(self, camera):
        """Camera should sustain >400 Hz with fast_external + overlap."""
        camera.apply_camera_settings(CAMERA_SETTINGS)
        camera.start_run_till_abort()

        try:
            time.sleep(1.0)
            frames, n_chunk = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        # n_chunk frames in ~1 second
        assert n_chunk > 400, (
            f"Frame rate {n_chunk}/s too low — is overlap enabled?"
        )

    def test_multiple_batch_reads(self, camera):
        """Successive batch reads return new frames each time."""
        camera.apply_camera_settings(CAMERA_SETTINGS)
        camera.start_run_till_abort()

        try:
            time.sleep(0.3)
            _, n1 = camera.get_buffered_frames()
            time.sleep(0.3)
            _, n2 = camera.get_buffered_frames()
            time.sleep(0.3)
            _, n3 = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        assert n1 > 0 and n2 > 0 and n3 > 0, (
            f"Batch reads: {n1}, {n2}, {n3} — some returned 0"
        )

    def test_frame_data_not_all_zeros(self, camera):
        """Frames should contain real data, not zeros."""
        camera.apply_camera_settings(CAMERA_SETTINGS)
        camera.start_run_till_abort()

        try:
            time.sleep(0.3)
            frames, n_chunk = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        assert n_chunk > 0
        mean_intensity = frames.mean()
        assert mean_intensity > 10, (
            f"Mean intensity {mean_intensity:.1f} — frames look blank"
        )


class TestSpectraQuality:
    """Verify spectral data quality from batch reads."""

    def test_spectra_shape_and_range(self, camera):
        camera.apply_camera_settings(CAMERA_SETTINGS)
        camera.start_run_till_abort()

        try:
            time.sleep(0.3)
            frames, n_chunk = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        assert n_chunk > 0
        # FVB mode: each frame is 1D (1600 pixels for DU970P)
        assert frames.ndim == 2
        assert frames.shape[1] == 1600, (
            f"Expected 1600 pixels, got {frames.shape[1]}"
        )

    def test_frame_to_frame_consistency(self, camera):
        """Consecutive frames should have similar mean intensity."""
        camera.apply_camera_settings(CAMERA_SETTINGS)
        camera.start_run_till_abort()

        try:
            time.sleep(0.5)
            frames, n_chunk = camera.get_buffered_frames()
        finally:
            camera.abort_acquisition()

        assert n_chunk >= 10
        frame_means = frames[:10].mean(axis=1)
        cv = frame_means.std() / frame_means.mean() * 100
        # With chopper, alternating frames differ by the chopper signal,
        # so CV could be ~50%. Without chopper, CV should be small.
        # Just assert it's not wildly variable.
        assert cv < 100, f"Frame means CV={cv:.1f}% — too variable"
