"""Tests for hardware-mode (NI DAQ) acquisition via acquire_delta_signal_at_delay.

Uses MockNIDAQPhaseReader and mock hardware — no real NI DAQ or camera needed.
"""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

import numpy as np
import pytest

from andor_qt.ta.acquisition import acquire_delta_signal_at_delay
from andor_qt.ta.nidaq_phase import MockNIDAQPhaseReader
from andor_qt.ta.scan_config import TAScanConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_hw(shot_values):
    """Make a mock hw_manager whose camera returns shot_values in order."""
    hw = MagicMock()
    hw.motion.get_axis.return_value = MagicMock()
    it = iter(shot_values)
    hw.camera.get_spectrum.side_effect = lambda: np.array(next(it), dtype=float)
    return hw


def make_config(n_averages=1):
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=n_averages,
        acquisition_mode="boxcar",
        scan_direction="forward",
        sample_name="test",
        nidaq_device="Dev1",
        nidaq_di_channel="port0/line0",
        nidaq_clock_source="/Dev1/PFI0",
        nidaq_clock_rate=1000.0,
    )


# ---------------------------------------------------------------------------
# TAScanConfig has nidaq fields
# ---------------------------------------------------------------------------


class TestTAScanConfigNIDAQFields:
    def test_has_nidaq_device(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_device")

    def test_has_nidaq_di_channel(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_di_channel")

    def test_has_nidaq_clock_source(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_clock_source")

    def test_has_nidaq_clock_rate(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert hasattr(cfg, "nidaq_clock_rate")

    def test_defaults(self):
        cfg = TAScanConfig(delay_list=[0.0])
        assert cfg.nidaq_device == "Astrella DAQ"
        assert cfg.nidaq_di_channel == "port0/line0"
        assert cfg.nidaq_clock_source == "/Astrella DAQ/PFI0"
        assert cfg.nidaq_clock_rate == 1000.0

    def test_yaml_roundtrip_preserves_nidaq_fields(self, tmp_path):
        cfg = TAScanConfig(
            delay_list=[1.0],
            nidaq_device="Dev2",
            nidaq_di_channel="port0/line3",
            nidaq_clock_source="/Dev2/PFI1",
            nidaq_clock_rate=500.0,
        )
        path = tmp_path / "cfg.yaml"
        cfg.to_yaml(path)
        loaded = TAScanConfig.from_yaml(path)
        assert loaded.nidaq_device == "Dev2"
        assert loaded.nidaq_di_channel == "port0/line3"
        assert loaded.nidaq_clock_source == "/Dev2/PFI1"
        assert loaded.nidaq_clock_rate == 500.0


# ---------------------------------------------------------------------------
# acquire_delta_signal_at_delay with hardware phase reader
# ---------------------------------------------------------------------------


class TestAcquireHardwarePhase:
    def test_returns_ndarray(self):
        n = 10
        hw = make_hw([[1000.0] * n, [800.0] * n])
        cfg = make_config(n_averages=1)
        reader = MockNIDAQPhaseReader(initial_phase=1)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        assert isinstance(result, np.ndarray)
        assert len(result) == n

    def test_pump_on_first_positive_delta(self):
        """Tag=1 → pump-on first → higher signal → positive ΔI/I₀."""
        n = 5
        on_val = 1200.0
        off_val = 1000.0
        hw = make_hw([[on_val] * n, [off_val] * n])
        cfg = make_config(n_averages=1)
        reader = MockNIDAQPhaseReader(initial_phase=1)  # starts with tag=1 (on)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        expected = (on_val - off_val) / off_val  # = 0.2
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_pump_off_first_still_correct(self):
        """initial_phase=0 → tag=0 first (off), tag=1 second (on) — result same."""
        n = 5
        on_val = 1200.0
        off_val = 1000.0
        # Camera returns off first, then on (phase reader tags them correctly)
        hw = make_hw([[off_val] * n, [on_val] * n])
        cfg = make_config(n_averages=1)
        reader = MockNIDAQPhaseReader(initial_phase=0)  # starts with tag=0 (off)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        expected = (on_val - off_val) / off_val  # = 0.2
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_identical_shots_gives_zero_delta(self):
        n = 8
        hw = make_hw([[1000.0] * n, [1000.0] * n])
        cfg = make_config(n_averages=1)
        reader = MockNIDAQPhaseReader(initial_phase=1)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        np.testing.assert_allclose(result, 0.0, atol=1e-10)

    def test_n_averages_uses_multiple_pairs(self):
        """With n_averages=3, camera.get_spectrum should be called 6 times."""
        n = 4
        # Provide 6 shots: alternating on/off
        shots = [[1200.0] * n if i % 2 == 0 else [1000.0] * n for i in range(6)]
        hw = make_hw(shots)
        cfg = make_config(n_averages=3)
        reader = MockNIDAQPhaseReader(initial_phase=1)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=reader)
        assert hw.camera.get_spectrum.call_count == 6
        assert isinstance(result, np.ndarray)

    def test_dark_subtraction_with_hardware_reader(self):
        n = 6
        on_val, off_val, dark_val = 1200.0, 1000.0, 100.0
        hw = make_hw([[on_val] * n, [off_val] * n])
        cfg = make_config(n_averages=1)
        reader = MockNIDAQPhaseReader(initial_phase=1)
        dark = np.ones(n) * dark_val
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, dark=dark, phase_reader=reader)
        expected = (on_val - dark_val - (off_val - dark_val)) / (off_val - dark_val)
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_no_phase_reader_still_works(self):
        """Passing phase_reader=None keeps old software-alternation behaviour."""
        n = 8
        hw = make_hw([[1000.0] * n, [1000.0] * n])
        cfg = make_config(n_averages=1)
        result = acquire_delta_signal_at_delay(0.0, hw, cfg, phase_reader=None)
        assert isinstance(result, np.ndarray)
        assert len(result) == n
