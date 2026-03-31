# Continuous Camera Mode for Chopper Acquisition

**Extracted:** 2026-03-30
**Context:** chopper_2x2 acquisition with Andor DU970P and MC2000B chopper

## Problem
Restarting the camera (`abort_acquisition` -> `start_run_till_abort`) between acquisition cycles randomizes the phase relationship between camera frames and the chopper blade. This causes the pump-ON/OFF tag assignment to flip randomly (50/50). Hardware sync on PFI13 does NOT fix this.

## Solution
Start the camera ONCE and keep it running for the entire session. Read accumulated frames with `get_buffered_frames()` which uses `GetNumberNewImages()` to return only new frames since the last read.

```python
# Start once
camera.start_run_till_abort()
phase_reader.start()
phase_reader.drain()

# Loop without restarting
while not abort:
    time.sleep(wait_s)
    frames, n = camera.get_buffered_frames()  # only NEW frames
    tags = phase_reader.read_tags(n * shots_per_frame)
    delta = _process_chopper_frames(frames, tags, config)

# Stop once
camera.abort_acquisition()
phase_reader.stop()
```

The circular buffer holds ~12000 frames (~24 seconds at 500 Hz). As long as reads happen within this window, no data is lost.

## When to Use
Any chopper_2x2 acquisition — monitor mode, TA scan, or standalone test scripts. The tag-to-frame alignment is set on the first read and stays stable for the entire camera session.
