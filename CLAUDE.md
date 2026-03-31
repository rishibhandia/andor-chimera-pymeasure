# CLAUDE.md

Project-specific guidance for Claude Code when working on andor-chimera-pymeasure.

## CRITICAL: Background Process Management

**NEVER run more than 1-2 background Bash commands at a time.** This machine has limited memory. Excessive background processes (especially Python/pytest) cause Claude Code itself to crash.

Rules:
- **Run tests in FOREGROUND** — never use `run_in_background` for pytest or `uv run` commands
- **Only use background for**: launching the app (`uv run python -m andor_qt`) or long git operations
- **Before launching a new background process**, check if previous ones are still running
- **Agent subprocesses are fine** — they manage their own lifecycle
- If a foreground command takes >2 minutes, increase the timeout instead of backgrounding it

**Killing Python processes (MUST do before relaunching the app):**
```bash
# Use PowerShell — most reliable on this machine
powershell.exe -Command "Stop-Process -Name python -Force -ErrorAction SilentlyContinue"
# Wait for camera SDK to release
sleep 3
```
**ALWAYS kill before relaunch.** The Andor camera SDK locks exclusively — if a previous python.exe holds it, the new instance gets DRV_NOT_AVAILABLE (20992).

## CRITICAL: Development Workflow

**STOP AND PLAN BEFORE CODING.** This project requires strict TDD with atomic commits.

### Required Workflow for Every Feature

1. **Plan atomic commits FIRST** - Before writing any code, identify the commits:
   ```
   Task: "Add user feedback to sequencer"

   Commits:
   1. feat: add FeedbackSequencerWidget class
   2. feat: integrate FeedbackSequencerWidget into main window
   3. test: add validation feedback tests
   ```

2. **For each commit, follow TDD**:
   - **RED**: Write failing tests first
   - Run tests → verify they FAIL
   - **GREEN**: Write minimal code to pass
   - Run tests → verify they PASS
   - **COMMIT**: Create atomic commit immediately

3. **Use task tracking** to maintain discipline:
   ```
   TaskCreate → for each planned commit
   TaskUpdate(in_progress) → when starting
   TaskUpdate(completed) → after commit
   ```

### What NOT To Do

❌ Implement features first, then write tests
❌ Make multiple changes before committing
❌ Batch all commits at the end
❌ Skip the planning phase

### Commit Checklist

Before each commit, verify:
- [ ] Tests were written BEFORE implementation
- [ ] Tests failed before implementation (RED phase verified)
- [ ] Commit does exactly ONE thing
- [ ] Tests pass after this commit
- [ ] No unrelated changes included

### Agents to Use

| Phase | Agent | Purpose |
|-------|-------|---------|
| Planning | `planner` or `/plan` | Break feature into atomic commits |
| Architecture | `architect` | Review design before implementation |
| Testing | `tdd-guide` | Write tests first (RED phase) |
| Implementation | Direct coding | Write minimal code to pass tests |
| Commit | `git-commit` | Verify atomic, create commit |
| Debug | `debugger` | If tests fail unexpectedly |

### Example Workflow

```
User: "Add wavelength validation to spectrograph"

1. PLAN (use planner agent):
   Commits:
   - feat: add wavelength range validation to MockSpectrograph
   - feat: add validation error feedback in SpectrographControlWidget

2. FOR EACH COMMIT:
   a. TaskCreate("Add wavelength validation to MockSpectrograph")
   b. TaskUpdate(status=in_progress)
   c. Write test: test_wavelength_rejects_out_of_range
   d. Run pytest → FAILS (RED)
   e. Implement validation in MockSpectrograph
   f. Run pytest → PASSES (GREEN)
   g. git commit
   h. TaskUpdate(status=completed)
   i. Move to next commit
```

## Project Overview

Qt/PySide6 GUI and PyMeasure integration for Andor CCD spectrometer control. Two packages:
- **andor_qt** — Main GUI application
- **andor_pymeasure** — PyMeasure procedures and instrument drivers

## Project Stack

- **Language**: Python 3.11+
- **Build system**: uv with pyproject.toml
- **GUI framework**: PySide6 (Qt6)
- **Experiment framework**: PyMeasure
- **Testing**: pytest with pytest-qt
- **Linting**: ruff

## Code Style Guidelines

Follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) with these project-specific overrides:

