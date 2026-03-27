"""Integration tests: validate readout time formula against SDK GetReadOutTime().

These tests require real hardware (camera connected). They are skipped
automatically when ANDOR_MOCK=1 or the camera fails to initialize.

Run with:
    uv run pytest tests/integration/test_readout_time_sdk.py -v
"""

from __future__ import annotations

import os

import pytest

from andor_qt.utils.readout_time import VS_SPEEDS_US, HS_RATES_HZ, calculate_readout_time_ms

SDK_PATH = r"C:\Program Files\Andor SDK"

_skip_hardware = pytest.mark.skipif(
    os.environ.get("ANDOR_MOCK", "0") == "1",
    reason="Requires real camera hardware",
)

# SDK readout times measured on DU970P (conventional amplifier, FVB mode)
# Format: (vs_idx, hs_idx, hbin) -> sdk_readout_ms
SDK_REFERENCE = {
    (0,0,1):1.555,(0,0,2):1.465,(0,0,4):1.465,(0,0,8):1.535,(0,0,16):1.735,
    (0,1,1):2.744,(0,1,2):2.124,(0,1,4):1.864,(0,1,8):1.804,(0,1,16):1.934,
    (0,2,1):34.168,(0,2,2):19.648,(0,2,4):12.428,(0,2,8):8.898,(0,2,16):7.288,
    (1,0,1):2.477,(1,0,2):2.387,(1,0,4):2.387,(1,0,8):2.457,(1,0,16):2.657,
    (1,1,1):3.665,(1,1,2):3.045,(1,1,4):2.785,(1,1,8):2.725,(1,1,16):2.855,
    (1,2,1):35.089,(1,2,2):20.569,(1,2,4):13.349,(1,2,8):9.819,(1,2,16):8.209,
    (2,0,1):4.320,(2,0,2):4.230,(2,0,4):4.230,(2,0,8):4.300,(2,0,16):4.500,
    (2,1,1):5.509,(2,1,2):4.889,(2,1,4):4.629,(2,1,8):4.569,(2,1,16):4.699,
    (2,2,1):36.933,(2,2,2):22.413,(2,2,4):15.193,(2,2,8):11.663,(2,2,16):10.053,
    (3,0,1):8.006,(3,0,2):7.916,(3,0,4):7.916,(3,0,8):7.986,(3,0,16):8.186,
    (3,1,1):9.195,(3,1,2):8.575,(3,1,4):8.315,(3,1,8):8.255,(3,1,16):8.385,
    (3,2,1):40.619,(3,2,2):26.099,(3,2,4):18.879,(3,2,8):15.349,(3,2,16):13.739,
    (4,0,1):11.693,(4,0,2):11.603,(4,0,4):11.603,(4,0,8):11.673,(4,0,16):11.873,
    (4,1,1):12.881,(4,1,2):12.261,(4,1,4):12.001,(4,1,8):11.941,(4,1,16):12.071,
    (4,2,1):44.305,(4,2,2):29.785,(4,2,4):22.565,(4,2,8):19.035,(4,2,16):17.425,
}

N_ROWS = 200
N_PIXELS = 1600


class TestFormulaVsStoredReference:
    """Compare formula against stored SDK values (no hardware needed)."""

    @pytest.mark.parametrize(
        "vs_idx,hs_idx,hbin",
        [(vs, hs, hb) for vs in range(5) for hs in range(3) for hb in [1, 2, 4, 8, 16]],
    )
    def test_within_10_percent_offline(self, vs_idx, hs_idx, hbin):
        formula_ms = calculate_readout_time_ms(
            "fvb", N_ROWS, N_PIXELS, vs_idx, hs_idx, hbin
        )
        sdk_ms = SDK_REFERENCE[(vs_idx, hs_idx, hbin)]
        pct_error = abs(formula_ms - sdk_ms) / sdk_ms * 100
        assert pct_error < 10, (
            f"VS={vs_idx} HS={hs_idx} hbin={hbin}: "
            f"SDK={sdk_ms:.3f} formula={formula_ms:.3f} err={pct_error:.1f}%"
        )


@_skip_hardware
class TestFormulaVsSDKReference:
    """Compare formula predictions against stored SDK reference values."""

    @pytest.mark.parametrize(
        "vs_idx,hs_idx,hbin",
        [(vs, hs, hb) for vs in range(5) for hs in range(3) for hb in [1, 2, 4, 8, 16]],
    )
    def test_within_10_percent(self, vs_idx, hs_idx, hbin):
        sdk_ms = SDK_REFERENCE[(vs_idx, hs_idx, hbin)]
        formula_ms = calculate_readout_time_ms(
            "fvb", N_ROWS, N_PIXELS, vs_idx, hs_idx, hbin
        )
        pct_error = abs(formula_ms - sdk_ms) / sdk_ms * 100
        assert pct_error < 10, (
            f"VS={vs_idx} HS={hs_idx} hbin={hbin}: "
            f"SDK={sdk_ms:.3f} formula={formula_ms:.3f} err={pct_error:.1f}%"
        )

    def test_all_within_5_percent_count(self):
        """At least 90% of settings should be within 5% of SDK."""
        within_5 = 0
        total = len(SDK_REFERENCE)
        for (vs_idx, hs_idx, hbin), sdk_ms in SDK_REFERENCE.items():
            formula_ms = calculate_readout_time_ms(
                "fvb", N_ROWS, N_PIXELS, vs_idx, hs_idx, hbin
            )
            if abs(formula_ms - sdk_ms) / sdk_ms < 0.05:
                within_5 += 1
        assert within_5 >= total * 0.90, (
            f"Only {within_5}/{total} within 5% (need {int(total*0.9)})"
        )

    def test_formula_never_underestimates_by_more_than_15_percent(self):
        """Formula should not dangerously underestimate readout time."""
        for (vs_idx, hs_idx, hbin), sdk_ms in SDK_REFERENCE.items():
            formula_ms = calculate_readout_time_ms(
                "fvb", N_ROWS, N_PIXELS, vs_idx, hs_idx, hbin
            )
            underestimate_pct = (sdk_ms - formula_ms) / sdk_ms * 100
            assert underestimate_pct < 15, (
                f"VS={vs_idx} HS={hs_idx} hbin={hbin}: "
                f"underestimates by {underestimate_pct:.1f}%"
            )
