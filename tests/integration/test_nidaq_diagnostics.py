"""NI DAQ PCIe-6353 diagnostic tests.

Verifies counter output, phase tag patterns, retrigger support, and frequency
measurement. Requires the chopper, laser sync, and SDG to be running.

Run with::

    uv run pytest tests/integration/test_nidaq_diagnostics.py --hardware -v
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from .conftest import DI_CHANNEL, NIDAQ_DEVICE, PFI0, PFI12

pytestmark = pytest.mark.hardware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_phase_tags(n_samples: int = 1000) -> np.ndarray:
    """Read P0.0 tags clocked by PFI0."""
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge

    with nidaqmx.Task() as task:
        task.di_channels.add_di_chan(DI_CHANNEL)
        task.timing.cfg_samp_clk_timing(
            rate=1000.0,
            source=PFI0,
            active_edge=Edge.RISING,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=n_samples,
        )
        task.start()
        data = task.read(number_of_samples_per_channel=n_samples, timeout=5.0)
        task.stop()
    return np.array(data, dtype=np.int8)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPFI0Frequency:
    """Verify the 1 kHz laser sync is present on PFI0."""

    def test_pfi0_is_approximately_1khz(self):
        import nidaqmx
        from nidaqmx.constants import Edge

        with nidaqmx.Task() as task:
            ch = task.ci_channels.add_ci_freq_chan(
                f"{NIDAQ_DEVICE}/ctr0",
                min_val=100.0,
                max_val=10000.0,
                edge=Edge.RISING,
            )
            ch.ci_freq_term = PFI0
            task.start()
            readings = [task.read(timeout=2.0) for _ in range(5)]
            task.stop()

        mean_freq = np.mean(readings)
        assert 900 < mean_freq < 1100, f"PFI0 frequency {mean_freq:.1f} Hz, expected ~1 kHz"


class TestPhaseTagPattern:
    """Verify P0.0 tags show the expected chopper modulation pattern."""

    def test_tags_have_both_on_and_off(self):
        tags = _read_phase_tags(1000)
        n_ones = int(tags.sum())
        n_zeros = len(tags) - n_ones
        assert n_ones > 0, "No ON tags — is the chopper running?"
        assert n_zeros > 0, "No OFF tags — is the chopper running?"

    def test_duty_cycle_near_50_percent(self):
        tags = _read_phase_tags(1000)
        duty = tags.sum() / len(tags) * 100
        assert 35 < duty < 65, f"Duty cycle {duty:.1f}%, expected ~50%"

    def test_run_length_consistent_with_250hz_chopper(self):
        """250 Hz chopper at 1 kHz sampling → runs of ~2 consecutive tags."""
        tags = _read_phase_tags(1000)
        changes = np.diff(tags)
        transitions = np.where(changes != 0)[0]
        assert len(transitions) > 10, "Too few transitions"
        run_lengths = np.diff(transitions)
        mean_run = run_lengths.mean()
        assert 1.5 < mean_run < 2.5, (
            f"Mean run length {mean_run:.1f}, expected ~2 for 250 Hz chopper"
        )


class TestRetriggerSupport:
    """Verify PCIe-6353 supports retriggerable counter output."""

    def test_retriggerable_counter_starts(self):
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, Edge, Level

        with nidaqmx.Task() as task:
            task.co_channels.add_co_pulse_chan_ticks(
                f"{NIDAQ_DEVICE}/ctr0",
                source_terminal=f"/{NIDAQ_DEVICE}/20MHzTimebase",
                low_ticks=36000,
                high_ticks=4000,
                idle_state=Level.LOW,
            )
            task.timing.cfg_implicit_timing(
                sample_mode=AcquisitionType.CONTINUOUS,
            )
            task.triggers.start_trigger.cfg_dig_edge_start_trig(
                trigger_source=PFI0,
                trigger_edge=Edge.RISING,
            )
            task.triggers.start_trigger.retriggerable = True
            task.start()
            time.sleep(1)
            task.stop()
        # If we get here without exception, retrigger is supported.


class TestPhaseLockStability:
    """500 Hz retriggered counter + tag reads — low discard rate."""

    def test_discard_rate_below_10_percent(self):
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, Edge, Level

        _TIMEBASE_HZ = 20_000_000
        period_ticks = _TIMEBASE_HZ // 500
        high_ticks = int(200e-6 * _TIMEBASE_HZ)
        low_ticks = period_ticks - high_ticks

        with nidaqmx.Task() as ctr_task:
            ctr_task.co_channels.add_co_pulse_chan_ticks(
                f"{NIDAQ_DEVICE}/ctr1",
                source_terminal=f"/{NIDAQ_DEVICE}/20MHzTimebase",
                low_ticks=low_ticks,
                high_ticks=high_ticks,
                idle_state=Level.LOW,
            )
            ctr_task.timing.cfg_implicit_timing(
                sample_mode=AcquisitionType.CONTINUOUS,
            )
            ctr_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                trigger_source=PFI12,
                trigger_edge=Edge.RISING,
            )
            ctr_task.triggers.start_trigger.retriggerable = True
            ctr_task.start()

            discard_counts = []
            for cycle in range(5):
                with nidaqmx.Task() as di_task:
                    di_task.di_channels.add_di_chan(DI_CHANNEL)
                    di_task.timing.cfg_samp_clk_timing(
                        rate=1000.0,
                        source=PFI0,
                        active_edge=Edge.RISING,
                        sample_mode=AcquisitionType.FINITE,
                        samps_per_chan=100,
                    )
                    di_task.start()
                    data = di_task.read(
                        number_of_samples_per_channel=100, timeout=2.0,
                    )
                    di_task.stop()

                tags = np.array(data, dtype=np.int8)
                best_disc = len(tags)
                for offset in (0, 1):
                    t = tags[offset:]
                    n_pairs = len(t) // 2
                    pairs = t[: n_pairs * 2].reshape(n_pairs, 2)
                    disc = int((pairs[:, 0] != pairs[:, 1]).sum())
                    if disc < best_disc:
                        best_disc = disc
                discard_counts.append(best_disc)

            ctr_task.stop()

        avg_discard = np.mean(discard_counts)
        assert avg_discard < 5, (
            f"Average discard rate {avg_discard:.1f}/cycle — counter not phase-locked"
        )


class TestCounterDivideBy4:
    """Toggle-mode divide-by-4 (fallback) runs without error."""

    def test_divide_by_4_runs(self):
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, Edge, Level

        with nidaqmx.Task() as task:
            task.co_channels.add_co_pulse_chan_ticks(
                f"{NIDAQ_DEVICE}/ctr1",
                source_terminal=PFI0,
                low_ticks=2,
                high_ticks=2,
                idle_state=Level.LOW,
            )
            task.timing.cfg_implicit_timing(
                sample_mode=AcquisitionType.CONTINUOUS,
            )
            task.triggers.start_trigger.cfg_dig_edge_start_trig(
                trigger_source=PFI0,
                trigger_edge=Edge.RISING,
            )
            task.start()
            time.sleep(2)
            task.stop()


class TestShotToShotDAQSignals:
    """Verify DAQ signals are suitable for shot_to_shot mode."""

    def test_pfi0_is_1khz_by_edge_count(self):
        """Measure PFI0 by counting edges over 1 second."""
        import nidaqmx
        from nidaqmx.constants import Edge

        with nidaqmx.Task() as task:
            ch = task.ci_channels.add_ci_count_edges_chan(f"{NIDAQ_DEVICE}/ctr0")
            ch.ci_count_edges_term = PFI0
            ch.ci_count_edges_active_edge = Edge.RISING
            task.start()
            t0 = time.perf_counter()
            time.sleep(1.0)
            count = task.read()
            elapsed = time.perf_counter() - t0
            task.stop()

        freq = count / elapsed
        assert 990 < freq < 1010, f"PFI0 = {freq:.1f} Hz, expected ~1000"

    def test_tag_pattern_suitable_for_shot_to_shot(self):
        """Each laser shot gets 1 tag; ON+OFF counts should be balanced."""
        tags = _read_phase_tags(200)
        n_on = int((tags == 1).sum())
        n_off = int((tags == 0).sum())
        assert n_on > 0 and n_off > 0, "Missing ON or OFF tags"
        duty = n_on / len(tags) * 100
        assert 35 < duty < 65, f"Duty cycle {duty:.1f}%, expected ~50%"
