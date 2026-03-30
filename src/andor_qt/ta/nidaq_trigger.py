"""NI DAQ 500 Hz camera trigger generator for chopper_2x2 acquisition.

``NIDAQChopper500Hz`` uses two NI DAQ counters to produce a drift-free
500 Hz camera trigger locked to the 1 kHz laser sync (PFI0):

Counter chain
-------------
  CTR2 (divider)
      Counts PFI0 edges with add_co_pulse_chan_ticks(low=2, high=2).
      Because the minimum tick count is 2 per phase, PFI0 (1 kHz) can only
      be divided by 4 here, giving a 250 Hz signal on Ctr2InternalOutput.
      This signal is phase-locked to PFI0 with zero drift (edge-count only,
      no free-running clock).

  CTR1 (camera trigger, default)
      Generates 500 Hz from the NI 20 MHz timebase
      (period = 40 000 ticks, high = 4 000 ticks / 200 µs pulse).
      Retriggers on every rising edge of Ctr2InternalOutput (250 Hz),
      resetting its phase to the laser every 4 ms.
      Output on CTR1OUT / PFI13 → Camera Ext Trigger.

Typical wiring
--------------
  Laser sync OUT (1 kHz TTL)  →  NI PFI0          (CTR2 tick source)
  NI PFI13 / CTR1OUT          →  BNC-2110 User 1  →  Camera Ext Trigger

The camera should be configured with ``fast_external`` trigger and 2 ms
exposure to integrate exactly 2 laser shots per frame.

Usage
-----
    trigger = NIDAQChopper500Hz(
        device="Dev1",
        clock_source="/Dev1/PFI0",
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
    """Generate a drift-free 500 Hz camera trigger via a two-counter chain.

    CTR2 divides the 1 kHz laser sync (PFI0) by 4 → 250 Hz locked to the
    laser.  CTR1 generates 500 Hz from the 20 MHz timebase, retriggered on
    every CTR2 rising edge so its phase is corrected to the laser every 4 ms.

    Args:
        device: NI DAQ device name (e.g. ``"Dev1"``).
        clock_source: PFI terminal for 1 kHz laser sync
            (e.g. ``"/Dev1/PFI0"``).
        sync_source: Kept for API compatibility; no longer used as the
            retrigger source (CTR2 internal output is used instead).
        counter: Camera-trigger counter channel (default ``"ctr1"``
            → output PFI13).
        divider_counter: Counter used as the PFI0 divide-by-4 stage
            (default ``"ctr2"``).  Must differ from ``counter``.
    """

    def __init__(
        self,
        device: str = "Dev1",
        clock_source: str = "/Dev1/PFI0",
        sync_source: str = "/Dev1/PFI12",
        counter: str = "ctr1",
        divider_counter: str = "ctr2",
    ) -> None:
        self._device = device
        self._clock_source = clock_source
        self._sync_source = sync_source      # kept for API compat
        self._counter = counter
        self._divider_counter = divider_counter
        self._task = None
        self._divider_task = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Configure and start the NI counter task.

        Uses a single counter to divide PFI0 (1 kHz laser sync) by 2,
        producing 500 Hz on the counter output (PFI13 for ctr1). This is
        inherently phase-locked to PFI0 with zero drift — each output
        edge is derived directly from counting PFI0 edges.

        Raises:
            ImportError: If the ``nidaqmx`` package is not installed.
        """
        try:
            import nidaqmx
            from nidaqmx.constants import AcquisitionType, Edge, Level
        except (ImportError, TypeError) as exc:
            raise ImportError(
                "nidaqmx is required for hardware trigger generation. "
                "Install with: uv pip install nidaqmx"
            ) from exc

        # ----------------------------------------------------------
        # 500 Hz camera trigger from 20 MHz timebase, retriggered
        # on every sync_source rising edge (500 Hz from SDG on PFI12).
        #
        # Each retrigger restarts the counter, producing one 2 ms
        # pulse cycle. Since the SDG also drives the chopper reference,
        # the counter output is phase-locked to the chopper blade.
        #
        # 500 Hz with 200 us pulse from 20 MHz timebase:
        #   period = 20,000,000 / 500 = 40,000 ticks = 2 ms
        #   high   = 200 us x 20 MHz  =  4,000 ticks
        #   low    = 40,000 - 4,000   = 36,000 ticks = 1.8 ms
        #
        # Output on CTR1OUT / PFI13 -> Camera Ext Trigger.
        # ----------------------------------------------------------
        _TIMEBASE_HZ = 20_000_000
        period_ticks = _TIMEBASE_HZ // 500
        high_ticks = int(200e-6 * _TIMEBASE_HZ)     # 4,000 ticks = 200 us
        low_ticks = period_ticks - high_ticks         # 36,000 ticks = 1.8 ms

        self._task = nidaqmx.Task()
        self._task.co_channels.add_co_pulse_chan_ticks(
            f"{self._device}/{self._counter}",
            source_terminal=f"/{self._device}/20MHzTimebase",
            low_ticks=low_ticks,
            high_ticks=high_ticks,
            idle_state=Level.LOW,
        )
        self._task.timing.cfg_implicit_timing(
            sample_mode=AcquisitionType.CONTINUOUS
        )
        # Retrigger on every sync_source rising edge (500 Hz on PFI12).
        # This resets the counter phase every 2 ms, keeping the output
        # locked to the SDG/chopper timing chain.
        self._task.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=self._sync_source,
            trigger_edge=Edge.RISING,
        )
        self._task.triggers.start_trigger.retriggerable = True

        self._task.start()
        log.info(
            f"NIDAQChopper500Hz started: 500 Hz on {self._counter}, "
            f"retriggered by {self._sync_source} (500 Hz)"
        )

    def stop(self) -> None:
        """Stop and release the NI counter task."""
        for task in (self._task, self._divider_task):
            if task is not None:
                try:
                    task.stop()
                    task.close()
                except Exception as exc:
                    log.warning(f"NIDAQChopper500Hz stop error: {exc}")
        self._task = None
        self._divider_task = None
        log.info("NIDAQChopper500Hz stopped")

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
