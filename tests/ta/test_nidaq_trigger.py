"""Tests for NIDAQChopper500Hz trigger generator."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, call, patch

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
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_nidaqmx(monkeypatch):
    """Inject a mock nidaqmx module so no hardware is needed."""
    mod = MagicMock()
    task = MagicMock()
    mod.Task.return_value.__enter__ = lambda s: task
    mod.Task.return_value.__exit__ = MagicMock(return_value=False)
    mod.Task.return_value = task
    monkeypatch.setitem(sys.modules, "nidaqmx", mod)
    monkeypatch.setitem(sys.modules, "nidaqmx.constants", mod.constants)
    return mod, task


class TestNIDAQChopper500HzTask:
    def test_start_creates_task(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        mod.Task.assert_called_once()

    def test_start_adds_co_pulse_chan_ticks(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz(device="Dev1", counter="ctr1")
        t.start()
        task.co_channels.add_co_pulse_chan_ticks.assert_called_once()
        args, kwargs = task.co_channels.add_co_pulse_chan_ticks.call_args
        # First positional arg is the counter channel
        assert args[0] == "Dev1/ctr1"

    def test_start_uses_pfi0_as_clock(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz(clock_source="/Dev1/PFI0")
        t.start()
        _, kwargs = task.co_channels.add_co_pulse_chan_ticks.call_args
        assert kwargs["source_terminal"] == "/Dev1/PFI0"

    def test_start_divides_by_two(self, mock_nidaqmx):
        """low_ticks=1 high_ticks=1 divides clock by 2."""
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        _, kwargs = task.co_channels.add_co_pulse_chan_ticks.call_args
        assert kwargs["low_ticks"] == 1
        assert kwargs["high_ticks"] == 1

    def test_start_sets_retriggerable(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        assert task.triggers.start_trigger.retriggerable is True

    def test_start_syncs_on_pfi12_rising(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz(sync_source="/Dev1/PFI12")
        t.start()
        task.triggers.start_trigger.cfg_dig_edge_start_trig.assert_called_once()
        _, kwargs = task.triggers.start_trigger.cfg_dig_edge_start_trig.call_args
        assert kwargs["trigger_source"] == "/Dev1/PFI12"
        assert kwargs["trigger_edge"] == mod.constants.Edge.RISING

    def test_stop_calls_task_stop_and_close(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        t.stop()
        task.stop.assert_called_once()
        task.close.assert_called_once()

    def test_stop_clears_task_reference(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        t.start()
        t.stop()
        assert t._task is None

    def test_context_manager_starts_and_stops(self, mock_nidaqmx):
        mod, task = mock_nidaqmx
        t = NIDAQChopper500Hz()
        with t:
            task.start.assert_called_once()
        task.stop.assert_called_once()
