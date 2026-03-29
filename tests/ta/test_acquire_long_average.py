"""Tests for acquire_long_average shared routine."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from andor_qt.ta.acquisition import acquire_long_average


def _make_mock_camera(frame_shape: tuple = (100,), n_return: int = 50):
    """Create a mock camera that returns random frames from get_buffered_frames."""
    camera = MagicMock()
    camera.get_circular_buffer_size.return_value = 12000

    def _get_frames():
        frames = np.random.rand(n_return, *frame_shape).astype(np.float32) * 1000
        return frames, n_return

    camera.get_buffered_frames.side_effect = _get_frames
    return camera


class TestAcquireLongAverage:
    def test_returns_mean_std_count(self):
        camera = _make_mock_camera(n_return=100)
        abort = threading.Event()
        mean, std, count = acquire_long_average(camera, 100, abort)
        assert isinstance(mean, np.ndarray)
        assert isinstance(std, np.ndarray)
        assert count == 100

    def test_mean_shape_matches_frame(self):
        camera = _make_mock_camera(frame_shape=(200,), n_return=50)
        abort = threading.Event()
        mean, std, count = acquire_long_average(camera, 50, abort)
        assert mean.shape == (200,)
        assert std.shape == (200,)

    def test_aborts_early(self):
        camera = _make_mock_camera(n_return=10)
        abort = threading.Event()
        abort.set()  # pre-set abort
        with pytest.raises(RuntimeError, match="no frames"):
            acquire_long_average(camera, 100, abort)

    def test_progress_callback_called(self):
        camera = _make_mock_camera(n_return=50)
        abort = threading.Event()
        progress_calls = []

        def _cb(running_mean, collected, n_target):
            progress_calls.append((collected, n_target))

        acquire_long_average(camera, 50, abort, progress_cb=_cb)
        assert len(progress_calls) >= 1
        assert progress_calls[-1] == (50, 50)

    def test_no_frames_raises(self):
        camera = MagicMock()
        camera.get_circular_buffer_size.return_value = 12000
        camera.get_buffered_frames.return_value = (np.array([]), 0)
        abort = threading.Event()
        with pytest.raises(RuntimeError, match="no frames"):
            acquire_long_average(camera, 100, abort)

    def test_std_is_nonnegative(self):
        camera = _make_mock_camera(n_return=100)
        abort = threading.Event()
        _, std, _ = acquire_long_average(camera, 100, abort)
        assert np.all(std >= 0)

    def test_multi_chunk_accumulation(self):
        """When n_target > buffer, multiple chunks should accumulate correctly."""
        camera = MagicMock()
        # Small buffer forces multiple chunks
        camera.get_circular_buffer_size.return_value = 100
        call_count = [0]

        def _get_frames():
            call_count[0] += 1
            frames = np.ones((50, 10)) * 1000.0  # 50 frames of 10 pixels
            return frames, 50

        camera.get_buffered_frames.side_effect = _get_frames
        camera.start_run_till_abort.return_value = None
        camera.abort_acquisition.return_value = None

        abort = threading.Event()
        mean, std, count = acquire_long_average(camera, 150, abort)
        assert count == 150
        assert call_count[0] >= 2  # must have done at least 2 chunks
        np.testing.assert_allclose(mean, 1000.0, rtol=1e-6)
