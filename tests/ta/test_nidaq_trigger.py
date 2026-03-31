"""Tests for NIDAQChopper500Hz trigger generator."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from andor_qt.ta.nidaq_trigger import MockNIDAQChopper500Hz, NIDAQChopper500Hz


# ---------------------------------------------------------------------------
# MockNIDAQChopper500Hz
# ---------------------------------------------------------------------------

class TestMockNIDAQChopper500Hz:
    def test_not_running_on_create(self):
        m = MockNIDAQChopper500Hz()
        assert not m.is_running

    def test_start_sets_running(self):
        m = MockNIDAQChopper500Hz()
        m.start()
        assert m.is_running

    def test_stop_clears_running(self):
        m = MockNIDAQChopper500Hz()
        m.start()
        m.stop()
        assert not m.is_running

    def test_context_manager_running_inside(self):
        m = MockNIDAQChopper500Hz()
        with m:
            assert m.is_running

    def test_context_manager_stopped_after(self):
        m = MockNIDAQChopper500Hz()
        with m:
            pass
        assert not m.is_running

    def test_accepts_config_kwargs(self):
        m = MockNIDAQChopper500Hz(
            device="Dev2",
            clock_source="/Dev2/PFI0",
            sync_source="/Dev2/PFI12",
            counter="ctr0",
        )
        assert m is not None

    def test_stop_when_not_started_is_safe(self):
        m = MockNIDAQChopper500Hz()
        m.stop()  # should not raise


# ---------------------------------------------------------------------------
# NIDAQChopper500Hz — configuration
# ---------------------------------------------------------------------------

class TestNIDAQChopper500HzConfig:
    def test_default_device(self):
        t = NIDAQChopper500Hz()
        assert t._device == "Dev1"

    def test_default_counter(self):
        t = NIDAQChopper500Hz()
        assert t._counter == "ctr1"

    def test_default_clock_source(self):
        t = NIDAQChopper500Hz()
        assert t._clock_source == "/Dev1/PFI0"

    def test_default_sync_source(self):
        t = NIDAQChopper500Hz()
        assert t._sync_source == "/Dev1/PFI12"

    def test_custom_params_stored(self):
        t = NIDAQChopper500Hz(
            device="Dev2",
            clock_source="/Dev2/PFI1",
            sync_source="/Dev2/PFI5",
            counter="ctr0",
        )
        assert t._device == "Dev2"
        assert t._clock_source == "/Dev2/PFI1"
        assert t._sync_source == "/Dev2/PFI5"
        assert t._counter == "ctr0"

    def test_stop_before_start_is_safe(self):
        t = NIDAQChopper500Hz()
        t.stop()  # must not raise


# ---------------------------------------------------------------------------
# NIDAQChopper500Hz — ImportError without nidaqmx
# ---------------------------------------------------------------------------

class TestNIDAQChopper500HzImport:
    def test_raises_import_error_without_nidaqmx(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "nidaqmx", None)
        monkeypatch.setitem(sys.modules, "nidaqmx.constants", None)
        t = NIDAQChopper500Hz()
        with pytest.raises(ImportError, match="nidaqmx"):
            t.start()


# ---------------------------------------------------------------------------
# NIDAQChopper500Hz — task configuration (mocked nidaqmx)
#
# Current implementation uses a SINGLE counter task:
#   - 500 Hz from 20 MHz timebase, retriggered by sync_source (PFI12)
#   - Output on counter (default ctr1 → PFI13)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_nidaqmx(monkeypatch):
    """Inject a mock nidaqmx module with a single task object."""
    mod = MagicMock()
    task = MagicMock()
    mod.Task.return_value = task
    monkeypatch.setitem(sys.modules, "nidaqmx", mod)
    monkeypatch.setitem(sys.modules, "nidaqmx.constants", mod.constants)
    return mod, task


class TestNIDAQChopper500HzTask:
    def test_start_creates_one_task(self, mock_nidaqmx):
        """Single nidaqmx.Task() call for the retriggered 500 Hz counter."""
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        assert mod.Task.call_count == 1

    # ------------------------------------------------------------------
    # Counter configuration: 500 Hz from 20 MHz timebase
    # ------------------------------------------------------------------

    def test_uses_20mhz_timebase(self, mock_nidaqmx):
        """Source must be the 20 MHz internal timebase."""
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz(device="Dev1")
        t.start()
        _, kwargs = task.co_channels.add_co_pulse_chan_ticks.call_args
        assert kwargs["source_terminal"] == "/Dev1/20MHzTimebase"

    def test_counter_channel(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz(device="Dev1", counter="ctr1")
        t.start()
        args, _ = task.co_channels.add_co_pulse_chan_ticks.call_args
        assert args[0] == "Dev1/ctr1"

    def test_tick_calculation_gives_500hz(self, mock_nidaqmx):
        """period=40000, high=4000, low=36000 → 20 MHz / 40000 = 500 Hz."""
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        _, kwargs = task.co_channels.add_co_pulse_chan_ticks.call_args
        high = kwargs["high_ticks"]
        low = kwargs["low_ticks"]
        assert high + low == 40_000
        assert high == 4_000
        assert low == 36_000

    def test_ticks_above_hardware_minimum(self, mock_nidaqmx):
        """NI DAQ requires high_ticks >= 2 and low_ticks >= 2."""
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        _, kwargs = task.co_channels.add_co_pulse_chan_ticks.call_args
        assert kwargs["high_ticks"] >= 2
        assert kwargs["low_ticks"] >= 2

    def test_idle_state_is_low(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        _, kwargs = task.co_channels.add_co_pulse_chan_ticks.call_args
        assert kwargs["idle_state"] == mod.constants.Level.LOW

    # ------------------------------------------------------------------
    # Retrigger: sync_source (PFI12) rising edge
    # ------------------------------------------------------------------

    def test_retriggers_on_sync_source(self, mock_nidaqmx):
        """Counter must retrigger on sync_source (default PFI12)."""
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz(device="Dev1", sync_source="/Dev1/PFI12")
        t.start()
        _, kwargs = task.triggers.start_trigger.cfg_dig_edge_start_trig.call_args
        assert kwargs["trigger_source"] == "/Dev1/PFI12"
        assert kwargs["trigger_edge"] == mod.constants.Edge.RISING

    def test_is_retriggerable(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        assert task.triggers.start_trigger.retriggerable is True

    # ------------------------------------------------------------------
    # Stop / cleanup
    # ------------------------------------------------------------------

    def test_stop_closes_task(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        t.stop()
        task.stop.assert_called_once()
        task.close.assert_called_once()

    def test_stop_clears_task_references(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        t.stop()
        assert t._task is None
        assert t._divider_task is None

    def test_context_manager_starts_and_stops(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        with t:
            task.start.assert_called_once()
        task.stop.assert_called_once()