- **Line length**: 100 characters (not 80 — Qt code is verbose)
- **Naming**: `lower_with_under` for functions/variables, `CamelCase` for classes, `CAPS_WITH_UNDER` for constants
- **Imports**: Absolute imports only, sorted by ruff, one per line (except `typing`)
- **Type hints**: Required on all public API functions. Use `from __future__ import annotations`
- **Docstrings**: Google style with `Args:`, `Returns:`, `Raises:` sections. Start with imperative verb
- **Mutable defaults**: Never use mutable objects (`[]`, `{}`) as default arguments
- **None checks**: Always `is None` / `is not None`, never `== None`
- **Boolean eval**: Use implicit false for sequences (`if not items:`)
- **Exceptions**: Never bare `except:`; minimize code inside `try` blocks
- **Properties**: Use for controlled access; no surprising side effects

### Property Docstrings (PyMeasure style)

For instrument properties, follow PyMeasure conventions:
```python
# Use "Control", "Measure", "Get", or "Set" to indicate property type
wavelength = Instrument.control(
    "?GW", ":GW %g",
    """Control the center wavelength in nm (float from 200 to 1100).""",
    validator=strict_range,
    values=[200, 1100],
)

temperature = Instrument.measurement(
    "?TEMP",
    """Measure the current temperature in degrees C (float, read-only).""",
)
```

## Quick Commands

```bash
# Run in mock mode (no hardware)
uv run python -m andor_qt --mock

# Run tests
uv run pytest

# Run specific test file
uv run pytest tests/qt/test_spectrum_overlay.py -v

# Check formatting
uv run ruff check src/
```

## Andor SDK Notes

### SDK Location
- **Windows**: `C:\Program Files\Andor SDK`
- The SDK path is configured in `HardwareManager` at `src/andor_qt/core/hardware_manager.py:77`
- **API reference**: `C:\Users\katsumilab\Downloads\Software Development Kit.pdf` (346 pages)
- **Hardware manual**: `C:\Users\katsumilab\Downloads\Andor_Newton_Manual.pdf` (44 pages)

### Required DLLs
- `atmcd64d.dll` — Camera control (CCD operations)
- `ShamrockCIF.dll` — Spectrograph control (gratings, wavelength)

### Mock Mode
- Set `ANDOR_MOCK=1` environment variable to force mock mode
- Mock implementations in `src/andor_pymeasure/instruments/mock.py`
- All tests run with `ANDOR_MOCK=1` automatically via `tests/conftest.py`

### SDK Return Codes
The Andor SDK uses integer return codes. Key ones:
- `20002` (DRV_SUCCESS) — Operation succeeded
- `20024` (DRV_TEMPERATURE_STABILIZED) — Cooler reached target
- `20034` (DRV_TEMPERATURE_NOT_REACHED) — Still cooling
- `20035` (DRV_TEMPERATURE_DRIFT) — Temperature drifting
- `20036` (DRV_TEMPERATURE_NOT_STABILIZED) — Not yet stabilized

### DU970P Newton EMCCD — Hardware Specifics

The camera is a **Newton DU970P EMCCD** (1600 × 200 pixels, 16 × 16 µm pixels, 16-bit).
It has **two output amplifiers** selectable in software:
- `type=0` → EM amplifier (use with EM gain for weak-signal / low-noise work)
- `type=1` → Conventional CCD amplifier (no EM multiplication, lower dark current)

#### VS Speeds (vertical shift, `SetVSSpeed(index)`)
| Index | Speed | Notes |
|-------|-------|-------|
| 0 | 4.9 µs/pixel | Fastest; slight CTE degradation possible |
| 1 | 9.8 µs/pixel | **Recommended default** (optimum CTE) |
| 2 | 19 µs/pixel | |
| 3 | 38 µs/pixel | |
| 4 | 57 µs/pixel | Slowest; best CTE |

Faster VS speeds increase clock-induced charge and heat at high frame rates (see Newton manual §6.2).

#### HS Speeds (horizontal readout, `SetHSSpeed(type, index)`)
| Index | Speed | Noise |
|-------|-------|-------|
| 0 | 3 MHz | Higher read noise (~tens of e⁻) |
| 1 | 1 MHz | Mid |
| 2 | 50 kHz | Lowest read noise |

Same speeds available for both EM and conventional amplifier.

