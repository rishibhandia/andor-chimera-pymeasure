"""NI DAQ hardware phase reader for pump-probe chopper synchronization.

``NIDAQPhaseReader`` reads a digital input line on an NI PCIe-6353 (or
compatible) card, clocked by the laser trigger on a PFI line.  Each
sample corresponds to one camera frame; the value (1 or 0) indicates
whether the chopper was open (pump-on) or closed (pump-off) for that shot.

Typical wiring
--------------
  Chopper controller REF OUT (500 Hz TTL)  →  NI DI line  (e.g. Dev1/port0/line0)
  Laser sync OUT (1 kHz TTL)               →  NI PFI0     (hardware sample clock)
  Laser sync OUT (1 kHz TTL)               →  Camera Ext Trigger SMB

Usage
-----
    reader = NIDAQPhaseReader(
        device="Dev1",
        di_channel="port0/line0",
        clock_source="/Dev1/PFI0",
        clock_rate=1000.0,
    )
    with reader:
        for _ in range(n_shots):
            spectrum = camera.get_spectrum()   # triggered by laser
            tag = reader.read_one()            # 1=pump-on, 0=pump-off

``MockNIDAQPhaseReader`` provides the same interface without hardware,
generating a strict 1-0-1-0 alternating pattern suitable for tests.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


class NIDAQPhaseReader:
    """Read chopper phase tags from an NI DAQ digital input, hardware-clocked.

    Args:
        device: NI DAQ device name (e.g. ``"Dev1"``).
        di_channel: Digital input channel spec relative to device
            (e.g. ``"port0/line0"``).
        clock_source: PFI terminal used as the sample clock
            (e.g. ``"/Dev1/PFI0"``).  Must be driven by the laser sync.
        clock_rate: Nominal clock rate in Hz (must match laser rep rate).
        buffer_size: Number of samples to buffer in the NI driver.
    """

    def __init__(
        self,
        device: str = "Dev1",
        di_channel: str = "port0/line0",
        clock_source: str = "/Dev1/PFI0",
        clock_rate: float = 1000.0,
        buffer_size: int = 100000,
    ) -> None:
        self._device = device
        self._di_channel = di_channel
        self._clock_source = clock_source
        self._clock_rate = clock_rate
        self._buffer_size = buffer_size
        self._task = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Create and start the NI DAQ task."""
        try:
            import nidaqmx
            from nidaqmx.constants import AcquisitionType, Edge
        except ImportError as exc:
            raise ImportError(
                "nidaqmx is required for hardware chopper sync. "
                "Install it with: uv pip install nidaqmx"
            ) from exc

        self._task = nidaqmx.Task()
        channel = f"{self._device}/{self._di_channel}"
        self._task.di_channels.add_di_chan(channel)
        self._task.timing.cfg_samp_clk_timing(
            rate=self._clock_rate,
            source=self._clock_source,
            active_edge=Edge.RISING,
            sample_mode=AcquisitionType.CONTINUOUS,
            samps_per_chan=self._buffer_size,
        )
        self._task.start()

    def stop(self) -> None:
        """Stop and release the NI DAQ task."""
        if self._task is not None:
            self._task.stop()
            self._task.close()
            self._task = None

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_one(self) -> int:
        """Read a single phase tag.  Blocks until one sample is available.

        Returns:
            1 if chopper was open (pump-on), 0 if closed (pump-off).
        """
        tags = self.read_tags(1)
        return int(tags[0])

    def drain(self) -> None:
        """Discard all samples currently in the buffer.

        Call this immediately before ``get_spectrum()`` so that the next
        ``read_tags(n)`` call returns only the samples acquired during that
        camera frame, not stale samples from stage moves or setup delays.
        """
        if self._task is None:
            return
        avail = self._task.in_stream.avail_samp_per_chan
        if avail > 0:
            self._task.read(number_of_samples_per_channel=avail)

    def read_tags(self, n: int) -> np.ndarray:
        """Read ``n`` phase tags.  Blocks until all samples are available.

        Args:
            n: Number of samples to read (one per camera frame).

        Returns:
            1-D integer numpy array of length ``n`` with values 0 or 1.
        """
        if self._task is None:
            raise RuntimeError("NIDAQPhaseReader not started — call start() first")
        raw = self._task.read(number_of_samples_per_channel=n)
        return np.array(raw, dtype=np.int8)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "NIDAQPhaseReader":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()


