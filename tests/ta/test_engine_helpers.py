"""Unit tests for pure helper functions in andor_qt.ta.engine.

Tests cover:
- _format_time: seconds to human-readable duration
- _format_eta: estimated time remaining formatting
- _estimate_point_time_s: per-point acquisition time estimation
- _make_scan_folder: timestamped folder creation
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from andor_qt.ta.engine import (
    _estimate_point_time_s,
    _format_eta,
    _format_time,
    _make_scan_folder,
)


# =========================================================================
# _format_time
# =========================================================================


class TestFormatTime:
    """Tests for _format_time(seconds)."""

    def test_zero_seconds(self):
        assert _format_time(0) == "0s"

    def test_sub_minute_integer(self):
        assert _format_time(30) == "30s"

    def test_sub_minute_fraction_rounds(self):
        """Fractional seconds are rounded to nearest integer."""
        assert _format_time(29.6) == "30s"
        assert _format_time(0.4) == "0s"

    def test_exactly_59_seconds(self):
        assert _format_time(59) == "59s"

    def test_exactly_60_seconds_shows_minutes(self):
        assert _format_time(60) == "1.0m"

    def test_90_seconds_shows_minutes(self):
        assert _format_time(90) == "1.5m"

    def test_sub_hour_minutes(self):
        assert _format_time(300) == "5.0m"

    def test_exactly_3599_seconds_still_minutes(self):
        result = _format_time(3599)
        assert result.endswith("m")

    def test_exactly_3600_seconds_shows_hours(self):
        assert _format_time(3600) == "1.0h"

    def test_7200_seconds_shows_hours(self):
        assert _format_time(7200) == "2.0h"

    def test_5400_seconds_shows_1_5_hours(self):
        assert _format_time(5400) == "1.5h"

    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0, "0s"),
            (1, "1s"),
            (30, "30s"),
            (59, "59s"),
            (60, "1.0m"),
            (90, "1.5m"),
            (600, "10.0m"),
            (3600, "1.0h"),
            (7200, "2.0h"),
        ],
    )
    def test_parametrized(self, seconds, expected):
        assert _format_time(seconds) == expected


# =========================================================================
# _format_eta
# =========================================================================


class TestFormatEta:
    """Tests for _format_eta(elapsed_s, completed, remaining, est_per_pt_s)."""

    def test_no_completed_no_estimate_returns_ellipsis(self):
        """When nothing is completed and no estimate, return '...'."""
        result = _format_eta(elapsed_s=0.0, completed=0, remaining=10)
        assert result == "..."

    def test_no_completed_with_zero_estimate_returns_ellipsis(self):
        """Zero est_per_pt_s is treated as no estimate."""
        result = _format_eta(elapsed_s=0.0, completed=0, remaining=10, est_per_pt_s=0.0)
        assert result == "..."

    def test_no_completed_with_estimate(self):
        """Before any point completes, use est_per_pt_s * remaining."""
        result = _format_eta(elapsed_s=0.0, completed=0, remaining=10, est_per_pt_s=3.0)
        # 3.0 * 10 = 30s -> "~30s"
        assert result == "~30s"

    def test_no_completed_with_estimate_minutes(self):
        """Estimate that results in minutes includes tilde prefix."""
        result = _format_eta(elapsed_s=0.0, completed=0, remaining=100, est_per_pt_s=6.0)
        # 6.0 * 100 = 600s -> "~10.0m"
        assert result == "~10.0m"

    def test_all_completed_returns_zero(self):
        """When remaining == 0, ETA should be 0s."""
        result = _format_eta(elapsed_s=30.0, completed=10, remaining=0)
        assert result == "0s"

    def test_half_completed_extrapolates(self):
        """Extrapolate from elapsed/completed rate."""
        # 5 points in 10s -> 2s/pt, 5 remaining -> 10s
        result = _format_eta(elapsed_s=10.0, completed=5, remaining=5)
        assert result == "10s"

    def test_one_completed_extrapolates(self):
        """Single completed point provides the rate."""
        # 1 point in 3s -> 3s/pt, 9 remaining -> 27s
        result = _format_eta(elapsed_s=3.0, completed=1, remaining=9)
        assert result == "27s"

    def test_completed_ignores_est_per_pt(self):
        """Once points are completed, est_per_pt_s is not used."""
        # 2 points in 10s -> 5s/pt, 2 remaining -> 10s
        result = _format_eta(
            elapsed_s=10.0, completed=2, remaining=2, est_per_pt_s=100.0
        )
        assert result == "10s"

    def test_estimate_prefix_is_tilde(self):
        """Pre-estimate results always start with '~'."""
        result = _format_eta(elapsed_s=0.0, completed=0, remaining=5, est_per_pt_s=2.0)
        assert result.startswith("~")

    def test_extrapolated_does_not_have_tilde(self):
        """Extrapolated results do NOT start with '~'."""
        result = _format_eta(elapsed_s=10.0, completed=5, remaining=5)
        assert not result.startswith("~")


# =========================================================================
# _estimate_point_time_s
# =========================================================================


class TestEstimatePointTimeS:
    """Tests for _estimate_point_time_s(camera_settings, n_averages, static)."""

    def test_none_settings_returns_default(self):
        """None camera_settings uses 0.002s default frame period."""
        # 0.002 * 2 * 10 = 0.04  (non-static doubles frames)
        result = _estimate_point_time_s(None, n_averages=10, static=False)
        assert result == pytest.approx(0.04)

    def test_none_settings_static(self):
        """None camera_settings, static mode: n_averages frames only."""
        # 0.002 * 10 = 0.02
        result = _estimate_point_time_s(None, n_averages=10, static=True)
        assert result == pytest.approx(0.02)

    def test_fast_external_trigger(self):
        """fast_external trigger returns 0.001s per frame."""
        settings = {"trigger_mode": "fast_external", "exposure_time": 0.0004}
        # 0.001 * 2 * 5 = 0.01
        result = _estimate_point_time_s(settings, n_averages=5, static=False)
        assert result == pytest.approx(0.01)

    def test_fast_external_static(self):
        """fast_external + static: n_averages * 0.001."""
        settings = {"trigger_mode": "fast_external"}
        # 0.001 * 5 = 0.005
        result = _estimate_point_time_s(settings, n_averages=5, static=True)
        assert result == pytest.approx(0.005)

    def test_internal_trigger_uses_exposure_plus_readout(self):
        """Internal trigger estimates exposure + readout time."""
        settings = {
            "trigger_mode": "internal",
            "exposure_time": 0.1,
            "vs_speed": 1,
            "hs_speed": 1,
        }
        result = _estimate_point_time_s(settings, n_averages=1, static=False)
        # Should be > exposure_time (exposure + readout) * 2 frames
        assert result > 0.1 * 2

    def test_non_static_doubles_frames(self):
        """Non-static mode acquires 2x n_averages frames (pump + ref)."""
        settings = {"trigger_mode": "fast_external"}
        result_static = _estimate_point_time_s(settings, n_averages=10, static=True)
        result_normal = _estimate_point_time_s(settings, n_averages=10, static=False)
        assert result_normal == pytest.approx(2 * result_static)

    def test_single_average(self):
        """n_averages=1 still works correctly."""
        settings = {"trigger_mode": "fast_external"}
        result = _estimate_point_time_s(settings, n_averages=1, static=True)
        assert result == pytest.approx(0.001)

    def test_result_is_positive(self):
        """Result should always be positive for reasonable inputs."""
        settings = {"trigger_mode": "internal", "exposure_time": 0.01}
        result = _estimate_point_time_s(settings, n_averages=1, static=True)
        assert result > 0


# =========================================================================
# _make_scan_folder
# =========================================================================


class TestMakeScanFolder:
    """Tests for _make_scan_folder(base_dir, sample_name)."""

    def test_creates_directory(self, tmp_path):
        """Created folder must exist on disk."""
        folder = _make_scan_folder(str(tmp_path), "test_sample")
        assert folder.exists()
        assert folder.is_dir()

    def test_returns_path_object(self, tmp_path):
        """Return value is a pathlib.Path."""
        folder = _make_scan_folder(str(tmp_path), "sample")
        assert isinstance(folder, Path)

    def test_timestamp_format_in_name(self, tmp_path):
        """Folder name contains YYYY-MM-DD_HHMMSS timestamp."""
        folder = _make_scan_folder(str(tmp_path), "sample")
        name = folder.name
        # Match pattern like 2026-04-01_143022_sample
        assert re.match(r"\d{4}-\d{2}-\d{2}_\d{6}_sample", name)

    def test_includes_sample_name(self, tmp_path):
        """Folder name ends with sample_name after timestamp."""
        folder = _make_scan_folder(str(tmp_path), "GaP_crystal")
        assert folder.name.endswith("_GaP_crystal")

    def test_empty_sample_name_timestamp_only(self, tmp_path):
        """Empty sample_name produces timestamp-only folder name."""
        folder = _make_scan_folder(str(tmp_path), "")
        name = folder.name
        # Should be just YYYY-MM-DD_HHMMSS without trailing underscore
        assert re.match(r"^\d{4}-\d{2}-\d{2}_\d{6}$", name)

    def test_default_sample_name_is_empty(self, tmp_path):
        """sample_name defaults to empty string."""
        folder = _make_scan_folder(str(tmp_path))
        name = folder.name
        assert re.match(r"^\d{4}-\d{2}-\d{2}_\d{6}$", name)

    def test_creates_nested_parents(self, tmp_path):
        """Creates intermediate directories if they don't exist."""
        deep_base = str(tmp_path / "level1" / "level2")
        folder = _make_scan_folder(deep_base, "sample")
        assert folder.exists()

    def test_is_subdirectory_of_base(self, tmp_path):
        """Created folder is a direct child of base_dir."""
        folder = _make_scan_folder(str(tmp_path), "sample")
        assert folder.parent == tmp_path

    def test_idempotent_same_timestamp(self, tmp_path):
        """Calling twice with same frozen time does not raise."""
        from datetime import datetime as real_datetime

        frozen = real_datetime(2026, 4, 1, 14, 30, 22)
        with patch("datetime.datetime") as mock_dt:
            mock_dt.now.return_value = frozen
            folder1 = _make_scan_folder(str(tmp_path), "sample")
            folder2 = _make_scan_folder(str(tmp_path), "sample")
        # Both should succeed (exist_ok=True) and point to same path
        assert folder1 == folder2
        assert folder1.exists()

    def test_folder_name_with_frozen_time(self, tmp_path):
        """Verify exact folder name with a frozen timestamp."""
        from datetime import datetime as real_datetime

        frozen = real_datetime(2026, 4, 1, 9, 5, 3)
        with patch("datetime.datetime") as mock_dt:
            mock_dt.now.return_value = frozen
            folder = _make_scan_folder(str(tmp_path), "myexp")
        assert folder.name == "2026-04-01_090503_myexp"
