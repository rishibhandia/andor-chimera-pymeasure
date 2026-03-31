# NI DAQ PCIe-6353 Counter Capabilities

**Extracted:** 2026-03-30
**Context:** Generating phase-locked camera triggers with NI DAQ counters

## Problem
Generating a 500 Hz camera trigger from a 1 kHz laser sync that stays phase-locked to a 250 Hz chopper. Multiple approaches were tested with varying success.

## Findings

### What works:
- **Retriggerable counters** — `task.triggers.start_trigger.retriggerable = True` IS supported on PCIe-6353 (confirmed by diagnostic test)
- **Counter edge detection** — `add_ci_count_edges_chan` blocks at hardware level until an edge arrives (microsecond precision)
- **Toggle mode divide-by-4** — `add_co_pulse_chan_ticks(low_ticks=2, high_ticks=2)` with external clock gives clean ÷4
- **Frequency measurement** — `add_ci_freq_chan` accurately measures PFI0 frequency

### What does NOT work:
- **Pulse mode (Toggle.PULSE)** — not available in nidaqmx 1.4.1. Cannot do divide-by-2 with tick counting
- **Retrigger at wrong rate** — retriggering a 500 Hz (2 ms period) counter at 1 kHz (every 1 ms) prevents the counter from completing a full cycle. Must retrigger at the output rate or slower
- **Software-polled phase sync** — reading DI samples in a Python loop has millisecond-level jitter, insufficient for sub-frame alignment

### NI DAQ resource conflicts:
- CTR0 OUT is hardwired to PFI12 — cannot use CTR0 if PFI12 is an input
- A DI task on port0/line0 conflicts with another task using the same line (even after the first task closes)
- PFI13 = CTR1 OUT = P2.5 — cannot read PFI13 as DI while CTR1 is active

## When to Use
When configuring NI DAQ counter tasks for trigger generation, frequency division, or phase detection on the PCIe-6353.
