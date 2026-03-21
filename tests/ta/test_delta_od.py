"""Tests for delta_OD computation functions."""

from __future__ import annotations

import numpy as np
import pytest

from andor_qt.ta.delta_od import (
    average_delta_od,
    background_subtract,
    compute_delta_od,
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


class TestComputeDeltaOD:
    def test_basic_delta_od(self):
        pump_on = np.array([90.0, 90.0, 90.0])
        pump_off = np.array([100.0, 100.0, 100.0])
        result = compute_delta_od(pump_on, pump_off)
        # ΔOD = -log10(on/off) = -log10(0.9) ≈ 0.0458
        expected = -np.log10(90.0 / 100.0)
        assert result == pytest.approx(expected * np.ones(3), rel=1e-5)

    def test_identical_spectra_gives_zero(self):
        spec = np.array([100.0, 200.0, 300.0])
        result = compute_delta_od(spec, spec)
        assert result == pytest.approx(np.zeros(3), abs=1e-10)

    def test_no_nan_or_inf(self):
        pump_on = np.array([0.0, 50.0, 100.0])
        pump_off = np.array([100.0, 100.0, 100.0])
        result = compute_delta_od(pump_on, pump_off)
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))

    def test_zero_pump_off_handled(self):
        pump_on = np.array([50.0])
        pump_off = np.array([0.0])
        result = compute_delta_od(pump_on, pump_off)
        assert not np.isnan(result[0])
        assert not np.isinf(result[0])

    def test_epsilon_prevents_division_by_zero(self):
        pump_on = np.array([1e-15])
        pump_off = np.array([0.0])
        result = compute_delta_od(pump_on, pump_off, epsilon=1e-10)
        assert not np.isinf(result[0])

    def test_returns_ndarray(self):
        result = compute_delta_od(np.array([1.0]), np.array([1.0]))
        assert isinstance(result, np.ndarray)


class TestAverageDeltaOD:
    def test_mean_of_identical_arrays(self):
        arr = np.array([1.0, 2.0, 3.0])
        mean, std = average_delta_od([arr, arr, arr])
        assert mean == pytest.approx(arr)
        assert std == pytest.approx(np.zeros(3), abs=1e-12)

    def test_mean_of_two_arrays(self):
        a = np.array([1.0, 2.0])
        b = np.array([3.0, 4.0])
        mean, std = average_delta_od([a, b])
        assert mean == pytest.approx([2.0, 3.0])

    def test_std_nonzero_for_different_arrays(self):
        a = np.array([0.0, 0.0])
        b = np.array([2.0, 2.0])
        mean, std = average_delta_od([a, b])
        assert std == pytest.approx([1.0, 1.0])

    def test_single_array(self):
        arr = np.array([1.0, 2.0, 3.0])
        mean, std = average_delta_od([arr])
        assert mean == pytest.approx(arr)
        assert std == pytest.approx(np.zeros(3), abs=1e-12)

    def test_returns_ndarray_tuple(self):
        result = average_delta_od([np.array([1.0])])
        assert isinstance(result[0], np.ndarray)
        assert isinstance(result[1], np.ndarray)
