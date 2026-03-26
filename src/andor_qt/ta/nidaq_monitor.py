"""NI DAQ signal monitor — burst capture digital timing signals.

Captures a short burst of samples from up to three digital channels using
the NI DAQ internal onboard clock so the monitor is independent of any
running counter or phase-reader task.

Default channels (PCIe-6353):
  - PFI0        : 1 kHz laser sync input
  - PFI13       : 500 Hz camera trigger output (CTR1OUT)
  - port0/line0 : Chopper phase signal (P0.0)

``NIDAQSignalMonitor.sample()`` is a blocking call that takes
``n_samples / sample_rate`` seconds (default ~40 ms).  Call it from a
background thread to avoid blocking the GUI.
"""

from __future__ import annotations

import logging
import time

import numpy as np

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

DEFAULT_CHANNELS: list[tuple[str, str]] = [
    ("PFI0",        "1 kHz Laser (PFI0)"),
    ("PFI13",       "500 Hz Trigger (PFI13)"),
    ("port0/line0", "Chopper Phase (P0.0)"),
]


class NIDAQSignalMonitor:
    """Burst-sample digital channels for timing diagnostics.

    Args:
        device: NI DAQ device name (e.g. ``"Dev1"``).
        channels: List of ``(channel_spec, label)`` pairs to capture.
        sample_rate: Internal sample clock rate in Hz.
        n_samples: Samples per channel per burst (~40 ms at 20 kHz default).
    """

    def __init__(
        self,
        device: str = "Dev1",
        channels: list[tuple[str, str]] | None = None,
        sample_rate: float = 20_000.0,
        n_samples: int = 800,
    ) -> None:
        self._device = device
        self._channels = channels if channels is not None else DEFAULT_CHANNELS
        self._sample_rate = sample_rate
        self._n_samples = n_samples

    @property
    def labels(self) -> list[str]:
        return [lbl for _, lbl in self._channels]

    @property
    def time_ms(self) -> np.ndarray:
        return np.arange(self._n_samples) / self._sample_rate * 1_000.0

    def sample(self) -> dict[str, np.ndarray]:
        """Capture a burst of digital samples.

        Port channels (e.g. port0/line0) are read with hardware clock timing.
        PFI channels are read with software polling (they don't support
        buffered DI on PCIe-6353 but on-demand point reads work fine).

        Returns:
            Dict mapping label -> int8 array of length ``n_samples``.
            Channels that cannot be read are silently omitted.
        """
        try:
            import nidaqmx  # noqa: F401
        except ImportError:
            return {}

        results: dict[str, np.ndarray] = {}
        for spec, label in self._channels:
            try:
                if spec.startswith("PFI"):
                    results[label] = self._read_polled(spec)
                else:
                    results[label] = self._read_hardware_timed(spec)
            except Exception as exc:
                log.warning(f"Signal monitor: could not read {spec}: {exc}")
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_hardware_timed(self, spec: str) -> np.ndarray:
        """Hardware-clocked DI read for port lines (e.g. port0/line0)."""
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, Edge

        with nidaqmx.Task() as task:
            task.di_channels.add_di_chan(f"{self._device}/{spec}")
            task.timing.cfg_samp_clk_timing(
                rate=self._sample_rate,
                source="",
                active_edge=Edge.RISING,
                sample_mode=AcquisitionType.FINITE,
                samps_per_chan=self._n_samples,
            )
            task.start()
            raw = task.read(
                number_of_samples_per_channel=self._n_samples, timeout=5.0
            )
        return np.array(raw, dtype=np.int8)

    def _read_polled(self, spec: str) -> np.ndarray:
        """Software-polled on-demand read for PFI lines.

        Uses busy-wait to achieve approximate hardware-rate sampling.
        Sufficient for visualising signals up to ~1 kHz.
        """
        import nidaqmx

        dt = 1.0 / self._sample_rate
        samples = np.empty(self._n_samples, dtype=np.int8)
        with nidaqmx.Task() as task:
            task.di_channels.add_di_chan(f"{self._device}/{spec}")
            t0 = time.perf_counter()
            for i in range(self._n_samples):
                samples[i] = int(task.read())
                # Busy-wait until next sample time for consistent spacing
                next_t = t0 + (i + 1) * dt
                while time.perf_counter() < next_t:
                    pass
        return samples


class MockNIDAQSignalMonitor:
    """Mock signal monitor — no NI hardware required."""

    def __init__(
        self,
        sample_rate: float = 20_000.0,
        n_samples: int = 800,
        **kwargs,
    ) -> None:
        self._sample_rate = sample_rate
        self._n_samples = n_samples

    @property
    def labels(self) -> list[str]:
        return [lbl for _, lbl in DEFAULT_CHANNELS]

    @property
    def time_ms(self) -> np.ndarray:
        return np.arange(self._n_samples) / self._sample_rate * 1_000.0

    def sample(self) -> dict[str, np.ndarray]:
        """Return synthetic timing signals matching real hardware patterns."""
        t = np.arange(self._n_samples) / self._sample_rate  # seconds

        # 1 kHz laser sync: short TTL pulses (~10 % duty)
        p_laser = 1.0 / 1_000.0
        laser = ((t % p_laser) < p_laser * 0.10).astype(np.int8)

        # 500 Hz camera trigger: 50 % duty square wave
        p_trig = 1.0 / 500.0
        trig = ((t % p_trig) < p_trig * 0.50).astype(np.int8)

        # Chopper phase on P0.0: stable for 2 ms (2 laser shots), 250 Hz toggle
        p_chop = 1.0 / 250.0
        chopper = ((t % p_chop) < p_chop * 0.50).astype(np.int8)

        _, lbl0 = DEFAULT_CHANNELS[0]
        _, lbl1 = DEFAULT_CHANNELS[1]
        _, lbl2 = DEFAULT_CHANNELS[2]
        return {lbl0: laser, lbl1: trig, lbl2: chopper}
