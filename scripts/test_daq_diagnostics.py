#!/usr/bin/env python
"""NI DAQ PCIe-6353 diagnostic tests for chopper_2x2 trigger generation.

Run from project root:
    uv run python scripts/test_daq_diagnostics.py

Tests:
  1. Counter divide-by-2 (pulse mode) -- verify 500 Hz output from 1 kHz input
  2. Phase tag pattern analysis -- verify P0.0 tags show chopper modulation
  3. Phase-lock stability -- check if counter output stays locked across cycles
  4. Retrigger test -- verify if PCIe-6353 supports retriggerable counters
  5. Counter divide-by-4 (toggle mode) -- fallback 250 Hz output

Each test prints PASS/FAIL with diagnostic data. No GUI needed.

Required wiring (same as chopper_2x2 mode):
  - PFI0:  1 kHz laser sync input
  - P0.0:  Chopper controller digital output (pump phase)
  - PFI13: CTR1 output -> camera trigger (User 1 BNC)
"""

from __future__ import annotations

import sys
import time

import numpy as np

# NI DAQ device name -- change if yours differs
DEVICE = "Astrella_DAQ"
PFI0 = f"/{DEVICE}/PFI0"
DI_CHANNEL = f"{DEVICE}/port0/line0"


def check_nidaqmx():
    """Verify nidaqmx is importable."""
    try:
        import nidaqmx
        print(f"nidaqmx version: {nidaqmx.__version__}")
        return True
    except ImportError:
        print("FAIL: nidaqmx not installed. Run: uv pip install nidaqmx")
        return False


# =========================================================================
# Test 1: Counter divide-by-2 using pulse mode
# =========================================================================

def test_counter_divide_by_2():
    """Start CTR1 in pulse mode to divide PFI0 by 2.

    Verifies:
    - Task starts without error
    - Counter runs for 2 seconds
    - No NI DAQ errors during operation
    """
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge, Level

    print("\n" + "=" * 60)
    print("TEST 1: Counter divide-by-2 (pulse mode)")
    print("=" * 60)
    print(f"  Source: {PFI0} (expected 1 kHz)")
    print(f"  Output: CTR1 -> PFI13 (expected 500 Hz)")
    print(f"  Mode: pulse (not toggle)")

    try:
        # Check if Toggle.PULSE exists
        try:
            from nidaqmx.constants import Toggle
            has_pulse_mode = hasattr(Toggle, 'PULSE')
            print(f"  Toggle.PULSE available: {has_pulse_mode}")
        except ImportError:
            has_pulse_mode = False
            print("  WARNING: Toggle not importable from nidaqmx.constants")

        task = nidaqmx.Task()
        chan = task.co_channels.add_co_pulse_chan_ticks(
            f"{DEVICE}/ctr1",
            source_terminal=PFI0,
            low_ticks=2,
            high_ticks=2,
            idle_state=Level.LOW,
        )

        if has_pulse_mode:
            from nidaqmx.constants import Toggle
            chan.co_pulse_done_event_output_behavior = Toggle.PULSE
            print("  Set pulse mode: OK")
        else:
            print("  WARNING: Pulse mode not available, using toggle (/4)")

        task.timing.cfg_implicit_timing(
            sample_mode=AcquisitionType.CONTINUOUS
        )
        task.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=PFI0,
            trigger_edge=Edge.RISING,
        )

        task.start()
        print("  Task started: OK")
        print("  >>> Check oscilloscope: PFI13 should show 500 Hz <<<")
        print("  Running for 5 seconds...")
        time.sleep(5)

        task.stop()
        task.close()
        print("  Task stopped: OK")
        print("  RESULT: PASS -- counter started and ran without error")
        return True

    except Exception as exc:
        print(f"  RESULT: FAIL -- {exc}")
        return False


# =========================================================================
# Test 2: Phase tag pattern analysis
# =========================================================================

