"""Tests for TAScanConfig and delay list generator functions.

Tests cover:
- TAScanConfig dataclass fields and defaults
- ordered_delays() forward/alternating scan direction
- to_yaml() / from_yaml() round-trip
- linear_delays(), log_delays(), custom_delays(), manual_delays()
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from andor_qt.ta.scan_config import (
    TAScanConfig,
    custom_delays,
    linear_delays,
    log_delays,
    manual_delays,
)


# ---------------------------------------------------------------------------
# TAScanConfig
# ---------------------------------------------------------------------------


class TestTAScanConfig:
    def _make_config(self, **kwargs) -> TAScanConfig:
        defaults = {
            "delay_list": [0.0, 1.0, 2.0, 5.0, 10.0],
            "n_averages": 3,
            "n_scans": 2,
            "acquisition_mode": "boxcar",
            "scan_direction": "forward",
            "wavelengths": None,
            "sample_name": "test_sample",
            "notes": "",
        }
        defaults.update(kwargs)
        return TAScanConfig(**defaults)

    def test_creates_with_defaults(self):
        config = self._make_config()
        assert config.n_averages == 3
        assert config.n_scans == 2
        assert config.sample_name == "test_sample"

    def test_delay_list_stored(self):
        delays = [0.0, 1.0, 5.0, 10.0]
        config = self._make_config(delay_list=delays)
        assert config.delay_list == delays

    def test_acquisition_mode_boxcar(self):
        config = self._make_config(acquisition_mode="boxcar")
        assert config.acquisition_mode == "boxcar"

    def test_acquisition_mode_shot_to_shot(self):
        config = self._make_config(acquisition_mode="shot_to_shot")
        assert config.acquisition_mode == "shot_to_shot"

    def test_scan_direction_forward(self):
        config = self._make_config(scan_direction="forward")
        assert config.scan_direction == "forward"

    def test_scan_direction_alternating(self):
        config = self._make_config(scan_direction="alternating")
        assert config.scan_direction == "alternating"


class TestOrderedDelays:
    def test_forward_always_same_order(self):
        delays = [1.0, 2.0, 3.0, 5.0]
        config = TAScanConfig(
            delay_list=delays,
            n_averages=1,
            n_scans=4,
            acquisition_mode="boxcar",
            scan_direction="forward",
            sample_name="test",
        )
        for i in range(4):
            assert config.ordered_delays(i) == delays

    def test_alternating_even_scan_is_forward(self):
        delays = [1.0, 2.0, 3.0]
        config = TAScanConfig(
            delay_list=delays,
            n_averages=1,
            n_scans=4,
            acquisition_mode="boxcar",
            scan_direction="alternating",
            sample_name="test",
        )
        assert config.ordered_delays(0) == delays
        assert config.ordered_delays(2) == delays

    def test_alternating_odd_scan_is_reversed(self):
        delays = [1.0, 2.0, 3.0]
        config = TAScanConfig(
            delay_list=delays,
            n_averages=1,
            n_scans=4,
            acquisition_mode="boxcar",
            scan_direction="alternating",
            sample_name="test",
        )
        assert config.ordered_delays(1) == list(reversed(delays))
        assert config.ordered_delays(3) == list(reversed(delays))


class TestTAScanConfigYAML:
    def test_yaml_roundtrip(self, tmp_path):
        delays = [0.0, 1.0, 5.0, 10.0, 50.0]
        config = TAScanConfig(
            delay_list=delays,
            n_averages=5,
            n_scans=3,
            acquisition_mode="shot_to_shot",
            scan_direction="alternating",
            wavelengths=[500.0, 600.0, 700.0],
            sample_name="rhodamine_6g",
            notes="test run",
        )
        yaml_path = tmp_path / "config.yaml"
        config.to_yaml(yaml_path)

        loaded = TAScanConfig.from_yaml(yaml_path)
        assert loaded.delay_list == delays
        assert loaded.n_averages == 5
        assert loaded.n_scans == 3
        assert loaded.acquisition_mode == "shot_to_shot"
        assert loaded.scan_direction == "alternating"
        assert loaded.wavelengths == [500.0, 600.0, 700.0]
        assert loaded.sample_name == "rhodamine_6g"
        assert loaded.notes == "test run"

    def test_yaml_file_created(self, tmp_path):
        config = TAScanConfig(
            delay_list=[0.0, 1.0],
            n_averages=1,
            n_scans=1,
            acquisition_mode="boxcar",
            scan_direction="forward",
            sample_name="test",
        )
        yaml_path = tmp_path / "out.yaml"
        config.to_yaml(yaml_path)
        assert yaml_path.exists()


# ---------------------------------------------------------------------------
# linear_delays
# ---------------------------------------------------------------------------


class TestLinearDelays:
    def test_basic_range(self):
        result = linear_delays(0.0, 10.0, 2.0)
        assert result == pytest.approx([0.0, 2.0, 4.0, 6.0, 8.0, 10.0])

    def test_single_point(self):
        result = linear_delays(5.0, 5.0, 1.0)
        assert result == [pytest.approx(5.0)]

    def test_returns_list(self):
        result = linear_delays(0.0, 5.0, 1.0)
        assert isinstance(result, list)

    def test_step_larger_than_range(self):
        # step > (end - start) → only start and end
        result = linear_delays(0.0, 3.0, 10.0)
        assert result[0] == pytest.approx(0.0)
        assert result[-1] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# log_delays
# ---------------------------------------------------------------------------


class TestLogDelays:
    def test_basic_log_range(self):
        result = log_delays(1.0, 1000.0, 3)
        assert len(result) == 10  # 3 per decade × log10(1000) = 3 decades
        assert result[0] == pytest.approx(1.0, rel=1e-5)
        assert result[-1] == pytest.approx(1000.0, rel=1e-5)

    def test_returns_list(self):
        result = log_delays(0.1, 100.0, 2)
        assert isinstance(result, list)

    def test_values_monotonically_increasing(self):
        result = log_delays(0.5, 500.0, 5)
        assert all(result[i] < result[i + 1] for i in range(len(result) - 1))

    def test_single_decade(self):
        result = log_delays(1.0, 10.0, 10)
        assert len(result) == 11  # 10 points per decade + endpoint
        assert result[0] == pytest.approx(1.0, rel=1e-5)
        assert result[-1] == pytest.approx(10.0, rel=1e-5)


# ---------------------------------------------------------------------------
# custom_delays
# ---------------------------------------------------------------------------


class TestCustomDelays:
    def test_single_linear_segment(self):
        segments = [{"type": "linear", "start": 0.0, "end": 5.0, "step": 1.0}]
        result = custom_delays(segments)
        assert result == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])

    def test_two_linear_segments_no_duplicates(self):
        segments = [
            {"type": "linear", "start": 0.0, "end": 2.0, "step": 1.0},
            {"type": "linear", "start": 2.0, "end": 4.0, "step": 1.0},
        ]
        result = custom_delays(segments)
        # Boundary point should not be duplicated
        assert result.count(2.0) == 1

    def test_log_segment(self):
        segments = [{"type": "log", "start": 1.0, "end": 10.0, "step": 5}]
        result = custom_delays(segments)
        assert result[0] == pytest.approx(1.0, rel=1e-5)
        assert result[-1] == pytest.approx(10.0, rel=1e-5)

    def test_returns_list(self):
        segments = [{"type": "linear", "start": 0.0, "end": 1.0, "step": 0.5}]
        assert isinstance(custom_delays(segments), list)


# ---------------------------------------------------------------------------
# manual_delays
# ---------------------------------------------------------------------------


class TestManualDelays:
    def test_returns_same_values(self):
        values = [0.0, 0.5, 1.0, 2.5, 5.0, 10.0]
        result = manual_delays(values)
        assert result == values

    def test_returns_list(self):
        result = manual_delays([1.0, 2.0])
        assert isinstance(result, list)

    def test_empty_list(self):
        result = manual_delays([])
        assert result == []

    def test_single_value(self):
        result = manual_delays([42.0])
        assert result == [42.0]