#### EM Gain (`SetEMCCDGain(gain)`)
- Range: 1–1000 (queried at runtime via `GetEMGainRange()`)
- Only meaningful when EM amplifier (`type=0`) is selected
- Use ≥10 for EM noise benefit; at high gain EM noise factor = √2 (excess noise)
- Do NOT set EM gain when using conventional amplifier

#### Pre-Amplifier Gain (`SetPreAmpGain(index)`)
- Typically 3 options: ×1, ×2, ×4 (exact values queried at runtime via `GetNumberPreAmpGains / GetPreAmpGain`)
- Higher gain = better SNR for weak signals (lower effective read noise in e⁻/ADU)

#### Read Modes
- **FVB** (Full Vertical Binning): all 200 rows summed → 1D spectrum. Fastest for spectroscopy.
- **Image**: 2D readout with `SetImage(hbin, vbin, hstart, hend, vstart, vend)`
- **Single Track**: `SetSingleTrack(centre, height)` — bin `height` rows centred on `centre` (1-indexed from bottom)
- **Crop Mode**: `SetIsolatedCropMode(active, cropheight, cropwidth, vbin, hbin)`

#### Crop Mode — Critical Constraints (from SDK manual)
- Region is **always anchored to the bottom of the sensor** (nearest readout register). **Position CANNOT be adjusted on Newton cameras.**
- `SetIsolatedCropModeEx` (which allows position via `cropleft`/`cropbottom`) is **iXon Ultra only** — not available on DU970P.
- `SetCropMode` (simpler, FVB-only Newton variant) also anchors to bottom; only `cropHeight` parameter.
- **Light must NOT fall on excluded rows** — any charge there corrupts data through charge smear.
- `cropheight` and `cropwidth` must each be a multiple of their respective bin value.
- Newton supports FVB or Image read mode in isolated crop mode (iDus is FVB only).
- Achieves up to 1,515 spectra/sec with 20-row crop + 3 MHz HS speed.

#### `CameraSettingsWidget` — Usage Pattern
Shared widget in `src/andor_qt/widgets/hardware/camera_settings.py`.
Call `populate_from_camera(camera)` after hardware init to set runtime pre-amp options and EM gain range.
Returns settings via `get_settings()` dict → passed to `camera.apply_camera_settings(dict)`.
Used in: `DynamicInputsWidget`, `RealtimeWindow`, `TAScanConfigWidget`.

`get_settings()` keys: `trigger_mode`, `exposure_time` (seconds, float), `vs_speed`, `hs_speed`, `em_gain`, `pre_amp_gain`.
`exposure_spin` range: 1 µs–300 s (6 decimal places). Auto-set to 2 ms when `chopper_2x2` mode is selected in `TAScanConfigWidget`.

### Camera Shutdown
Always warm up before shutdown to prevent thermal damage:
```python
camera.set_cooler(False)  # Turn off cooler
# Wait for temp > -20°C before calling shutdown()
```
The GUI handles this automatically via `ShutdownDialog`.

## Motion Controllers

### Newport ESP302 — Delay Stage Controller

**Full API reference:** `ESP302-API-Reference.md` (in repo root)

#### Serial / TCP
- **RS-232**: 8N1, `rtscts=True` (**CRITICAL** — without it commands are silently dropped), 19200 baud typical
- **TCP port 5001**: raw ASCII (Telnet-style); **port 5002**: MKS Python wrapper library
- Commands end with `\r` (CR); responses end with `\r\n` (CR LF)

#### Command format (raw ASCII)
```
xxAAnnn\r      # xx = axis number (1–3), AA = mnemonic, nnn = params
1VA10\r        # set axis 1 velocity to 10 units/s
1TP\r          # query axis 1 position
```
Multiple commands in one line: semicolon-separated, max 80 chars.

#### Critical rules
| Rule | Detail |
|------|--------|
| **Motor on before move** | `xxMO` required; error `x13 MOTOR NOT ENABLED` if omitted |
| **No implicit wait** | ESP302 queues commands — always poll `xxMD?` (done=`1`) or send `xxWS` |
| **WS blocks serial** | In immediate mode `WS` freezes the port; use `MD?` polling from Python |
| **Home every power cycle** | `xxOR1` (switch + index); `MF` (soft off) retains position; `MK` clears it |
| **AB is all-axes** | `AB` stops and powers off ALL axes; no axis parameter |
| **PA over PR for precision** | Successive `PR` moves accumulate rounding error |

