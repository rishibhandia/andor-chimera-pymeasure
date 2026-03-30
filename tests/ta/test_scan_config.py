"""Tests for TAScanConfig and delay list generator functions.

Tests cover:
- TAScanConfig dataclass fields and defaults
- ordered_delays() forward/alternating scan direction
- to_yaml() / from_yaml() round-trip
- linear_delays(), log_delays(), stage_delays_ps()
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from andor_qt.ta.scan_config import (
    TAScanConfig,
    linear_delays,
    log_delays,
    stage_delays_ps,
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
# stage_delays_ps
# ---------------------------------------------------------------------------

_C_MM_PS = 0.299792458


class TestStageScanHelpers:
    def test_stage_delays_ps_count(self):
        delays = stage_delays_ps(-57000.0, 3.0, 400)
        assert len(delays) == 400

    def test_stage_delays_ps_first_position(self):
        delays = stage_delays_ps(-57000.0, 3.0, 10)
        expected_first = (2 * (-57.0)) / _C_MM_PS
        assert delays[0] == pytest.approx(expected_first, rel=1e-6)

    def test_stage_delays_ps_uniform_step(self):
        delays = stage_delays_ps(0.0, 3.0, 5)
        step_ps = (2 * 0.003) / _C_MM_PS
        for i in range(1, len(delays)):
            assert delays[i] - delays[i - 1] == pytest.approx(step_ps, rel=1e-6)

    def test_stage_delays_ps_single_step(self):
        delays = stage_delays_ps(0.0, 3.0, 1)
        assert len(delays) == 1
        assert delays[0] == pytest.approx(0.0, abs=1e-10)

    def test_stage_delays_ps_returns_list(self):
        delays = stage_delays_ps(0.0, 1.0, 3)
        assert isinstance(delays, list)


# ---------------------------------------------------------------------------
# TAScanConfig — stage fields
# ---------------------------------------------------------------------------


class TestTAScanConfigStageFields:
    def test_default_stage_axis(self):
        config = TAScanConfig(delay_list=[0.0])
        assert config.stage_axis == 2

    def test_save_spectra_dir_default_none(self):
        config = TAScanConfig(delay_list=[0.0])
        assert config.save_spectra_dir is None

    def test_stage_axis_yaml_roundtrip(self, tmp_path):
        config = TAScanConfig(
            delay_list=[0.0, 1.0],
            stage_axis=2,
            save_spectra_dir="/tmp/spectra",
        )
        yaml_path = tmp_path / "config.yaml"
        config.to_yaml(yaml_path)
        loaded = TAScanConfig.from_yaml(yaml_path)
        assert loaded.stage_axis == 2
        assert loaded.save_spectra_dir == "/tmp/spectra"

    def test_from_yaml_backward_compat(self, tmp_path):
        """Old YAML without stage fields loads with defaults."""
        import yaml

        old_data = {
            "delay_list": [0.0, 1.0],
            "n_averages": 3,
            "n_scans": 1,
            "acquisition_mode": "boxcar",
            "scan_direction": "forward",
            "wavelengths": None,
            "sample_name": "old",
            "notes": "",
            "nidaq_device": "Astrella DAQ",
            "nidaq_di_channel": "port0/line0",
            "nidaq_clock_source": "/Astrella DAQ/PFI0",
            "nidaq_clock_rate": 1000.0,
        }
        yaml_path = tmp_path / "old_config.yaml"
        yaml_path.write_text(yaml.dump(old_data))
        loaded = TAScanConfig.from_yaml(yaml_path)
        assert loaded.stage_axis == 2
        assert loaded.save_spectra_dir is None


# ---------------------------------------------------------------------------
# Unit conversion functions
# ---------------------------------------------------------------------------


class TestUnitConversions:
    def test_ps_to_um_zero(self):
        from andor_qt.ta.scan_config import ps_to_um
        assert ps_to_um(0.0) == pytest.approx(0.0)

    def test_um_to_ps_zero(self):
        from andor_qt.ta.scan_config import um_to_ps
        assert um_to_ps(0.0) == pytest.approx(0.0)

    def test_roundtrip_ps_um_ps(self):
        from andor_qt.ta.scan_config import ps_to_um, um_to_ps
        ps = 10.0
        assert um_to_ps(ps_to_um(ps)) == pytest.approx(ps, rel=1e-10)

    def test_roundtrip_um_ps_um(self):
        from andor_qt.ta.scan_config import ps_to_um, um_to_ps
        um = -57000.0
        assert ps_to_um(um_to_ps(um)) == pytest.approx(um, rel=1e-10)


# ---------------------------------------------------------------------------
# linear_delays_um, log_delays_um
# ---------------------------------------------------------------------------


class TestLinearDelaysUm:
    def test_basic_forward(self):
        from andor_qt.ta.scan_config import linear_delays_um, um_to_ps
        result = linear_delays_um(0.0, 9.0, 3.0)
        assert len(result) == 4  # 0, 3, 6, 9 µm
        assert result[0] == pytest.approx(um_to_ps(0.0))
        assert result[-1] == pytest.approx(um_to_ps(9.0))

    def test_reverse_direction(self):
        from andor_qt.ta.scan_config import linear_delays_um, um_to_ps
        result = linear_delays_um(9.0, 0.0, 3.0)
        assert len(result) == 4
        assert result[0] == pytest.approx(um_to_ps(9.0))
        assert result[-1] == pytest.approx(um_to_ps(0.0))

    def test_single_point(self):
        from andor_qt.ta.scan_config import linear_delays_um, um_to_ps
        result = linear_delays_um(5.0, 5.0, 1.0)
        assert len(result) == 1
        assert result[0] == pytest.approx(um_to_ps(5.0))

    def test_overshoot_trimmed_forward(self):
        """Forward scan where last computed position exceeds end_um."""
        from andor_qt.ta.scan_config import linear_delays_um
        # 0, 3, 6, 9 — 12 would overshoot 10, so should be trimmed and 10 appended
        result = linear_delays_um(0.0, 10.0, 3.0)
        from andor_qt.ta.scan_config import um_to_ps
        assert result[-1] == pytest.approx(um_to_ps(10.0), rel=1e-6)

    def test_overshoot_trimmed_reverse(self):
        """Reverse scan where last computed position undershoots end_um."""
        from andor_qt.ta.scan_config import linear_delays_um
        result = linear_delays_um(10.0, 0.0, 3.0)
        from andor_qt.ta.scan_config import um_to_ps
        assert result[-1] == pytest.approx(um_to_ps(0.0), rel=1e-6)

    def test_step_zero_raises(self):
        from andor_qt.ta.scan_config import linear_delays_um
        with pytest.raises(ValueError, match="non-zero"):
            linear_delays_um(0.0, 10.0, 0.0)


class TestLogDelaysUm:
    def test_basic(self):
        from andor_qt.ta.scan_config import log_delays_um, um_to_ps
        result = log_delays_um(1.0, 1000.0, 3)
        assert len(result) > 2
        assert result[0] == pytest.approx(um_to_ps(1.0), rel=1e-3)
        assert result[-1] == pytest.approx(um_to_ps(1000.0), rel=1e-3)


# ---------------------------------------------------------------------------
# parse_manual_um
# ---------------------------------------------------------------------------


class TestParseManualUm:
    def test_plain_numbers(self):
        from andor_qt.ta.scan_config import parse_manual_um
        result = parse_manual_um("-57000, -56000, -55000")
        assert result == [-57000.0, -56000.0, -55000.0]

    def test_range_expression(self):
        from andor_qt.ta.scan_config import parse_manual_um
        result = parse_manual_um("range(0, 5, 1)")
        assert result == [0.0, 1.0, 2.0, 3.0, 4.0]

    def test_range_two_args(self):
        from andor_qt.ta.scan_config import parse_manual_um
        result = parse_manual_um("range(0, 3)")
        assert result == [0.0, 1.0, 2.0]

    def test_comments_ignored(self):
        from andor_qt.ta.scan_config import parse_manual_um
        result = parse_manual_um("# comment\n100\n# another\n200")
        assert result == [100.0, 200.0]

    def test_empty_lines_ignored(self):
        from andor_qt.ta.scan_config import parse_manual_um
        result = parse_manual_um("\n\n100\n\n200\n\n")
        assert result == [100.0, 200.0]

    def test_mixed_numbers_and_range(self):
        from andor_qt.ta.scan_config import parse_manual_um
        result = parse_manual_um("10, 20, range(100, 103)")
        assert result == [10.0, 20.0, 100.0, 101.0, 102.0]

    def test_multiline(self):
        from andor_qt.ta.scan_config import parse_manual_um
        text = "-57000\n-56000\n-55000"
        result = parse_manual_um(text)
        assert len(result) == 3

    def test_invalid_range_args_raises(self):
        from andor_qt.ta.scan_config import parse_manual_um
        with pytest.raises(ValueError, match="Invalid range"):
            parse_manual_um("range(1)")

    def test_invalid_range_four_args_raises(self):
        from andor_qt.ta.scan_config import parse_manual_um
        with pytest.raises(ValueError, match="Invalid range"):
            parse_manual_um("range(1, 2, 3, 4)")


# ---------------------------------------------------------------------------
# linear_delays validation
# ---------------------------------------------------------------------------


class TestLinearDelaysValidation:
    def test_step_zero_raises(self):
        with pytest.raises(ValueError, match="positive"):
            linear_delays(0.0, 10.0, 0.0)

    def test_step_negative_raises(self):
        with pytest.raises(ValueError, match="positive"):
            linear_delays(0.0, 10.0, -1.0)


class TestLogDelaysValidation:
    def test_start_zero_raises(self):
        with pytest.raises(ValueError, match="positive"):
            log_delays(0.0, 10.0, 5)

    def test_start_negative_raises(self):
        with pytest.raises(ValueError, match="positive"):
            log_delays(-1.0, 10.0, 5)
