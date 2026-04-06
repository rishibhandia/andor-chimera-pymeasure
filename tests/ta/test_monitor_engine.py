"""Tests for TAMonitorEngine / _MonitorWorker.

Verifies the three acquisition modes:
1. _run_continuous  -- continuous chopper/boxcar acquisition loop
2. _run_static      -- two-phase static ON/OFF with user prompt between
3. _run_single_phase -- single phase (pump-only or ref-only)

Uses TAMonitorEngine (which wraps _MonitorWorker in a QThread) and
captures signals with a polling loop + QApplication.processEvents().
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from andor_qt.ta.monitor_engine import TAMonitorEngine
from andor_qt.ta.scan_config import TAScanConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

N_PIXELS = 64
WAVELENGTHS = np.linspace(400.0, 800.0, N_PIXELS)


def _make_config(
    mode: str = "boxcar",
    n_averages: int = 2,
    shots_per_frame: int = 2,
) -> TAScanConfig:
    """Create a minimal TAScanConfig for testing."""
    return TAScanConfig(
        delay_list=[0.0],
        n_averages=n_averages,
        acquisition_mode=mode,
        scan_direction="forward",
        sample_name="test",
        shots_per_frame=shots_per_frame,
    )


def _make_hw(
    spectrum_value: float = 1000.0,
    n_pixels: int = N_PIXELS,
) -> MagicMock:
    """Create a mock HardwareManager that satisfies the monitor worker.

    The mock provides:
    - camera.get_spectrum() returning a flat spectrum
    - camera.start_run_till_abort / get_buffered_frames / abort_acquisition
    - motion_manager.get_axis("delay") returning a mock axis
    - get_wavelengths(hbin=...) returning calibrated wavelengths
    """
    hw = MagicMock()
    hw.camera.get_spectrum.return_value = np.ones(n_pixels) * spectrum_value
    hw.camera.start_run_till_abort.return_value = None
    hw.camera.get_buffered_frames.return_value = (
        np.ones((200, n_pixels)) * spectrum_value,
        200,
    )
    hw.camera.abort_acquisition.return_value = None
    hw.camera.apply_camera_settings.return_value = None

    mock_axis = MagicMock()
    mock_axis.position = 0.0
    mock_axis.position_ps = 0.0
    mock_axis.position_mm = 0.0
    mock_axis.t0_offset_mm = 0.0
    hw.motion_manager.get_axis.return_value = mock_axis

    hw.get_wavelengths.return_value = np.linspace(400.0, 800.0, n_pixels)

    return hw


def _wait_for_qt(condition_fn, timeout: float = 10.0) -> bool:
    """Poll Qt event loop until condition_fn returns True or timeout."""
    app = QApplication.instance()
    start = time.time()
    while time.time() - start < timeout:
        if app:
            app.processEvents()
        if condition_fn():
            return True
        time.sleep(0.02)
    return False


def _stop_and_wait(engine: TAMonitorEngine, timeout: float = 5.0) -> None:
    """Stop engine and wait for thread to finish."""
    engine.stop()
    app = QApplication.instance()
    start = time.time()
    while engine.is_running and time.time() - start < timeout:
        if app:
            app.processEvents()
        time.sleep(0.02)


# ===========================================================================
# _run_continuous (boxcar mode)
# ===========================================================================


class TestRunContinuous:
    """Tests for the continuous acquisition loop (_run_continuous)."""

    def test_cycle_completed_emits_wavelengths_delta_and_avg(self, qt_app):
        """cycle_completed signal emits (wavelengths, delta, avg_delta)."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=2)
        engine = TAMonitorEngine()

        results = []
        engine.cycle_completed.connect(
            lambda wl, delta, avg: results.append((
                np.array(wl), np.array(delta), np.array(avg),
            ))
        )

        engine.start_monitor(config, hw)

        ok = _wait_for_qt(lambda: len(results) >= 1)
        _stop_and_wait(engine)

        assert ok, "Timed out waiting for cycle_completed"
        wl, delta, avg = results[0]
        assert wl.shape == (N_PIXELS,)
        assert delta.shape == (N_PIXELS,)
        assert avg.shape == (N_PIXELS,)

    def test_running_average_is_mean_of_deltas(self, qt_app):
        """After N cycles, avg should equal np.mean(all deltas, axis=0)."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        engine = TAMonitorEngine()

        results = []
        engine.cycle_completed.connect(
            lambda wl, delta, avg: results.append((
                np.array(delta, copy=True), np.array(avg, copy=True),
            ))
        )

        engine.start_monitor(config, hw)
        ok = _wait_for_qt(lambda: len(results) >= 3)
        _stop_and_wait(engine)

        assert ok, "Timed out waiting for 3 cycles"
        # Verify the running average at the last captured cycle
        n = len(results)
        all_deltas = np.array([r[0] for r in results[:n]])
        expected_avg = np.mean(all_deltas, axis=0)
        _, actual_avg = results[n - 1]
        np.testing.assert_allclose(actual_avg, expected_avg, atol=1e-10)

    def test_multiple_cycles_accumulate_in_avg_stack(self, qt_app):
        """Each cycle adds to the running average stack."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        engine = TAMonitorEngine()

        avgs = []
        engine.cycle_completed.connect(
            lambda wl, delta, avg: avgs.append(np.array(avg, copy=True))
        )

        engine.start_monitor(config, hw)
        ok = _wait_for_qt(lambda: len(avgs) >= 3)
        _stop_and_wait(engine)

        assert ok, "Timed out waiting for 3 cycles"
        # All averages should have the right shape
        for a in avgs:
            assert a.shape == (N_PIXELS,)

    def test_runtime_error_retries_without_crash(self, qt_app):
        """RuntimeError in acquire_one_cycle is caught and the loop retries."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        engine = TAMonitorEngine()

        call_count = [0]
        results = []
        errors = []

        engine.cycle_completed.connect(
            lambda wl, delta, avg: results.append(1)
        )
        engine.error.connect(lambda msg: errors.append(msg))

        # Patch AcquisitionSession.acquire_one_cycle to raise on first call
        orig_acquire = None

        def _patched_acquire(self_session, *args, **kwargs):
            nonlocal orig_acquire
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RuntimeError("simulated zero frames")
            return orig_acquire(self_session, *args, **kwargs)

        from andor_qt.ta.acquisition import AcquisitionSession
        orig_acquire = AcquisitionSession.acquire_one_cycle

        with patch.object(AcquisitionSession, "acquire_one_cycle", _patched_acquire):
            engine.start_monitor(config, hw)
            ok = _wait_for_qt(lambda: len(results) >= 1, timeout=10.0)
            _stop_and_wait(engine)

        assert ok, "Engine never recovered after RuntimeError retries"
        # No error signal should have been emitted (RuntimeError is handled)
        assert len(errors) == 0

    def test_cleanup_calls_trigger_gen_stop(self, qt_app):
        """trigger_gen.stop() is called when monitor stops."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        trigger_gen = MagicMock()
        engine = TAMonitorEngine()

        stopped = [False]
        engine.stopped.connect(lambda: stopped.__setitem__(0, True))

        engine.start_monitor(config, hw, trigger_gen=trigger_gen)
        ok = _wait_for_qt(lambda: engine.is_running)
        assert ok, "Engine did not start"

        _stop_and_wait(engine)
        _wait_for_qt(lambda: stopped[0])

        trigger_gen.start.assert_called_once()
        trigger_gen.stop.assert_called_once()

    def test_cleanup_calls_phase_reader_stop(self, qt_app):
        """phase_reader.stop() is called when monitor stops (non-chopper mode)."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        phase_reader = MagicMock()
        engine = TAMonitorEngine()

        stopped = [False]
        engine.stopped.connect(lambda: stopped.__setitem__(0, True))

        engine.start_monitor(config, hw, phase_reader=phase_reader)
        ok = _wait_for_qt(lambda: engine.is_running)
        assert ok, "Engine did not start"

        _stop_and_wait(engine)
        _wait_for_qt(lambda: stopped[0])

        phase_reader.start.assert_called_once()
        phase_reader.stop.assert_called_once()

    def test_stopped_signal_emitted_on_exit(self, qt_app):
        """stopped signal is emitted when the monitor loop finishes."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        engine = TAMonitorEngine()

        stopped = [False]
        engine.stopped.connect(lambda: stopped.__setitem__(0, True))

        engine.start_monitor(config, hw)
        _wait_for_qt(lambda: engine.is_running)
        _stop_and_wait(engine)

        ok = _wait_for_qt(lambda: stopped[0])
        assert ok, "stopped signal was not emitted"