#### Key commands
| Command | Description |
|---------|-------------|
| `xxMO` / `xxMF` / `xxMK` | Motor ON / soft OFF / kill+clear-home |
| `xxOR1` | Home search (switch + index) |
| `xxPA{pos}` | Move to absolute position |
| `xxPR{delta}` | Move relative |
| `xxTP` | Read actual position |
| `xxMD?` | Motion done? `1`=done, `0`=moving |
| `xxVA{v}` / `xxAC{a}` | Set velocity / acceleration |
| `ST{ax}` / `AB` | Stop axis / emergency stop all |
| `TB` | Read oldest error (code, timestamp, message) |

#### Delay ↔ position conversion
```python
C_MM_PER_PS = 0.29979   # speed of light in mm/ps
def delay_ps_to_mm(delay_ps, reference_mm=0.0):
    return reference_mm + (delay_ps * C_MM_PER_PS) / 2   # /2 for double-pass
```

**Current project axis:** axis **2** (default changed from 1 to 2 in commit b5977be).

---

### OptoSigma GSC-02C + OSMS-YAW — Rotation Stage Controller

**Full API reference:** `GSC02-SGSP-YAW-Reference.md` (in repo root)

#### Serial connection
```python
serial.Serial(port='COM3', baudrate=9600, bytesize=8,
              parity='N', stopbits=1, rtscts=True, timeout=5)
```
- Factory DIP default: 9600 baud (SW2=OFF, SW1=ON)
- **`rtscts=True` required** — flow control is mandatory
- Commands end with `\r\n` (CR LF)

#### Critical rules
| Rule | Detail |
|------|--------|
| **M:/A:/J: need G:** | Motion commands only queue; **nothing moves until `G:` is sent** |
| **While BUSY** | Only `L:`, `Q:`, `!:`, `?:` accepted; all others silently ignored |
| **Homing direction** | OSMS-YAW: always `H:1-` (CW toward limit sensor) — `H:1+` runs CCW indefinitely |
| **No origin sensor** | OSMS-YAW has only a CW limit sensor; MINI homing touches it twice at two speeds |
| **`L:` won't stop `H:`** | Use `L:W` or `L:E` to abort a homing move |

#### Key commands
| Command | Returns | Description |
|---------|---------|-------------|
| `H:1-` | — | Home axis 1 CW (OSMS-YAW) |
| `M:1+P{n}` then `G:` | — | Relative move, n pulses CCW |
| `A:1+P{n}` then `G:` | — | Absolute move to pulse n (GSC-02C only) |
| `L:W` | — | Decelerate-stop all axes |
| `L:E` | — | Emergency stop all axes |
| `!:` | `B` or `R` | Quick busy check |
| `Q:` | `pos1,pos2,ACK1,ACK2,ACK3` | Full status (ACK3: `B`=busy, `R`=ready) |
| `R:W` | — | Zero coordinate at current position |

#### Stage specs (OSMS-YAW)
- 5-phase stepper, worm gear 1:144
- **400 pulses/degree** (half-step default, 0.0025°/pulse)
- CW hard stop at ~−2.5° (−1000 pulses); no CCW limit
- Positioning accuracy: 0.1°; repeatability: 0.02°; backlash: 0.1°

```python
PULSES_PER_DEGREE = 400
pulses = round(abs(degrees) * PULSES_PER_DEGREE)
```

#### DIP switch (OSMS-YAW required settings)
- SW3 = **OFF** (MINI homing — uses CW limit as reference)
- SW4 = **OFF** (Normal close limit sensor logic)

## TA (Transient Absorption) Module

### Overview

Pump-probe transient absorption measurement system. Key files:

| Class/File | Location | Purpose |
|-----------|----------|---------|
| `TAScanConfig` | `ta/scan_config.py` | Dataclass — all scan parameters |
| `TransientAbsorptionEngine` | `ta/engine.py` | Orchestrates scan loop in QThread |
| `TADataWriter` | `ta/hdf5_writer.py` | Writes ΔOD data to HDF5 files |
| `TAWindowPanel` | `windows/ta_panel.py` | Composite widget: config + live display |
| `TAScanConfigWidget` | `widgets/ta/scan_config_widget.py` | UI for configuring scans |
| `TALiveDisplayWidget` | `widgets/ta/live_display.py` | Real-time ΔOD plots |
| `NIDAQChopper500Hz` | `ta/nidaq_trigger.py` | Generates 500 Hz camera trigger via NI DAQ Counter 1 |
| `NIDAQPhaseReader` | `ta/nidaq_phase.py` | Reads chopper phase tags from P0.0 |

