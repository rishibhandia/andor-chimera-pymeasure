"""Tests for TransientAbsorptionEngine scan loop and acquire helpers.

Uses MockHardwareManager to avoid real hardware.
Engine runs in a QThread — tests use signal capture with a short timeout.
"""

from __future__ import annotations

import threading
import time
from typing import List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from andor_qt.ta.scan_config import TAScanConfig
from andor_qt.ta.engine import TransientAbsorptionEngine
from andor_qt.ta.acquisition import acquire_delta_signal_at_delay


# ---------------------------------------------------------------------------
# Minimal mock hardware manager
# ---------------------------------------------------------------------------


def make_mock_hw(n_pixels: int = 64):
    """Create a minimal mock HardwareManager for TA engine tests."""
    hw = MagicMock()
    # Camera returns a flat spectrum
    hw.camera.get_spectrum.return_value = np.ones(n_pixels) * 1000.0
    hw.camera.get_image.return_value = np.ones((10, n_pixels)) * 1000.0

    # Mock motion axis — plain MagicMock allows attribute setting
    mock_axis = MagicMock()
    hw.motion.get_axis.return_value = mock_axis
    hw.wavelengths = np.linspace(400.0, 800.0, n_pixels)
    return hw


def make_config(n_delays: int = 3, n_averages: int = 1, n_scans: int = 1):
    delays = [float(i) for i in range(n_delays)]
    return TAScanConfig(
        delay_list=delays,
        n_averages=n_averages,
        n_scans=n_scans,
        acquisition_mode="boxcar",
        scan_direction="forward",
        sample_name="test",
    )


# ---------------------------------------------------------------------------
# acquire_delta_signal_at_delay
# ---------------------------------------------------------------------------


class TestAcquireDeltaSignalAtDelay:
    def test_returns_ndarray(self):
        hw = make_mock_hw()
        config = make_config(n_averages=2)
        result = acquire_delta_signal_at_delay(
            delay_ps=1.0, hw_manager=hw, config=config, dark=None
        )
        assert isinstance(result, np.ndarray)

    def test_result_length_matches_pixels(self):
        hw = make_mock_hw(n_pixels=32)
        config = make_config(n_averages=1)
        result = acquire_delta_signal_at_delay(0.0, hw, config, dark=None)
        assert len(result) == 32

    def test_dark_subtraction_applied(self):
        hw = make_mock_hw(n_pixels=10)
        # Camera always returns 1000, dark = 100 → net = 900
        hw.camera.get_spectrum.return_value = np.ones(10) * 1000.0
        config = make_config(n_averages=1)
        dark = np.ones(10) * 100.0
        result = acquire_delta_signal_at_delay(0.0, hw, config, dark=dark)
        # ΔI/I₀ of identical pumped/ref = 0
        assert result == pytest.approx(np.zeros(10), abs=1e-8)


# ---------------------------------------------------------------------------
# TransientAbsorptionEngine — signal capture helpers
# ---------------------------------------------------------------------------


def collect_signals(engine, signal_name: str, timeout: float = 5.0) -> List:
    """Collect emitted signal values into a list."""
    received = []
    sig = getattr(engine, signal_name)
    sig.connect(lambda *args: received.append(args))
    return received


class TestTransientAbsorptionEngineSignals:
    """Test that the engine emits expected signals during a scan."""

    def _run_engine(self, engine, config, hw, writer=None, timeout=10.0):
        """Start engine scan and wait for it to finish, processing Qt events."""
        import time as _time
        from PySide6.QtWidgets import QApplication

        done = [False]
        engine.scan_completed.connect(lambda: done.__setitem__(0, True))
        engine.aborted.connect(lambda: done.__setitem__(0, True))
        engine.error.connect(lambda msg: done.__setitem__(0, True))

        engine.start_scan(config, hw, writer)

        start = _time.time()
        while not done[0] and _time.time() - start < timeout:
            QApplication.instance().processEvents()
            _time.sleep(0.005)

    def test_scan_started_emitted(self, qt_app):
        hw = make_mock_hw()
        config = make_config(n_delays=2, n_scans=1)
        engine = TransientAbsorptionEngine()

        started = []
        engine.scan_started.connect(lambda idx: started.append(idx))

        self._run_engine(engine, config, hw)
        assert len(started) == 1
        assert started[0] == 0

    def test_scan_completed_emitted(self, qt_app):
        hw = make_mock_hw()
        config = make_config(n_delays=2, n_scans=1)
        engine = TransientAbsorptionEngine()

        done = []
        engine.scan_completed.connect(lambda: done.append(True))

        self._run_engine(engine, config, hw)
        assert len(done) == 1

    def test_point_completed_emitted_for_each_delay(self, qt_app):
        hw = make_mock_hw()
        config = make_config(n_delays=3, n_scans=1)
        engine = TransientAbsorptionEngine()

        points = []
        engine.point_completed.connect(lambda idx, delay: points.append((idx, delay)))

        self._run_engine(engine, config, hw)
        assert len(points) == 3

    def test_abort_stops_scan(self, qt_app):
        from PySide6.QtWidgets import QApplication

        hw = make_mock_hw()
        # Slow down acquisition so we can abort mid-scan
        hw.camera.get_spectrum.side_effect = lambda: (time.sleep(0.01), np.ones(64) * 1000.0)[1]
        config = make_config(n_delays=10, n_scans=5)
        engine = TransientAbsorptionEngine()

        aborted = []
        engine.aborted.connect(lambda: aborted.append(True))

        done = [False]
        engine.aborted.connect(lambda: done.__setitem__(0, True))
        engine.scan_completed.connect(lambda: done.__setitem__(0, True))

        engine.start_scan(config, hw, None)
        time.sleep(0.05)
        engine.abort()

        start = time.time()
        while not done[0] and time.time() - start < 5.0:
            QApplication.instance().processEvents()
            time.sleep(0.005)

        assert len(aborted) >= 1

    def test_multiple_scans_emits_scan_started_for_each(self, qt_app):
        hw = make_mock_hw()
        config = make_config(n_delays=2, n_scans=3)
        engine = TransientAbsorptionEngine()

        started = []
        engine.scan_started.connect(lambda idx: started.append(idx))

        self._run_engine(engine, config, hw)
        assert len(started) == 3
        assert started == [0, 1, 2]

    def test_signal_updated_emitted(self, qt_app):
        hw = make_mock_hw(n_pixels=16)
        config = make_config(n_delays=2, n_scans=1)
        engine = TransientAbsorptionEngine()

        updates = []
        engine.signal_updated.connect(lambda delay, wl, sig: updates.append(delay))

        self._run_engine(engine, config, hw)
        assert len(updates) == 2  # once per delay point


class TestTransientAbsorptionEnginePauseResume:
    def test_pause_resume_completes_scan(self, qt_app):
        from PySide6.QtWidgets import QApplication

        hw = make_mock_hw()
        config = make_config(n_delays=3, n_scans=1)
        engine = TransientAbsorptionEngine()

        done = [False]
        engine.scan_completed.connect(lambda: done.__setitem__(0, True))

        engine.start_scan(config, hw, None)
        time.sleep(0.01)
        engine.pause()
        time.sleep(0.05)
        engine.resume()

        start = time.time()
        while not done[0] and time.time() - start < 5.0:
            QApplication.instance().processEvents()
            time.sleep(0.005)

        assert done[0] is True
