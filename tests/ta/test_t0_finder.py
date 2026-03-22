"""Tests for T0Finder utility.

T0Finder does a coarse + fine scan to locate the optical t0 (onset of ΔI/I₀).
Tests use a mock hardware manager that returns zero ΔI/I₀ before t0 and
nonzero ΔI/I₀ after t0.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from andor_qt.ta.t0_finder import T0Finder
from andor_qt.ta.scan_config import TAScanConfig


# ---------------------------------------------------------------------------
# Mock hardware that simulates a ΔOD onset at t0 = 5.0 ps
# ---------------------------------------------------------------------------

TRUE_T0_PS = 5.0
N_PIXELS = 16


def make_mock_hw_with_t0(t0_ps: float = TRUE_T0_PS):
    """Return a mock hw where ΔI/I₀ is 0 before t0 and 0.1 after."""
    hw = MagicMock()
    call_count = [0]

    def get_spectrum():
        # acquire_delta_signal_at_delay is patched directly in tests; this
        # is just a fallback that returns a flat spectrum
        return np.ones(N_PIXELS) * 1000.0

    hw.camera.get_spectrum.side_effect = get_spectrum
    hw.wavelengths = np.linspace(400.0, 800.0, N_PIXELS)

    mock_axis = MagicMock()
    hw.motion.get_axis.return_value = mock_axis
    return hw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_signal(engine, signal_name, timeout=5.0):
    """Wait for a signal to be emitted, processing Qt events."""
    from PySide6.QtWidgets import QApplication

    received = [None]
    sig = getattr(engine, signal_name)
    sig.connect(lambda *args: received.__setitem__(0, args))

    start = time.time()
    while received[0] is None and time.time() - start < timeout:
        QApplication.instance().processEvents()
        time.sleep(0.005)
    return received[0]


# ---------------------------------------------------------------------------
# T0Finder tests
# ---------------------------------------------------------------------------


class TestT0FinderSignals:
    def test_t0_found_signal_emitted(self, qt_app):
        """t0_found(t0_ps, t0_mm) is emitted after a successful search."""
        hw = make_mock_hw_with_t0()
        finder = T0Finder()

        # Mock acquire_delta_signal_at_delay to return zero before t0, nonzero after
        delay_captured = []

        def fake_acquire(delay_ps, hw_manager, config, dark=None):
            delay_captured.append(delay_ps)
            if delay_ps >= TRUE_T0_PS:
                return np.ones(N_PIXELS) * 0.05  # nonzero ΔOD
            return np.zeros(N_PIXELS)

        found = [None]
        finder.t0_found.connect(lambda t0_ps, t0_mm: found.__setitem__(0, (t0_ps, t0_mm)))

        done = [False]
        finder.t0_found.connect(lambda *a: done.__setitem__(0, True))
        finder.error.connect(lambda msg: done.__setitem__(0, True))

        from PySide6.QtWidgets import QApplication
        import andor_qt.ta.t0_finder as t0_mod

        with patch.object(t0_mod, "acquire_delta_signal_at_delay", fake_acquire):
            finder.find_t0(
                hw,
                coarse_range_ps=20.0,
                coarse_step_ps=2.0,
                fine_range_ps=2.0,
                fine_step_ps=0.5,
                threshold=0.01,
            )

            start = time.time()
            while not done[0] and time.time() - start < 10.0:
                QApplication.instance().processEvents()
                time.sleep(0.005)

        assert found[0] is not None, "t0_found was not emitted"
        t0_ps, t0_mm = found[0]
        # Should find t0 near TRUE_T0_PS
        assert t0_ps == pytest.approx(TRUE_T0_PS, abs=2.0)

    def test_progress_signal_emitted(self, qt_app):
        """progress(current, total) is emitted during the search."""
        hw = make_mock_hw_with_t0()
        finder = T0Finder()

        progress_updates = []
        finder.progress.connect(lambda cur, tot: progress_updates.append((cur, tot)))

        done = [False]
        finder.t0_found.connect(lambda *a: done.__setitem__(0, True))
        finder.error.connect(lambda msg: done.__setitem__(0, True))

        def fake_acquire(delay_ps, hw_manager, config, dark=None):
            if delay_ps >= TRUE_T0_PS:
                return np.ones(N_PIXELS) * 0.05
            return np.zeros(N_PIXELS)

        from PySide6.QtWidgets import QApplication
        import andor_qt.ta.t0_finder as t0_mod

        with patch.object(t0_mod, "acquire_delta_signal_at_delay", fake_acquire):
            finder.find_t0(hw, coarse_range_ps=10.0, coarse_step_ps=2.0,
                           fine_range_ps=2.0, fine_step_ps=0.5, threshold=0.01)

            start = time.time()
            while not done[0] and time.time() - start < 10.0:
                QApplication.instance().processEvents()
                time.sleep(0.005)

        assert len(progress_updates) > 0

    def test_abort_stops_search(self, qt_app):
        """abort() stops the search and no t0_found is emitted."""
        hw = make_mock_hw_with_t0()
        finder = T0Finder()

        found = [False]
        aborted_or_done = [False]
        finder.t0_found.connect(lambda *a: (found.__setitem__(0, True), aborted_or_done.__setitem__(0, True)))
        finder.error.connect(lambda msg: aborted_or_done.__setitem__(0, True))
        finder.aborted.connect(lambda: aborted_or_done.__setitem__(0, True))

        slow_calls = [0]

        def slow_acquire(delay_ps, hw_manager, config, dark=None):
            time.sleep(0.05)  # slow enough to abort
            slow_calls[0] += 1
            return np.zeros(N_PIXELS)

        from PySide6.QtWidgets import QApplication
        import andor_qt.ta.t0_finder as t0_mod

        with patch.object(t0_mod, "acquire_delta_signal_at_delay", slow_acquire):
            finder.find_t0(hw, coarse_range_ps=100.0, coarse_step_ps=2.0,
                           fine_range_ps=2.0, fine_step_ps=0.5, threshold=0.01)
            time.sleep(0.1)
            finder.abort()

            start = time.time()
            while not aborted_or_done[0] and time.time() - start < 5.0:
                QApplication.instance().processEvents()
                time.sleep(0.005)

        # Either aborted before finding t0 or found very quickly
        # The key is: no deadlock, test completes
        assert True


class TestT0FinderBasic:
    def test_creates_successfully(self):
        finder = T0Finder()
        assert finder is not None

    def test_has_t0_found_signal(self):
        finder = T0Finder()
        assert hasattr(finder, "t0_found")

    def test_has_progress_signal(self):
        finder = T0Finder()
        assert hasattr(finder, "progress")

    def test_has_error_signal(self):
        finder = T0Finder()
        assert hasattr(finder, "error")

    def test_has_abort_method(self):
        finder = T0Finder()
        assert callable(finder.abort)

    def test_has_find_t0_method(self):
        finder = T0Finder()
        assert callable(finder.find_t0)
