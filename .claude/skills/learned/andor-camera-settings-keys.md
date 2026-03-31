# Andor Camera apply_camera_settings Key Names

**Extracted:** 2026-03-30
**Context:** Standalone scripts or test scripts that configure the Andor DU970P camera

## Problem
`apply_camera_settings()` silently ignores unknown keys. Using `vs_speed` instead of `vs_speed_index` means VS speed is never configured, causing the camera readout to be too slow. This produces identical ON/OFF frames in chopper_2x2 mode because each frame straddles the chopper transition.

## Solution
Always use the exact key names that `CameraSettingsWidget.get_settings()` returns:

```python
camera.apply_camera_settings({
    "trigger_mode": "fast_external",   # not "trigger"
    "exposure_time": 0.0004,           # seconds, float
    "vs_speed_index": 0,               # NOT "vs_speed"
    "hs_speed_index": 0,               # NOT "hs_speed"
    "amplifier_type": 1,               # 0=EM, 1=conventional
    "preamp_gain_index": 0,            # NOT "preamp_gain"
    "em_gain": 1,                      # only used when amplifier_type=0
    "hbin": 1,
    "vbin": 1,
    "read_area_mode": "full",          # "full", "crop", "single_track"
})
```

## When to Use
Any time you write a standalone script, test, or diagnostic that calls `camera.apply_camera_settings()` outside the GUI. The GUI's `CameraSettingsWidget` always uses the correct keys.