### Acquisition Modes

| Mode | Description |
|------|-------------|
| `boxcar` | Software alternation: first frame = pump-on, second = pump-off |
| `hardware` | NI DAQ hardware phase tags via P0.0; single shot per frame |
| `chopper_2x2` | 500 Hz camera trigger + chopper phase verification; 2 laser shots per frame |

### chopper_2x2 Mode — Hardware Wiring

**Concept:** 250 Hz chopper + 1 kHz laser → 500 Hz camera frames. Each frame integrates 2 laser shots (configurable via `shots_per_frame`). Camera is triggered externally by SDG at 500 Hz.

#### BNC-2110 Connections (current working setup)

| BNC-2110 Connector | NI PCIe-6353 Terminal | Direction | Signal |
|-------------------|----------------------|-----------|--------|
| User 1 BNC | PFI13 (P2.5, pin 40) | **INPUT** | Chopper REF OUT (INNER) — for phase sync |
| User 2 BNC | P0.0 (port0/line0) | **INPUT** | Chopper REF OUT (INNER) — phase tags |
| (dedicated BNC) | PFI0 | **INPUT** | 1 kHz laser sync clock |
| (dedicated BNC) | PFI12 (pin 2) | **INPUT** | SDG 500 Hz output (also chopper reference) |

Camera Ext Trigger SMB ← SDG 500 Hz (direct BNC connection, not through NI DAQ).

**CRITICAL — CTR0 conflict:** On PCIe-6353, CTR0 OUT is hardwired to PFI12 (pin 2) — the same pin used for the SDG input. **Never use CTR0 for counter output in this setup.**

#### Signal Chain

```
Laser 1 kHz → PFI0 (phase reader clock)
            → SDG (external reference)

SDG 500 Hz  → Camera Ext Trigger SMB (direct)
            → PFI12 (for NIDAQChopper500Hz retrigger, if used)
            → Chopper REF IN (chopper locks to SDG, runs at 250 Hz with ÷2)

Chopper REF OUT (INNER, 250 Hz) → P0.0 (User 2 BNC) — phase tags
                                → PFI13 (User 1 BNC) — hardware phase sync
```

#### Chopper Controller (Thorlabs MC2000B)

- **Blade:** MC1F10HP (10-slot high precision)
- **REF IN:** External, from SDG 500 Hz
- **Harmonic:** N=1, D=2 (divides SDG by 2 → 250 Hz chopper)
- **REF OUT:** INNER — tracks the actual blade position of inner slots
- **P0.0 = HIGH when blade is open** (beam passes through)

#### Camera Readout — Critical Lessons Learned

**Overlap mode is REQUIRED for 500 Hz with fast_external trigger.** Without overlap, the camera can only sustain ~260 Hz (exposure + readout > 2 ms frame period). With overlap enabled, readout happens during the next exposure, allowing 500 Hz. The camera may fire in bursts (not every trigger), but the frames that do fire are properly timed:
```python
self._sdk.SetOverlapMode(1)  # in start_run_till_abort()
```

**Without overlap, max frame rate is limited by exposure + readout:**
- VS=0, HS=0, hbin=1: readout ≈ 1.5 ms
- 0.4 ms exposure + 1.5 ms readout = 1.9 ms → max ~517 Hz
- 2.0 ms exposure + 1.5 ms readout = 3.5 ms → max ~285 Hz (too slow for 500 Hz)
- With overlap enabled, camera can sustain 500 Hz even with longer exposures

**Camera MUST NOT restart between acquisition cycles.** Restarting (`abort_acquisition` → `start_run_till_abort`) randomizes the phase relationship between camera frames and chopper blade, causing pump-ON/OFF assignment to flip randomly. The monitor engine now starts the camera once and keeps it running:
```python
# Monitor engine: camera starts ONCE before the loop
camera.start_run_till_abort()
phase_reader.start()
phase_reader.drain()
while not abort:
    frames = camera.get_buffered_frames()  # reads NEW frames only
    tags = phase_reader.read_tags(n * spf)
    delta = _process_chopper_frames(frames, tags, config)
camera.abort_acquisition()  # stops ONCE after the loop
```