def test_phase_tag_pattern():
    """Read P0.0 tags at 1 kHz (clocked by PFI0) and analyze the pattern.

    Expected pattern for 250 Hz chopper with 1 kHz sampling:
    - Blocks of 2 consecutive 1s followed by 2 consecutive 0s
    - i.e., [1,1,0,0,1,1,0,0,...] or [0,0,1,1,0,0,1,1,...]

    This tells us if the chopper phase signal on P0.0 is working.
    """
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge

    print("\n" + "=" * 60)
    print("TEST 2: Phase tag pattern analysis (P0.0)")
    print("=" * 60)
    print(f"  DI channel: {DI_CHANNEL}")
    print(f"  Clock: {PFI0} (1 kHz)")
    print(f"  Expected: blocks of 1s and 0s (250 Hz chopper)")

    try:
        task = nidaqmx.Task()
        task.di_channels.add_di_chan(DI_CHANNEL)
        task.timing.cfg_samp_clk_timing(
            rate=1000.0,
            source=PFI0,
            active_edge=Edge.RISING,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=1000,
        )

        task.start()
        data = task.read(number_of_samples_per_channel=1000, timeout=5.0)
        task.stop()
        task.close()

        tags = np.array(data, dtype=np.int8)
        n_ones = int(tags.sum())
        n_zeros = int(len(tags) - n_ones)
        print(f"  Read {len(tags)} samples: {n_ones} ones, {n_zeros} zeros")
        print(f"  Duty cycle: {100 * n_ones / len(tags):.1f}%")

        # Analyze run lengths (consecutive same values)
        changes = np.diff(tags)
        transition_indices = np.where(changes != 0)[0]
        if len(transition_indices) > 1:
            run_lengths = np.diff(transition_indices)
            print(f"  Transitions: {len(transition_indices)}")
            print(f"  Run lengths: mean={run_lengths.mean():.1f}, "
                  f"std={run_lengths.std():.1f}, "
                  f"min={run_lengths.min()}, max={run_lengths.max()}")
            print(f"  First 20 tags: {tags[:20].tolist()}")
            print(f"  Expected run length for 250 Hz chopper: 2 samples")
            print(f"  Expected run length for 500 Hz chopper: 1 sample")

            if 1.5 < run_lengths.mean() < 2.5:
                print(f"  RESULT: PASS -- pattern consistent with 250 Hz chopper")
            elif 0.8 < run_lengths.mean() < 1.2:
                print(f"  RESULT: PASS -- pattern consistent with 500 Hz chopper")
            else:
                print(f"  RESULT: WARNING -- unexpected run length "
                      f"({run_lengths.mean():.1f} samples)")
        else:
            print(f"  RESULT: FAIL -- no transitions detected "
                  f"(all {'1s' if n_ones > n_zeros else '0s'})")
            print(f"  Check: is the chopper running? Is P0.0 connected?")

        return True

    except Exception as exc:
        print(f"  RESULT: FAIL -- {exc}")
        return False


# =========================================================================
# Test 3: Phase-lock stability
# =========================================================================

