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

    def start(self, start_trigger: str | None = None) -> None:
        """Create and start the NI DAQ task.

        Args:
            start_trigger: Optional PFI terminal for a digital-edge start
                trigger (e.g. ``"/{device}/PFI13"``).  When set, the task
                arms but does not acquire samples until the specified
                rising edge arrives.  Use the Camera Fire output to
                guarantee that tag[0] corresponds to frame[0].
        """
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
        if start_trigger is not None:
            self._task.triggers.start_trigger.cfg_dig_edge_start_trig(
                trigger_source=start_trigger,
                trigger_edge=Edge.RISING,
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
        raw = self._task.read(number_of_samples_per_channel=n, timeout=10.0)
        return np.array(raw, dtype=np.int8)

    def read_available_tags(self) -> np.ndarray:
        """Read all currently available tags without blocking.

        Returns:
            1-D integer numpy array (may be empty).
        """
        if self._task is None:
            return np.array([], dtype=np.int8)
        avail = self._task.in_stream.avail_samp_per_chan
        if avail == 0:
            return np.array([], dtype=np.int8)
        raw = self._task.read(number_of_samples_per_channel=avail)
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

    Supports both single-shot (shot_to_shot) and paired (chopper_2x2) patterns
    via the ``shots_per_frame`` parameter:

    - ``shots_per_frame=1``: alternating ``1,0,1,0,...`` (one tag per frame)
    - ``shots_per_frame=2``: paired ``1,1,0,0,1,1,0,0,...`` (two tags per frame)

    Args:
        initial_phase: Starting tag value.  1 = pump-on first (default).
        shots_per_frame: Number of consecutive identical tags per frame.
    """

    def __init__(self, initial_phase: int = 1, shots_per_frame: int = 1, **kwargs) -> None:
        if initial_phase not in (0, 1):
            raise ValueError("initial_phase must be 0 or 1")
        self._initial_phase = initial_phase
        self._shots_per_frame = shots_per_frame
        self._shot_counter = 0

    def start(self, start_trigger: str | None = None) -> None:
        self._shot_counter = 0

    def stop(self) -> None:
        pass

    def drain(self) -> None:
        pass

    def read_one(self) -> int:
        """Return the next tag and advance the counter."""
        frame = self._shot_counter // self._shots_per_frame
        tag = (self._initial_phase + frame) % 2
        self._shot_counter += 1
        return int(tag)

    def read_tags(self, n: int) -> np.ndarray:
        """Return the next ``n`` tags as a numpy array."""
        return np.array([self.read_one() for _ in range(n)], dtype=np.int8)

    def read_available_tags(self) -> np.ndarray:
        """Non-blocking read — mock returns pending tags from the buffer.

        In real hardware, this returns however many tags the NI DAQ has
        buffered since the last read. The mock simulates this by returning
        ``_pending`` tags (set by ``set_pending()``), defaulting to 0.
        """
        n = getattr(self, "_pending_count", 0)
        if n > 0:
            self._pending_count = 0
            return self.read_tags(n)
        return np.array([], dtype=np.int8)

    def set_pending(self, n: int) -> None:
        """Set the number of tags that ``read_available_tags`` will return."""
        self._pending_count = n

    def __enter__(self) -> "MockNIDAQPhaseReader":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()


# Backward-compatible alias
MockNIDAQChopper2x2Reader = lambda initial_phase=1, **kw: MockNIDAQPhaseReader(
    initial_phase=initial_phase, shots_per_frame=2, **kw
)
