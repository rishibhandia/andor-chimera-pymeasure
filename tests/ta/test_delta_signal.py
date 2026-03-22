"""Tests for delta_signal (ΔI/I₀) computation functions."""

from __future__ import annotations

import numpy as np
import pytest

from andor_qt.ta.delta_signal import (
    average_delta_signal,
    background_subtract,
    compute_delta_signal,
)


class TestBackgroundSubtract:
    def test_basic_subtraction(self):
        spectrum = np.array([10.0, 20.0, 30.0])
        dark = np.array([5.0, 5.0, 5.0])
        result = background_subtract(spectrum, dark)
        assert result == pytest.approx([5.0, 15.0, 25.0])

    def test_clips_to_zero(self):
        spectrum = np.array([3.0, 5.0, 10.0])
        dark = np.array([5.0, 5.0, 5.0])
        result = background_subtract(spectrum, dark)
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(0.0)
        assert result[2] == pytest.approx(5.0)

    def test_no_negative_values(self):
        spectrum = np.array([1.0, 2.0, 3.0])
        dark = np.array([10.0, 10.0, 10.0])
        result = background_subtract(spectrum, dark)
        assert np.all(result >= 0)

    def test_returns_ndarray(self):
        result = background_subtract(np.array([1.0, 2.0]), np.array([0.5, 0.5]))
        assert isinstance(result, np.ndarray)


class TestComputeDeltaSignal:
    def test_basic_delta_signal(self):
        pumped = np.array([90.0, 90.0, 90.0])
        ref = np.array([100.0, 100.0, 100.0])
        result = compute_delta_signal(pumped, ref)
        # ΔI/I₀ = (90 - 100) / 100 = -0.1
        assert result == pytest.approx([-0.1, -0.1, -0.1], rel=1e-5)

    def test_identical_spectra_gives_zero(self):
        spec = np.array([100.0, 200.0, 300.0])
        result = compute_delta_signal(spec, spec)
        assert result == pytest.approx(np.zeros(3), abs=1e-10)

    def test_increased_transmission_positive(self):
        pumped = np.array([110.0])
        ref = np.array([100.0])
        result = compute_delta_signal(pumped, ref)
        assert result[0] == pytest.approx(0.1, rel=1e-5)

    def test_no_nan_or_inf(self):
        pumped = np.array([0.0, 50.0, 100.0])
        ref = np.array([100.0, 100.0, 100.0])
        result = compute_delta_signal(pumped, ref)
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))

    def test_zero_ref_handled(self):
        pumped = np.array([50.0])
        ref = np.array([0.0])
        result = compute_delta_signal(pumped, ref)
        assert not np.isnan(result[0])
        assert not np.isinf(result[0])

    def test_returns_ndarray(self):
        result = compute_delta_signal(np.array([1.0]), np.array([1.0]))
        assert isinstance(result, np.ndarray)


class TestAverageDeltaSignal:
    def test_mean_of_identical_arrays(self):
        arr = np.array([1.0, 2.0, 3.0])
        mean, std = average_delta_signal([arr, arr, arr])
        assert mean == pytest.approx(arr)
        assert std == pytest.approx(np.zeros(3), abs=1e-12)

    def test_mean_of_two_arrays(self):
        a = np.array([1.0, 2.0])
        b = np.array([3.0, 4.0])
        mean, std = average_delta_signal([a, b])
        assert mean == pytest.approx([2.0, 3.0])

    def test_std_nonzero_for_different_arrays(self):
        a = np.array([0.0, 0.0])
        b = np.array([2.0, 2.0])
        mean, std = average_delta_signal([a, b])
        assert std == pytest.approx([1.0, 1.0])

    def test_single_array(self):
        arr = np.array([1.0, 2.0, 3.0])
        mean, std = average_delta_signal([arr])
        assert mean == pytest.approx(arr)
        assert std == pytest.approx(np.zeros(3), abs=1e-12)

    def test_returns_ndarray_tuple(self):
        result = average_delta_signal([np.array([1.0])])
        assert isinstance(result[0], np.ndarray)
        assert isinstance(result[1], np.ndarray)