# ===========================================================================
# _run_static
# ===========================================================================


class TestRunStatic:
    """Tests for the two-phase static ON/OFF mode (_run_static)."""

    def _make_static_hw(self, pump_value=1200.0, ref_value=1000.0):
        """Create mock hw that returns different spectra for pump/ref phases.

        For static mode, acquire_static_at_delay uses acquire_long_average
        which calls camera.start_run_till_abort() and get_buffered_frames().
        The worker calls _acquire_static twice. We use side_effect to return
        different frame values for each call.
        """
        hw = _make_hw(spectrum_value=pump_value)

        # First call returns pump frames, second returns ref frames
        call_idx = [0]

        def _buffered_frames():
            call_idx[0] += 1
            if call_idx[0] <= 1:
                frames = np.ones((50, N_PIXELS)) * pump_value
            else:
                frames = np.ones((50, N_PIXELS)) * ref_value
            return frames, len(frames)

        hw.camera.get_buffered_frames.side_effect = lambda: _buffered_frames()
        return hw

    def test_single_phase_completed_emitted_for_pump(self, qt_app):
        """single_phase_completed should NOT be emitted in full static_onoff mode.

        (single_phase_completed is only for _run_single_phase, not _run_static.)
        Instead, static_completed should be emitted after both phases.
        """
        hw = self._make_static_hw()
        config = _make_config("static_onoff", n_averages=5)
        engine = TAMonitorEngine()

        raw_pairs = []
        engine.raw_pair_updated.connect(
            lambda p, r, m, d, f: raw_pairs.append(1)
        )

        prompts = []
        engine.user_prompt.connect(lambda msg: prompts.append(msg))

        static_results = []
        engine.static_completed.connect(
            lambda wl, pump, ref, dod: static_results.append((
                np.array(wl), np.array(pump), np.array(ref), np.array(dod),
            ))
        )

        # Auto-confirm the user prompt after it appears
        def _auto_confirm():
            if len(prompts) >= 1:
                engine.user_confirmed()
                return True
            return False

        engine.start_monitor(config, hw)
        _wait_for_qt(_auto_confirm, timeout=5.0)
        ok = _wait_for_qt(lambda: len(static_results) >= 1, timeout=10.0)
        _stop_and_wait(engine)

        assert ok, "static_completed was not emitted"

    def test_user_prompt_emitted_between_phases(self, qt_app):
        """user_prompt signal is emitted after pump phase, before ref phase."""
        hw = self._make_static_hw()
        config = _make_config("static_onoff", n_averages=5)
        engine = TAMonitorEngine()

        prompts = []
        engine.user_prompt.connect(lambda msg: prompts.append(msg))

        static_done = [False]
        engine.static_completed.connect(lambda *_: static_done.__setitem__(0, True))

        # Auto-confirm after prompt
        def _auto_confirm():
            if len(prompts) >= 1:
                engine.user_confirmed()
                return True
            return False

        engine.start_monitor(config, hw)
        _wait_for_qt(_auto_confirm, timeout=5.0)
        _wait_for_qt(lambda: static_done[0], timeout=10.0)
        _stop_and_wait(engine)

        assert len(prompts) >= 1
        assert "pump" in prompts[0].lower() or "block" in prompts[0].lower()

    def test_static_completed_emits_wavelengths_pump_ref_delta_od(self, qt_app):
        """static_completed emits (wavelengths, pump_avg, ref_avg, delta_od)."""
        pump_val = 1200.0
        ref_val = 1000.0
        hw = self._make_static_hw(pump_value=pump_val, ref_value=ref_val)
        config = _make_config("static_onoff", n_averages=5)
        engine = TAMonitorEngine()

        prompts = []
        engine.user_prompt.connect(lambda msg: prompts.append(msg))

        static_results = []
        engine.static_completed.connect(
            lambda wl, pump, ref, dod: static_results.append((
                np.array(wl), np.array(pump), np.array(ref), np.array(dod),
            ))
        )

        def _auto_confirm():
            if len(prompts) >= 1:
                engine.user_confirmed()
                return True
            return False

        engine.start_monitor(config, hw)
        _wait_for_qt(_auto_confirm, timeout=5.0)
        ok = _wait_for_qt(lambda: len(static_results) >= 1, timeout=10.0)
        _stop_and_wait(engine)

        assert ok, "static_completed was not emitted"
        wl, pump_avg, ref_avg, delta_od = static_results[0]
        assert wl.shape == (N_PIXELS,)
        assert pump_avg.shape == (N_PIXELS,)
        assert ref_avg.shape == (N_PIXELS,)
        assert delta_od.shape == (N_PIXELS,)

    def test_delta_od_is_negative_log10_pump_over_ref(self, qt_app):
        """delta_od = -log10(pump / ref)."""
        pump_val = 1200.0
        ref_val = 1000.0
        hw = self._make_static_hw(pump_value=pump_val, ref_value=ref_val)
        config = _make_config("static_onoff", n_averages=5)
        engine = TAMonitorEngine()

        prompts = []
        engine.user_prompt.connect(lambda msg: prompts.append(msg))

        static_results = []
        engine.static_completed.connect(
            lambda wl, pump, ref, dod: static_results.append((
                np.array(pump, copy=True),
                np.array(ref, copy=True),
                np.array(dod, copy=True),
            ))
        )

        def _auto_confirm():
            if len(prompts) >= 1:
                engine.user_confirmed()
                return True
            return False

        engine.start_monitor(config, hw)
        _wait_for_qt(_auto_confirm, timeout=5.0)
        ok = _wait_for_qt(lambda: len(static_results) >= 1, timeout=10.0)
        _stop_and_wait(engine)

        assert ok, "static_completed was not emitted"
        pump_avg, ref_avg, delta_od = static_results[0]
        expected = -np.log10(pump_avg / ref_avg)
        np.testing.assert_allclose(delta_od, expected, atol=1e-10)

    def test_abort_during_prompt_stops_cleanly(self, qt_app):
        """Aborting while waiting for user response stops the engine."""
        hw = self._make_static_hw()
        config = _make_config("static_onoff", n_averages=5)
        engine = TAMonitorEngine()

        prompts = []
        engine.user_prompt.connect(lambda msg: prompts.append(msg))

        stopped = [False]
        engine.stopped.connect(lambda: stopped.__setitem__(0, True))

        engine.start_monitor(config, hw)

        # Wait for prompt, then abort instead of confirming
        _wait_for_qt(lambda: len(prompts) >= 1, timeout=5.0)
        engine.stop()

        ok = _wait_for_qt(lambda: stopped[0], timeout=5.0)
        assert ok, "Engine did not stop after abort during prompt"


