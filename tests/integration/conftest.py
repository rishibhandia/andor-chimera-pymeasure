"""Integration test configuration — hardware marker and fixtures.

Tests marked ``@pytest.mark.hardware`` are skipped by default.
Pass ``--hardware`` to run them::

    uv run pytest tests/integration/ --hardware -v
"""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--hardware",
        action="store_true",
        default=False,
        help="Run tests that require real hardware (camera, NI DAQ, …)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--hardware"):
        return
    skip_hw = pytest.mark.skip(reason="needs --hardware flag to run")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hw)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

SDK_PATH = r"C:\Program Files\Andor SDK"
NIDAQ_DEVICE = "Astrella_DAQ"
PFI0 = f"/{NIDAQ_DEVICE}/PFI0"
PFI12 = f"/{NIDAQ_DEVICE}/PFI12"
PFI13 = f"/{NIDAQ_DEVICE}/PFI13"
DI_CHANNEL = f"{NIDAQ_DEVICE}/port0/line0"


# ---------------------------------------------------------------------------
# Camera fixture — function-scoped, init/shutdown per test
# ---------------------------------------------------------------------------

@pytest.fixture
def camera():
    """Initialize real Andor camera, yield it, then shut down.

    Function-scoped so the SDK is fully released between tests.
    """
    os.environ.pop("ANDOR_MOCK", None)

    from andor_pymeasure.instruments.andor_camera import AndorCamera

    cam = AndorCamera(sdk_path=SDK_PATH)
    cam.initialize()
    yield cam
    cam.shutdown()


@pytest.fixture
def spectrograph():
    """Initialize real Andor spectrograph, yield it, then shut down."""
    os.environ.pop("ANDOR_MOCK", None)

    from andor_pymeasure.instruments.andor_spectrograph import AndorSpectrograph

    spec = AndorSpectrograph(device_index=0, sdk_path=SDK_PATH)
    spec.initialize()
    yield spec
    spec.shutdown()


@pytest.fixture
def phase_reader():
    """Create (but don't start) a real NI DAQ phase reader.

    Teardown stops it if still running.
    """
    from andor_qt.ta.nidaq_phase import NIDAQPhaseReader

    reader = NIDAQPhaseReader(
        device=NIDAQ_DEVICE,
        di_channel="port0/line0",
        clock_source=PFI0,
        clock_rate=1000.0,
    )
    yield reader
    try:
        reader.stop()
    except Exception:
        pass