class MockNIDAQPhaseReader:
    """Mock phase reader for tests — no NI hardware required.

    Generates a strict alternating 1-0-1-0 pattern.  ``initial_phase``
    controls whether the sequence starts with pump-on (1, default) or
    pump-off (0).

    Args:
        initial_phase: Starting tag value.  1 = pump-on first (default),
            0 = pump-off first.
    """

    def __init__(self, initial_phase: int = 1, **kwargs) -> None:
        if initial_phase not in (0, 1):
            raise ValueError("initial_phase must be 0 or 1")
        self._initial_phase = initial_phase
        self._counter = 0

    def start(self) -> None:
        self._counter = 0

    def stop(self) -> None:
        pass

    def drain(self) -> None:
        pass

    def read_one(self) -> int:
        """Return the next tag and advance the counter."""
        tag = (self._initial_phase + self._counter) % 2
        self._counter += 1
        return tag

    def read_tags(self, n: int) -> np.ndarray:
        """Return the next ``n`` tags as a numpy array."""
        start = self._counter
        tags = np.array(
            [(self._initial_phase + start + i) % 2 for i in range(n)],
            dtype=np.int8,
        )
        self._counter += n
        return tags

    def __enter__(self) -> "MockNIDAQPhaseReader":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()


class MockNIDAQChopper2x2Reader:
    """Mock phase reader for chopper_2x2 mode — no NI hardware required.

    Simulates 250 Hz chopping of a 1 kHz laser: each pair of consecutive
    shots has the same phase (pump-on: [1, 1], pump-off: [0, 0]).

    ``read_tags(2)`` returns matched pairs, suitable for ``_acquire_chopper_2x2``.

    Args:
        initial_phase: Starting frame phase.  1 = pump-on frame first (default),
            0 = pump-off frame first.
    """

    def __init__(self, initial_phase: int = 1, **kwargs) -> None:
        if initial_phase not in (0, 1):
            raise ValueError("initial_phase must be 0 or 1")
        self._initial_phase = initial_phase
        self._shot_counter = 0

    def start(self) -> None:
        self._shot_counter = 0

    def stop(self) -> None:
        pass

    def drain(self) -> None:
        pass

    def read_one(self) -> int:
        """Return the next shot tag (pattern: 1,1,0,0,1,1,0,0,…)."""
        # Each group of 2 consecutive shots has the same phase
        frame = self._shot_counter // 2
        tag = (self._initial_phase + frame) % 2
        self._shot_counter += 1
        return int(tag)

    def read_tags(self, n: int) -> np.ndarray:
        """Return the next ``n`` shot tags as a numpy array.

        When ``n == 3`` (arm/drain/collect pattern), returns
        ``[tag, tag, next_tag]`` — two exposure samples for the current camera
        frame plus the first sample of the next frame — and advances the
        internal counter by exactly one camera frame (2 shots).
        """
        if n == 3:
            # Simulate 0 pre-exposure samples + 2 exposure + 1 next-frame sample
            frame = self._shot_counter // 2
            tag = (self._initial_phase + frame) % 2
            next_tag = 1 - tag
            self._shot_counter += 2  # advance by one full camera frame
            return np.array([tag, tag, next_tag], dtype=np.int8)
        return np.array([self.read_one() for _ in range(n)], dtype=np.int8)

    def __enter__(self) -> "MockNIDAQChopper2x2Reader":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()
