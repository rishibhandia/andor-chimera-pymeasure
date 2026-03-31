#!/usr/bin/env python
"""Quick chopper_2x2 test — mirrors the GUI's exact acquisition path.

Close the GUI before running this. Run from project root:
    uv run python scripts/test_chopper_quick.py

Uses the same camera init, settings, and acquisition code as the app.
"""

from __future__ import annotations

import sys
import time

import numpy as np

# Camera settings — match your GUI settings exactly
CAMERA_SETTINGS = {
    "trigger_mode": "fast_external",
    "exposure_time": 0.0004,  # 0.4 ms
    "vs_speed": 0,            # 4.88 us (fastest)
    "hs_speed": 0,            # 3 MHz (fastest)
    "hbin": 1,
    "vbin": 1,
}

DEVICE = "Astrella_DAQ"
N_AVERAGES = 100
SHOTS_PER_FRAME = 2
N_CYCLES = 5  # number of read cycles (camera stays running)


def main():
    print("=" * 60)
    print("Quick Chopper_2x2 Test")
    print("=" * 60)

    # --- Init camera + spectrograph (same as hardware_manager._init_real_hardware) ---
    from andor_pymeasure.instruments.andor_camera import AndorCamera
    from andor_pymeasure.instruments.andor_spectrograph import AndorSpectrograph

    sdk_path = r"C:\Program Files\Andor SDK"
    print(f"Initializing camera (SDK: {sdk_path})...")
    camera = AndorCamera(sdk_path=sdk_path)
    camera.initialize()
    print(f"  Camera: {camera._info.xpixels}x{camera._info.ypixels}")

    print("Initializing spectrograph...")
    spectrograph = AndorSpectrograph(device_index=0, sdk_path=sdk_path)
    spectrograph.initialize()
    print(f"  Spectrograph: grating={spectrograph.grating}, wavelength={spectrograph.wavelength}nm")

    # --- Init phase reader (same as _make_daq_hardware) ---
    from andor_qt.ta.nidaq_phase import NIDAQPhaseReader

    print("Initializing phase reader...")
    phase_reader = NIDAQPhaseReader(
        device=DEVICE,
        di_channel="port0/line0",
        clock_source=f"/{DEVICE}/PFI0",
        clock_rate=1000.0,
    )

    # --- Apply camera settings (same as monitor engine) ---
    print(f"Applying camera settings: {CAMERA_SETTINGS}")
    camera.apply_camera_settings(CAMERA_SETTINGS)

    # --- Sync to chopper on PFI13 (hardware edge detect) ---
    print("Syncing to chopper rising edge on PFI13...")
    try:
        import nidaqmx
        from nidaqmx.constants import Edge

        with nidaqmx.Task("chopper_sync") as sync_task:
            sync_task.ci_channels.add_ci_count_edges_chan(
                f"{DEVICE}/ctr0", edge=Edge.RISING,
            )
            sync_task.ci_channels[0].ci_count_edges_term = f"/{DEVICE}/PFI13"
            sync_task.start()
            sync_task.read(timeout=5.0)
        print("  Sync OK")
    except Exception as exc:
        print(f"  Sync failed: {exc} -- continuing anyway")

    # --- Start camera + phase reader (continuous, no restart) ---
    print("Starting camera (RTA) and phase reader...")
    camera.start_run_till_abort()
    phase_reader.start()
    phase_reader.drain()
    print("  Running")

    # --- Read cycles (same as monitor _run_continuous) ---
    from andor_qt.ta.acquisition import _process_chopper_frames, last_acquisition_stats
    from andor_qt.ta.scan_config import TAScanConfig

    config = TAScanConfig(
        delay_list=[0.0],
        n_averages=N_AVERAGES,
        acquisition_mode="chopper_2x2",
        scan_direction="forward",
        sample_name="test",
        shots_per_frame=SHOTS_PER_FRAME,
    )

    spf = SHOTS_PER_FRAME
    n_target = int(N_AVERAGES * 2.2) + 10
    wait_s = (n_target * spf) / 1000.0 + 0.05

    results = []
    for cycle in range(N_CYCLES):
        time.sleep(wait_s)
        frames, n_chunk = camera.get_buffered_frames()
        if n_chunk == 0:
            print(f"  Cycle {cycle+1}: no frames!")
            continue

        tags = phase_reader.read_tags(n_chunk * spf)

        try:
            delta = _process_chopper_frames(frames, tags, config)
        except RuntimeError as exc:
            print(f"  Cycle {cycle+1}: {exc}")
            continue

        stats = last_acquisition_stats
        on_mean = float(np.asarray(stats.get("pump_mean", [0])).mean())
        off_mean = float(np.asarray(stats.get("ref_mean", [0])).mean())
        n_on = stats.get("n_on", 0)
        n_off = stats.get("n_off", 0)

        ratio = on_mean / off_mean if off_mean > 0 else float("inf")
        print(f"  Cycle {cycle+1}: ON={on_mean:.1f}  OFF={off_mean:.1f}  "
              f"ratio={ratio:.2f}  n_on={n_on}  n_off={n_off}  "
              f"frames={n_chunk}")
        results.append((on_mean, off_mean))

    # --- Cleanup ---
    print("\nStopping...")
    camera.abort_acquisition()
    phase_reader.stop()
    spectrograph.shutdown()
    camera.shutdown()

    # --- Summary ---
    print("\n" + "=" * 60)
    if results:
        on_means = [r[0] for r in results]
        off_means = [r[1] for r in results]
        print(f"ON  mean: {np.mean(on_means):.1f} (std {np.std(on_means):.1f})")
        print(f"OFF mean: {np.mean(off_means):.1f} (std {np.std(off_means):.1f})")
        if abs(np.mean(on_means) - np.mean(off_means)) > 100:
            print("RESULT: PASS -- clear ON/OFF separation")
        else:
            print("RESULT: FAIL -- ON and OFF look the same")
    else:
        print("RESULT: FAIL -- no valid cycles")

    return 0


if __name__ == "__main__":
    sys.exit(main())