# ===========================================================================
# _run_single_phase
# ===========================================================================


class TestRunSinglePhase:
    """Tests for single-phase acquisition (_run_single_phase)."""

    def test_single_phase_pump_acquires_and_emits(self, qt_app):
        """Acquires n_averages frames and emits single_phase_completed for pump."""
        hw = _make_hw(spectrum_value=1500.0)
        config = _make_config("static_onoff", n_averages=10)
        engine = TAMonitorEngine()

        results = []
        engine.single_phase_completed.connect(
            lambda phase, wl, avg: results.append((
                phase, np.array(wl), np.array(avg),
            ))
        )

        engine.start_monitor(config, hw, static_phase="pump")

        ok = _wait_for_qt(lambda: len(results) >= 1, timeout=10.0)
        _stop_and_wait(engine)

        assert ok, "single_phase_completed was not emitted"
        phase, wl, avg = results[0]
        assert phase == "pump"
        assert wl.shape == (N_PIXELS,)
        assert avg.shape == (N_PIXELS,)

    def test_single_phase_ref_acquires_and_emits(self, qt_app):
        """Acquires n_averages frames and emits single_phase_completed for ref."""
        hw = _make_hw(spectrum_value=900.0)
        config = _make_config("static_onoff", n_averages=10)
        engine = TAMonitorEngine()

        results = []
        engine.single_phase_completed.connect(
            lambda phase, wl, avg: results.append((
                phase, np.array(wl), np.array(avg),
            ))
        )

        engine.start_monitor(config, hw, static_phase="ref")

        ok = _wait_for_qt(lambda: len(results) >= 1, timeout=10.0)
        _stop_and_wait(engine)

        assert ok, "single_phase_completed was not emitted"
        phase, wl, avg = results[0]
        assert phase == "ref"
        assert wl.shape == (N_PIXELS,)
        assert avg.shape == (N_PIXELS,)

    def test_single_phase_averages_frames(self, qt_app):
        """The averaged spectrum should reflect the input frame values."""
        spectrum_val = 2500.0
        hw = _make_hw(spectrum_value=spectrum_val)
        config = _make_config("static_onoff", n_averages=10)
        engine = TAMonitorEngine()

        results = []
        engine.single_phase_completed.connect(
            lambda phase, wl, avg: results.append(np.array(avg, copy=True))
        )

        engine.start_monitor(config, hw, static_phase="pump")

        ok = _wait_for_qt(lambda: len(results) >= 1, timeout=10.0)
        _stop_and_wait(engine)

        assert ok, "single_phase_completed was not emitted"
        avg = results[0]
        # Mean of flat frames at spectrum_val should be spectrum_val
        np.testing.assert_allclose(avg, spectrum_val, atol=1.0)

    def test_single_phase_emits_stopped(self, qt_app):
        """stopped signal is emitted after single phase completes."""
        hw = _make_hw()
        config = _make_config("static_onoff", n_averages=5)
        engine = TAMonitorEngine()

        stopped = [False]
        engine.stopped.connect(lambda: stopped.__setitem__(0, True))

        engine.start_monitor(config, hw, static_phase="pump")

        ok = _wait_for_qt(lambda: stopped[0], timeout=10.0)
        # Give thread time to fully finish
        _stop_and_wait(engine)

        assert ok, "stopped signal was not emitted"

    def test_single_phase_error_emits_error_signal(self, qt_app):
        """If acquisition fails, error signal is emitted."""
        hw = _make_hw()
        # Return zero frames so acquire_long_average raises RuntimeError
        hw.camera.get_buffered_frames.return_value = (np.array([]), 0)
        config = _make_config("static_onoff", n_averages=5)
        engine = TAMonitorEngine()

        errors = []
        engine.error.connect(lambda msg: errors.append(msg))

        stopped = [False]
        engine.stopped.connect(lambda: stopped.__setitem__(0, True))

        engine.start_monitor(config, hw, static_phase="pump")

        ok = _wait_for_qt(lambda: stopped[0], timeout=10.0)
        _stop_and_wait(engine)

        assert ok, "Engine did not stop after error"
        assert len(errors) >= 1, "error signal was not emitted"