`get_buffered_frames()` uses `GetNumberNewImages()` which returns only frames accumulated since the last read — safe for continuous operation. The circular buffer holds ~12000 frames (~24 seconds at 500 Hz).

**Phase sync on startup:** A hardware counter edge detection on PFI13 waits for the chopper blade rising edge before starting the camera. However, testing confirmed this does NOT deterministically set the tag-to-frame alignment — the initial phase is still random (50/50). **Continuous mode is what actually prevents flipping** — the phase is set once on first read and stays stable for the entire session.

**Tag-to-frame alignment:** The offset detection in `_process_chopper_frames` tries offsets 0 through `shots_per_frame-1` and picks the one with the most matched tag groups. This offset is re-detected each read cycle, but in continuous mode it stays consistent because the camera never restarts.

**P0.0 polarity (MC2000B):** The photo-interrupter polarity is fixed by hardware and does NOT change between sessions. From testing with the MC1F10HP blade with INNER REF OUT: P0.0=0 typically means beam passes (slot open), P0.0=1 means beam blocked. But the actual assignment depends on the tag-to-frame alignment offset, which varies per camera start. The ΔI/I₀ sign is determined by which tag group has higher intensity — this is consistent within a session.

**`_ensure_idle()` prevents DRV_ACQUIRING (20072).** Called at the top of `start_run_till_abort()` and `start_run_till_abort_crop()` — checks `GetStatus()` and aborts if still acquiring.

#### NIDAQChopper500Hz (optional — when not using SDG directly)

Generates 500 Hz from 20 MHz timebase, retriggered by PFI12 (500 Hz SDG):

```python
trigger_gen = NIDAQChopper500Hz(
    device="Dev1",
    clock_source="/Dev1/PFI0",    # 1 kHz laser sync
    sync_source="/Dev1/PFI12",    # 500 Hz SDG → retrigger source
    counter="ctr1",               # CTR1 → PFI13 output
)
```

**Note:** nidaqmx 1.4.1 does not support `Toggle.PULSE` for divide-by-2. The counter uses the 20 MHz timebase with retriggerable start trigger on PFI12. Retrigger IS supported on PCIe-6353 (confirmed by diagnostic test). When using the SDG directly to trigger the camera, check "External trigger (SDG)" in the UI to skip starting this counter.

#### NIDAQPhaseReader (for chopper_2x2)

Reads `shots_per_frame` phase tags per camera frame from P0.0, clocked by PFI0 (one sample per laser shot):

```python
phase_reader = NIDAQPhaseReader(
    device="Dev1",
    di_channel="port0/line0",     # P0.0 = User 2 BNC = chopper REF OUT
    clock_source="/Dev1/PFI0",    # 1 kHz laser sync
    clock_rate=1000.0,
)
# shots_per_frame=2: tags [1,1]=pump-ON, [0,0]=pump-OFF, [1,0]=discard
# shots_per_frame=4: tags [1,1,1,1]=pump-ON, [0,0,0,0]=pump-OFF
```

#### chopper_2x2 Acquisition Logic

The acquisition uses two functions:
- `_acquire_chopper_2x2()` — starts/stops camera (used by scan engine)
- `_process_chopper_frames()` — processes pre-read frames (used by continuous monitor)

Tag alignment: tries offsets 0 through `shots_per_frame-1` and picks the offset with the most matched groups (all tags in a group identical).

Frame assignment: P0.0=1 → pump-ON, P0.0=0 → pump-OFF. **No intensity-based auto-swap** — trust the chopper controller output directly.

#### Camera Settings for chopper_2x2

- **Trigger mode:** `fast_external` — camera waits for external trigger on Ext Trigger SMB
- **Exposure time:** 0.4 ms (must be ≤ 0.5 ms for 500 Hz without overlap)
- **VS speed:** index 0 (4.9 µs/row) — fastest, required for high frame rates
- **HS speed:** index 0 (3 MHz) — fastest
- **Overlap:** ENABLED (required for 500 Hz frame rate — DO NOT DISABLE)
- **shots_per_frame:** 2 (500 Hz camera / 250 Hz chopper) or 4 (250 Hz camera / 125 Hz chopper)
- **CRITICAL: `apply_camera_settings` key names must match exactly:**
  - `vs_speed_index` (not `vs_speed`) — without this, VS speed is never set and readout is too slow
  - `hs_speed_index` (not `hs_speed`) — same issue
  - `amplifier_type`, `preamp_gain_index`, `em_gain` — all use `_index` suffix
  - Wrong key names are silently ignored, causing subtle timing failures

