"""Tests for ChopperSync."""

from __future__ import annotations

import numpy as np
import pytest

from andor_qt.ta.chopper import ChopperSync


class TestChopperSyncSoftwareMode:
    def test_create_software_mode(self):
        chopper = ChopperSync(mode="software")
        assert chopper.mode == "software"

    def test_tag_shots_alternating(self):
        chopper = ChopperSync(mode="software")
        # 4 spectra, even indices = pump_on, odd = pump_off
        spectra = np.array([
            [10.0, 20.0],  # 0: pump_on
            [8.0, 16.0],   # 1: pump_off
            [10.5, 20.5],  # 2: pump_on
            [7.5, 15.5],   # 3: pump_off
        ])
        on_list, off_list = chopper.tag_shots(spectra)
        assert len(on_list) == 2
        assert len(off_list) == 2
        assert on_list[0] == pytest.approx(spectra[0])
        assert off_list[0] == pytest.approx(spectra[1])

    def test_tag_shots_odd_count_handled(self):
        chopper = ChopperSync(mode="software")
        # 3 spectra: last one (odd index = off) is orphan if 2 on but only 1 off
        spectra = np.array([
            [10.0],  # on
            [8.0],   # off
            [10.5],  # on — no corresponding off
        ])
        on_list, off_list = chopper.tag_shots(spectra)
        # Should not raise; may drop the last unmatched shot
        assert len(on_list) == len(off_list)

    def test_phase_check_returns_bool(self):
        chopper = ChopperSync(mode="software")
        spectra = np.ones((6, 100))
        # Small variance → phase ok or not; just verify it returns bool
        result = chopper.phase_check(spectra)
        assert isinstance(result, bool)

    def test_phase_check_detects_same_signal(self):
        chopper = ChopperSync(mode="software")
        # Identical spectra — no pump-probe modulation → phase suspect
        spectra = np.ones((4, 50))
        result = chopper.phase_check(spectra)
        assert result is False  # no variance → bad phase

    def test_phase_check_detects_alternating(self):
        chopper = ChopperSync(mode="software")
        # Strong alternation between on/off → good phase
        on_row = np.ones(50) * 100.0
        off_row = np.ones(50) * 50.0
        spectra = np.array([on_row, off_row, on_row, off_row])
        result = chopper.phase_check(spectra)
        assert result is True


class TestChopperSyncHardwareMode:
    def test_create_hardware_mode(self):
        chopper = ChopperSync(mode="hardware")
        assert chopper.mode == "hardware"

    def test_tag_shots_with_external_tags(self):
        chopper = ChopperSync(mode="hardware")
        spectra = np.array([
            [10.0, 20.0],
            [8.0, 16.0],
            [10.5, 20.5],
            [7.5, 15.5],
        ])
        tags = np.array([1, 0, 1, 0])  # 1=pump_on, 0=pump_off
        on_list, off_list = chopper.tag_shots(spectra, tags=tags)
        assert len(on_list) == 2
        assert len(off_list) == 2
        assert on_list[0] == pytest.approx(spectra[0])
        assert off_list[0] == pytest.approx(spectra[1])