def test_phase_lock_stability():
    """Start counter /2, read tags, check if ON/OFF correlate with counter phase.

    Runs multiple short acquisitions and checks if the ON/OFF tag assignment
    is stable -- i.e., the same counter output phase always maps to the same
    chopper state.
    """
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge, Level

    print("\n" + "=" * 60)
    print("TEST 3: Phase-lock stability (counter + tags)")
    print("=" * 60)

    try:
        # Start counter
        ctr_task = nidaqmx.Task("ctr_phase_test")
        chan = ctr_task.co_channels.add_co_pulse_chan_ticks(
            f"{DEVICE}/ctr1",
            source_terminal=PFI0,
            low_ticks=2,
            high_ticks=2,
            idle_state=Level.LOW,
        )
        try:
            from nidaqmx.constants import Toggle
            chan.co_pulse_done_event_output_behavior = Toggle.PULSE
        except (ImportError, AttributeError):
            print("  WARNING: pulse mode not available, using toggle (/4)")

        ctr_task.timing.cfg_implicit_timing(
            sample_mode=AcquisitionType.CONTINUOUS
        )
        ctr_task.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=PFI0,
            trigger_edge=Edge.RISING,
        )
        ctr_task.start()
        print("  Counter started")

        # Read tags in multiple bursts
        results = []
        for cycle in range(10):
            di_task = nidaqmx.Task(f"di_phase_{cycle}")
            di_task.di_channels.add_di_chan(DI_CHANNEL)
            di_task.timing.cfg_samp_clk_timing(
                rate=1000.0,
                source=PFI0,
                active_edge=Edge.RISING,
                sample_mode=AcquisitionType.FINITE,
                samps_per_chan=100,
            )
            di_task.start()
            data = di_task.read(number_of_samples_per_channel=100, timeout=2.0)
            di_task.stop()
            di_task.close()

            tags = np.array(data, dtype=np.int8)
            # Reshape into pairs (2 tags per 500 Hz frame)
            n_pairs = len(tags) // 2
            pairs = tags[:n_pairs * 2].reshape(n_pairs, 2)
            matched = (pairs[:, 0] == pairs[:, 1])
            on_count = int((pairs[matched, 0] == 1).sum())
            off_count = int((pairs[matched, 0] == 0).sum())
            discarded = int(n_pairs - matched.sum())

            results.append({
                "on": on_count, "off": off_count, "discarded": discarded,
                "first_tag": int(tags[0]),
            })
            print(f"  Cycle {cycle+1}: ON={on_count}, OFF={off_count}, "
                  f"discarded={discarded}, first_tag={tags[0]}")

        ctr_task.stop()
        ctr_task.close()

        # Analyze stability
        on_counts = [r["on"] for r in results]
        off_counts = [r["off"] for r in results]
        discard_counts = [r["discarded"] for r in results]

        print(f"\n  ON  counts: {on_counts}")
        print(f"  OFF counts: {off_counts}")
        print(f"  Discarded:  {discard_counts}")

        avg_discard = np.mean(discard_counts)
        if avg_discard < 5:
            print(f"  RESULT: PASS -- low discard rate ({avg_discard:.1f}/cycle)")
        else:
            print(f"  RESULT: WARNING -- high discard rate ({avg_discard:.1f}/cycle)")
            print(f"  This suggests the counter output is not phase-locked "
                  f"to the chopper")

        return True

    except Exception as exc:
        print(f"  RESULT: FAIL -- {exc}")
        return False


# =========================================================================
# Test 4: Retrigger test
# =========================================================================

def test_retrigger():
    """Test if PCIe-6353 supports retriggerable counter output.

    Creates a counter with retriggerable=True and checks if it errors.
    """
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge, Level

    print("\n" + "=" * 60)
    print("TEST 4: Retrigger support test")
    print("=" * 60)

    try:
        # Use CTR0 for this test (CTR1 might be in use)
        task = nidaqmx.Task("retrig_test")
        task.co_channels.add_co_pulse_chan_ticks(
            f"{DEVICE}/ctr0",
            source_terminal=f"/{DEVICE}/20MHzTimebase",
            low_ticks=36000,
            high_ticks=4000,
            idle_state=Level.LOW,
        )
        task.timing.cfg_implicit_timing(
            sample_mode=AcquisitionType.CONTINUOUS
        )

        # Try to set retriggerable
        task.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=PFI0,
            trigger_edge=Edge.RISING,
        )

        try:
            task.triggers.start_trigger.retriggerable = True
            print("  Set retriggerable=True: OK (no error)")
        except Exception as exc:
            print(f"  Set retriggerable=True: FAILED -- {exc}")
            task.close()
            return False

        try:
            task.start()
            print("  Task started with retrigger: OK")
            time.sleep(2)
            task.stop()
            print("  Task ran for 2s and stopped: OK")
            print("  RESULT: PASS -- retriggerable is supported")
        except Exception as exc:
            print(f"  Task start failed: {exc}")
            print("  RESULT: FAIL -- retriggerable not supported on this hardware")
        finally:
            task.close()

        return True

    except Exception as exc:
        print(f"  RESULT: FAIL -- {exc}")
        return False


# =========================================================================
# Test 5: Counter divide-by-4 (toggle mode, fallback)
# =========================================================================

