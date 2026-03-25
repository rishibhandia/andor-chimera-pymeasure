"""NI DAQ 500 Hz camera trigger generator for chopper_2x2 acquisition.

``NIDAQChopper500Hz`` uses NI DAQ Counter 1 to divide the 1 kHz laser sync
(PFI0) by 2, retriggered on every 250 Hz chopper pulse (PFI12).  The output
on CTR1OUT / PFI13 is a phase-locked 500 Hz pulse train:

  - Odd triggers  (1st, 3rd, …): start of pump-ON window  (2 laser shots)
  - Even triggers (2nd, 4th, …): start of pump-OFF window (2 laser shots)

Typical wiring
--------------
  Laser sync OUT (1 kHz TTL)     →  NI PFI0   (hardware divide-by-2 clock)
  Chopper sync OUT (250 Hz TTL)  →  NI PFI12  (phase re-sync pulse)
  NI PFI13 / CTR1OUT             →  BNC-2110 User 1  →  Camera Ext Trigger

The camera should be configured with ``fast_external`` trigger and 2 ms
exposure to integrate exactly 2 laser shots per frame.

Usage
-----
    trigger = NIDAQChopper500Hz(
        device="Dev1",
        clock_source="/Dev1/PFI0",
        sync_source="/Dev1/PFI12",
    )
    with trigger:
        # Camera now receives 500 Hz trigger on PFI13
        engine.run(config)

``MockNIDAQChopper500Hz`` provides the same interface without hardware,
suitable for unit tests and mock-mode operation.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class NIDAQChopper500Hz:
    """Generate a phase-locked 500 Hz camera trigger using NI DAQ Counter 1.

    Divides the 1 kHz laser sync (PFI0) by 2, retriggered on every rising
    edge of the 250 Hz chopper pulse (PFI12).  Output appears on CTR1OUT
    (PFI13, pin 40 on the PCIe-6353 68-pin connector).

    Args:
        device: NI DAQ device name (e.g. ``"Dev1"``).
        clock_source: PFI terminal for 1 kHz laser sync
            (e.g. ``"/Dev1/PFI0"``).
        sync_source: PFI terminal for 250 Hz chopper pulse
            (e.g. ``"/Dev1/PFI12"``).
        counter: Counter channel to use (default ``"ctr1"`` → output PFI13).
    """

    def __init__(
        self,
        device: str = "Dev1",
        clock_source: str = "/Dev1/PFI0",
        sync_source: str = "/Dev1/PFI12",
        counter: str = "ctr1",
    ) -> None:
        self._device = device
        self._clock_source = clock_source
        self._sync_source = sync_source
        self._counter = counter
        self._task = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Configure and start the NI counter task.

        Raises:
            ImportError: If the ``nidaqmx`` package is not installed.
        """
        try:
            import nidaqmx
            from nidaqmx.constants import AcquisitionType, Edge
        except (ImportError, TypeError) as exc:
            raise ImportError(
                "nidaqmx is required for hardware trigger generation. "
                "Install with: uv pip install nidaqmx"
            ) from exc

        self._task = nidaqmx.Task()

        # Divide PFI0 (1 kHz) by 2 → 500 Hz pulse train on CTR1OUT
        self._task.co_channels.add_co_pulse_chan_ticks(
            f"{self._device}/{self._counter}",
            source_terminal=self._clock_source,
            low_ticks=1,
            high_ticks=1,
        )

        self._task.timing.cfg_implicit_timing(
            sample_mode=AcquisitionType.CONTINUOUS
        )

        # Re-sync phase on every 250 Hz chopper pulse (rising edge)
        self._task.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=self._sync_source,
            trigger_edge=Edge.RISING,
        )
        self._task.triggers.start_trigger.retriggerable = True

        self._task.start()
        log.debug(
            f"NIDAQChopper500Hz started: clock={self._clock_source}, "
            f"sync={self._sync_source}, counter={self._counter}"
        )

    def stop(self) -> None:
        """Stop and release the NI counter task."""
        if self._task is not None:
            self._task.stop()
            self._task.close()
            self._task = None
            log.debug("NIDAQChopper500Hz stopped")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "NIDAQChopper500Hz":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()


class MockNIDAQChopper500Hz:
    """Mock trigger generator for tests and mock-mode operation.

    Accepts the same constructor arguments as ``NIDAQChopper500Hz`` and
    provides the same ``start`` / ``stop`` / context-manager interface,
    but performs no hardware operations.

    Args:
        **kwargs: Ignored; accepted for API compatibility.
    """

    def __init__(self, **kwargs) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        """Return True if the mock trigger is currently active."""
        return self._running

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def __enter__(self) -> "MockNIDAQChopper500Hz":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()
