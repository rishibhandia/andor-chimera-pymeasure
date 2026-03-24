"""Tests for readout time calculator."""
import pytest
from andor_qt.utils.readout_time import (
    VS_SPEEDS_US,
    HS_RATES_HZ,
    calculate_readout_time_ms,
)


class TestLookupTables:
    def test_vs_speeds_has_five_entries(self):
        assert len(VS_SPEEDS_US) == 5

    def test_vs_index_0_is_fastest(self):
        assert VS_SPEEDS_US[0] < VS_SPEEDS_US[1]

    def test_hs_rates_has_three_entries(self):
        assert len(HS_RATES_HZ) == 3

    def test_hs_index_0_is_fastest(self):
        assert HS_RATES_HZ[0] > HS_RATES_HZ[1]


class TestFVBReadout:
    """FVB: all rows binned into one horizontal readout."""

    def test_fvb_3mhz_fast_vs(self):
        # 200 rows × 4.9 µs + 1600 px / 3 MHz = 0.98 + 0.533 = ~1.51 ms
        t = calculate_readout_time_ms("fvb", n_rows=200, n_pixels=1600,
                                     vs_idx=0, hs_idx=0)
        assert 1.4 < t < 1.7

    def test_fvb_50khz(self):
        # 200 × 4.9 µs + 1600 / 50,000 = 0.98 ms + 32 ms = ~33 ms
        t = calculate_readout_time_ms("fvb", n_rows=200, n_pixels=1600,
                                     vs_idx=0, hs_idx=2)
        assert 30 < t < 36

    def test_fvb_hbin_halves_hs_time(self):
        t1 = calculate_readout_time_ms("fvb", n_rows=200, n_pixels=1600,
                                      vs_idx=0, hs_idx=2, hbin=1)
        t2 = calculate_readout_time_ms("fvb", n_rows=200, n_pixels=1600,
                                      vs_idx=0, hs_idx=2, hbin=2)
        # hbin=2 halves the HS term; VS term stays the same
        assert t2 < t1


class TestImageReadout:
    """Image mode: each row shifted then read."""

    def test_image_full_3mhz_fast_vs(self):
        # 200 × (4.9 µs + 1600/3e6) = 200 × 538 µs ≈ 107.6 ms
        t = calculate_readout_time_ms("image", n_rows=200, n_pixels=1600,
                                     vs_idx=0, hs_idx=0)
        assert 100 < t < 115

    def test_image_50khz_15rows_under_500ms(self):
        t = calculate_readout_time_ms("image", n_rows=15, n_pixels=1600,
                                     vs_idx=0, hs_idx=2)
        assert t < 500

    def test_image_50khz_16rows_over_500ms(self):
        t = calculate_readout_time_ms("image", n_rows=16, n_pixels=1600,
                                     vs_idx=0, hs_idx=2)
        assert t > 500

    def test_image_vbin_reduces_hs_cycles(self):
        # vbin=10 means 10× fewer horizontal readout cycles
        t1 = calculate_readout_time_ms("image", n_rows=200, n_pixels=1600,
                                      vs_idx=0, hs_idx=0, vbin=1)
        t2 = calculate_readout_time_ms("image", n_rows=200, n_pixels=1600,
                                      vs_idx=0, hs_idx=0, vbin=10)
        assert t2 < t1

    def test_image_hbin_reduces_hs_time(self):
        t1 = calculate_readout_time_ms("image", n_rows=20, n_pixels=1600,
                                      vs_idx=0, hs_idx=2, hbin=1)
        t2 = calculate_readout_time_ms("image", n_rows=20, n_pixels=1600,
                                      vs_idx=0, hs_idx=2, hbin=2)
        assert t2 < t1

class TestCropReadout:
    """Isolated crop mode: all crop rows binned then one horizontal readout."""

    def test_crop_20rows_3mhz_under_1ms(self):
        # TA use case: 20-row crop at 3 MHz → ~0.63 ms (matches 1515 spectra/sec)
        t = calculate_readout_time_ms("crop", n_rows=20, n_pixels=1600,
                                     vs_idx=0, hs_idx=0)
        assert t < 1.0

    def test_crop_matches_fvb_formula(self):
        t_crop = calculate_readout_time_ms("crop", n_rows=20, n_pixels=1600,
                                          vs_idx=0, hs_idx=0)
        t_fvb = calculate_readout_time_ms("fvb", n_rows=20, n_pixels=1600,
                                         vs_idx=0, hs_idx=0)
        assert t_crop == t_fvb

    def test_full_fvb_200rows_3mhz_approx_1_5ms(self):
        t = calculate_readout_time_ms("fvb", n_rows=200, n_pixels=1600,
                                     vs_idx=0, hs_idx=0)
        assert 1.4 < t < 1.7