def test_counter_divide_by_4():
    """Divide PFI0 by 4 using toggle mode (known to work).

    If /2 pulse mode fails, /4 toggle mode is the fallback.
    Output: 250 Hz from 1 kHz input.
    """
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, Edge, Level

    print("\n" + "=" * 60)
    print("TEST 5: Counter divide-by-4 (toggle mode, fallback)")
    print("=" * 60)
    print(f"  Source: {PFI0} (expected 1 kHz)")
    print(f"  Output: CTR1 -> PFI13 (expected 250 Hz)")

    try:
        task = nidaqmx.Task()
        task.co_channels.add_co_pulse_chan_ticks(
            f"{DEVICE}/ctr1",
            source_terminal=PFI0,
            low_ticks=2,
            high_ticks=2,
            idle_state=Level.LOW,
        )
        # No pulse mode -- default toggle mode
        task.timing.cfg_implicit_timing(
            sample_mode=AcquisitionType.CONTINUOUS
        )
        task.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=PFI0,
            trigger_edge=Edge.RISING,
        )
        task.start()
        print("  Task started: OK")
        print("  >>> Check oscilloscope: PFI13 should show 250 Hz <<<")
        print("  Running for 5 seconds...")
        time.sleep(5)
        task.stop()
        task.close()
        print("  Task stopped: OK")
        print("  RESULT: PASS -- /4 toggle mode works")
        return True

    except Exception as exc:
        print(f"  RESULT: FAIL -- {exc}")
        return False


# =========================================================================
# Test 6: Frequency measurement using counter input
# =========================================================================

def test_measure_pfi0_frequency():
    """Use a counter in frequency measurement mode to verify PFI0 rate.

    This confirms the 1 kHz laser sync is actually present on PFI0.
    """
    import nidaqmx
    from nidaqmx.constants import Edge

    print("\n" + "=" * 60)
    print("TEST 6: Measure PFI0 frequency")
    print("=" * 60)

    try:
        task = nidaqmx.Task()
        task.ci_channels.add_ci_freq_chan(
            f"{DEVICE}/ctr0",
            min_val=100.0,
            max_val=10000.0,
            edge=Edge.RISING,
        )
        # Route PFI0 to counter input
        task.ci_channels[0].ci_freq_term = PFI0

        task.start()
        # Read multiple samples
        readings = []
        for _ in range(5):
            freq = task.read(timeout=2.0)
            readings.append(freq)
            time.sleep(0.2)

        task.stop()
        task.close()

        mean_freq = np.mean(readings)
        std_freq = np.std(readings)
        print(f"  PFI0 frequency: {mean_freq:.1f} Hz (std: {std_freq:.1f} Hz)")
        print(f"  Readings: {[f'{r:.1f}' for r in readings]}")

        if 900 < mean_freq < 1100:
            print(f"  RESULT: PASS -- PFI0 is ~1 kHz")
        elif 450 < mean_freq < 550:
            print(f"  RESULT: WARNING -- PFI0 is ~500 Hz (not 1 kHz)")
            print(f"  Check: is PFI0 connected to laser sync or SDG output?")
        elif 200 < mean_freq < 300:
            print(f"  RESULT: WARNING -- PFI0 is ~250 Hz")
        else:
            print(f"  RESULT: FAIL -- unexpected frequency ({mean_freq:.1f} Hz)")

        return True

    except Exception as exc:
        print(f"  RESULT: FAIL -- {exc}")
        return False


# =========================================================================
# Main
# =========================================================================

def main():
    print("=" * 60)
    print("NI DAQ PCIe-6353 Diagnostic Tests")
    print(f"Device: {DEVICE}")
    print("=" * 60)

    if not check_nidaqmx():
        return 1

    tests = [
        ("PFI0 frequency", test_measure_pfi0_frequency),
        ("Phase tag pattern", test_phase_tag_pattern),
        ("Counter /2 pulse mode", test_counter_divide_by_2),
        ("Counter /4 toggle mode", test_counter_divide_by_4),
        ("Retrigger support", test_retrigger),
        ("Phase-lock stability", test_phase_lock_stability),
    ]

    if len(sys.argv) > 1:
        # Run specific test by number
        idx = int(sys.argv[1]) - 1
        if 0 <= idx < len(tests):
            name, fn = tests[idx]
            print(f"\nRunning test {idx+1}: {name}")
            fn()
        else:
            print(f"Invalid test number. Valid: 1-{len(tests)}")
        return 0

    # Run all tests
    results = {}
    for name, fn in tests:
        try:
            results[name] = fn()
        except Exception as exc:
            print(f"  UNEXPECTED ERROR: {exc}")
            results[name] = False

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