### TAScanConfig — NI DAQ Fields

| Field | Default | Description |
|-------|---------|-------------|
| `nidaq_device` | `"Dev1"` | NI DAQ device name |
| `nidaq_di_channel` | `"port0/line0"` | P0.0 — digital input for phase reader |
| `nidaq_clock_source` | `"/Dev1/PFI0"` | 1 kHz laser sync (phase reader sample clock) |
| `nidaq_clock_rate` | `1000.0` | Clock rate in Hz |
| `nidaq_chopper_sync_source` | `"/Astrella DAQ/PFI12"` | 250 Hz chopper pulse (counter retrigger source) |
| `nidaq_chopper_counter` | `"ctr1"` | NI counter to use for 500 Hz trigger generation |

### Mock Objects (ANDOR_MOCK=1)

| Class | Location | Pattern |
|-------|----------|---------|
| `MockNIDAQChopper500Hz` | `ta/nidaq_trigger.py` | No hardware; has `is_running` property |
| `MockNIDAQChopper2x2Reader` | `ta/nidaq_phase.py` | Returns `[1,1],[0,0],[1,1]…` — matched pairs |
| `MockNIDAQPhaseReader` | `ta/nidaq_phase.py` | Returns alternating `1,0,1,0…` — single-shot pattern |

`_make_chopper_2x2_hardware()` in `ta_panel.py` selects mock vs real objects based on `ANDOR_MOCK` env var.

---

## Architecture

### Singleton Pattern
- `HardwareManager` — Single instance managing camera/spectrograph
- `EventBus` — Pub/sub for inter-widget communication
- Access via `.instance()` class method

### Signal Flow
```
Hardware → HardwareSignals → Widgets
                ↓
            EventBus → Cross-widget updates
```

### Key Classes

| Class | Location | Purpose |
|-------|----------|---------|
| `HardwareManager` | `core/hardware_manager.py` | Singleton managing hardware lifecycle |
| `SpectrumPlotWidget` | `widgets/display/spectrum_plot.py` | Multi-trace spectrum plot |
| `TraceListWidget` | `widgets/display/trace_list.py` | Trace visibility management |
| `ExperimentQueueRunner` | `core/experiment_queue.py` | Sequential procedure execution |
| `SequencerAdapter` | `core/sequencer_adapter.py` | PyMeasure SequencerWidget integration |
| `DynamicInputsWidget` | `widgets/inputs/dynamic_inputs.py` | Parameter input form |
| `RealtimeWindow` | `windows/realtime_window.py` | Continuous live acquisition window |
| `DataSettingsWidget` | `widgets/hardware/data_settings.py` | Save directory and metadata settings |
| `TransientAbsorptionEngine` | `ta/engine.py` | TA scan loop in QThread with pause/abort |
| `TAWindowPanel` | `windows/ta_panel.py` | Composite TA panel; wires engine + NI DAQ hardware |
| `NIDAQChopper500Hz` | `ta/nidaq_trigger.py` | 500 Hz camera trigger via NI DAQ Counter 1 |
| `NIDAQPhaseReader` | `ta/nidaq_phase.py` | Chopper phase tags from P0.0 per laser shot |

### Procedures
PyMeasure procedures in `src/andor_qt/procedures/`:
- `SpectrumProcedure` — FVB spectrum acquisition
- `ImageProcedure` — 2D image acquisition

Both use `SharedHardwareMixin` from `procedures/base.py` to share hardware with GUI.

## Testing

### Test Structure
```
tests/
├── conftest.py          # Global fixtures, mock SDK setup
├── qt/
│   ├── conftest.py      # Qt fixtures (qt_app, hardware_manager, wait_for)
│   └── test_*.py        # Widget and integration tests
├── procedures/          # Procedure tests
└── e2e/                 # End-to-end workflow tests
```

### Key Fixtures
- `qt_app` — QApplication instance (module scope)
- `hardware_manager` — Fresh HardwareManager with mock SDK
- `wait_for` — Polling helper for async operations
- `reset_hardware_manager` — Resets singleton between tests