# ===========================================================================
# Edge cases and status signals
# ===========================================================================


class TestMonitorEdgeCases:
    """Edge case and status signal tests."""

    def test_status_updated_emitted_during_continuous(self, qt_app):
        """status_updated signal is emitted during continuous mode."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        engine = TAMonitorEngine()

        statuses = []
        engine.status_updated.connect(lambda msg: statuses.append(msg))

        engine.start_monitor(config, hw)
        ok = _wait_for_qt(lambda: len(statuses) >= 1)
        _stop_and_wait(engine)

        assert ok, "status_updated was never emitted"
        assert len(statuses) >= 1

    def test_wavelengths_populated_from_hw(self, qt_app):
        """Wavelengths emitted by cycle_completed come from hw.get_wavelengths()."""
        hw = _make_hw()
        expected_wl = np.linspace(500.0, 900.0, N_PIXELS)
        hw.get_wavelengths.return_value = expected_wl
        config = _make_config("boxcar", n_averages=1)
        engine = TAMonitorEngine()

        results = []
        engine.cycle_completed.connect(
            lambda wl, delta, avg: results.append(np.array(wl, copy=True))
        )

        engine.start_monitor(config, hw)
        ok = _wait_for_qt(lambda: len(results) >= 1)
        _stop_and_wait(engine)

        assert ok, "cycle_completed not emitted"
        np.testing.assert_array_equal(results[0], expected_wl)

    def test_camera_settings_applied(self, qt_app):
        """Camera settings are applied before acquisition starts."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        settings = {"trigger_mode": "internal", "exposure_time": 0.01}
        engine = TAMonitorEngine()

        results = []
        engine.cycle_completed.connect(lambda *_: results.append(1))

        engine.start_monitor(config, hw, camera_settings=settings)
        ok = _wait_for_qt(lambda: len(results) >= 1)
        _stop_and_wait(engine)

        assert ok
        hw.camera.apply_camera_settings.assert_called_with(settings)

    def test_start_while_running_is_ignored(self, qt_app):
        """Calling start_monitor while already running does nothing."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        engine = TAMonitorEngine()

        engine.start_monitor(config, hw)
        _wait_for_qt(lambda: engine.is_running)

        # Second start should be silently ignored
        engine.start_monitor(config, hw)

        _stop_and_wait(engine)
        # No crash is the pass condition


# ===========================================================================
# Stage axis selection
# ===========================================================================


class TestMonitorStageAxisSelection:
    """Monitor engine must apply config.stage_axis before acquisition."""

    def test_monitor_calls_set_axis_hardware_index(self, qt_app):
        """Monitor calls motion_manager.set_axis_hardware_index('delay', stage_axis)."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        config.stage_axis = 3

        engine = TAMonitorEngine()
        cycles = []
        engine.cycle_completed.connect(lambda *args: cycles.append(1))

        engine.start_monitor(config, hw)
        _wait_for_qt(lambda: len(cycles) >= 1, timeout=10.0)
        _stop_and_wait(engine)

        hw.motion_manager.set_axis_hardware_index.assert_called_with("delay", 3)

    def test_monitor_applies_stage_axis_1(self, qt_app):
        """Monitor applies stage_axis=1."""
        hw = _make_hw()
        config = _make_config("boxcar", n_averages=1)
        config.stage_axis = 1

        engine = TAMonitorEngine()
        cycles = []
        engine.cycle_completed.connect(lambda *args: cycles.append(1))

        engine.start_monitor(config, hw)
        _wait_for_qt(lambda: len(cycles) >= 1, timeout=10.0)
        _stop_and_wait(engine)

        hw.motion_manager.set_axis_hardware_index.assert_called_with("delay", 1)