### Qt Signal Testing
Signals from background threads need event loop processing:
```python
def wait_for_qt(condition_fn, timeout=15.0):
    app = QApplication.instance()
    start = time.time()
    while time.time() - start < timeout:
        if app:
            app.processEvents()
        if condition_fn():
            return True
        time.sleep(0.05)
    return False
```

## Common Patterns

### Adding a New Widget
1. Create widget in appropriate `widgets/` subdirectory
2. Export from `__init__.py`
3. Add to `main_window.py` layout
4. Connect signals in `_connect_signals()`
5. Write tests in `tests/qt/`

### Adding a New Procedure
1. Create procedure class inheriting from `Procedure` and `SharedHardwareMixin`
2. Define parameters as class attributes using `Parameter()`
3. Implement `startup()`, `execute()`, `shutdown()`
4. Inject hardware via `HardwareManager.inject_into_procedure()`

### Thread Safety
- Use Qt signals for cross-thread communication
- `AcquisitionSignals` class in main_window provides thread-safe signals
- Never access Qt widgets from background threads

## Recent Features (2024)

### Spectrum Overlay (Commits 17-19)
- `SpectrumPlotWidget.add_trace()` — Add overlay trace
- `TraceListWidget` — Manage trace visibility
- Up to 20 traces with automatic color cycling

### PyMeasure Sequencer (Commits 20-22)
- `ExperimentQueueRunner` — Background queue execution
- `SequencerAdapter` — Bridges SequencerWidget to our queue
- QTabWidget with Single/Sequence tabs in left panel

## Instrument Driver Patterns

### Creating New Instruments

Follow PyMeasure's Instrument pattern:
```python
from pymeasure.instruments import Instrument

class MyInstrument(Instrument):
    """Docstring describing the instrument."""

    # Use property creators instead of getter/setter methods
    voltage = Instrument.control(
        "VOLT?", "VOLT %g",
        """Control output voltage in V (float from 0 to 10).""",
        validator=strict_range,
        values=[0, 10],
    )

    # Read-only properties use measurement()
    status = Instrument.measurement(
        "STATUS?",
        """Measure the device status (str, read-only).""",
    )

    # Write-only properties use setting()
    reset = Instrument.setting(
        "*RST",
        """Set to True to reset the device.""",
    )
```

### Validators

- `strict_range` — Raises ValueError if out of range
- `truncated_range` — Clamps value to range silently
- `strict_discrete_set` — Raises if not in allowed set
- `truncated_discrete_set` — Rounds to nearest allowed value

### Mock Instruments

For testing without hardware:
- Inherit from base instrument class
- Override adapter with mock responses
- Use `ANDOR_MOCK=1` environment variable
- Mock implementations in `src/andor_pymeasure/instruments/`

## Non-Obvious Conventions

### Signal Parameter Order
When signals pass multiple objects, order matters:
```python
# Correct order for spectrum signals
spectrum_ready = Signal(object, object, dict)  # wavelengths, intensities, params
image_ready = Signal(object, object, dict)     # image, wavelengths, params
```

### Hardware Manager Singleton
Always use `.instance()`, never construct directly:
```python
# Correct
hw = HardwareManager.instance()

# Wrong - creates orphan instance
hw = HardwareManager()
```

### Qt Thread Safety
Never access widgets from background threads. Use signals:
```python
# In background thread - emit signal
self._acq_signals.spectrum_ready.emit(wavelengths, data, params)

# In main thread - slot handles update
@Slot(object, object, dict)
def _on_spectrum_ready(self, wavelengths, data, params):
    self._plot.add_trace(wavelengths, data)  # Safe - main thread
```

### Procedure Parameter Injection
Procedures get shared hardware via mixin, not constructor:
```python
class SpectrumProcedure(SharedHardwareMixin, Procedure):
    def startup(self):
        self._init_hardware()  # Gets shared instances from HardwareManager
```

## Troubleshooting

### "Hardware not initialized"
- Check SDK path in `hardware_manager.py`
- Verify DLLs are present
- Try mock mode: `--mock`

### Tests timeout waiting for signals
- Use `wait_for_qt()` instead of `wait_for()` for Qt signals
- Ensure `QApplication.processEvents()` is called in wait loop

### Camera won't cool
- Check cooler is enabled: `camera.set_cooler(True)`
- Verify temperature target: `camera.set_temperature(-60)`
- Monitor via `temperature_changed` signal
