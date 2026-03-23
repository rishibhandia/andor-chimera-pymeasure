# CLAUDE.md

Project-specific guidance for Claude Code when working on andor-chimera-pymeasure.

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

- **Line length**: 100 characters
- **Naming**: lowercase_with_underscores for functions/variables, CamelCase for classes
- **Imports**: Use absolute imports, sorted by ruff
- **Type hints**: Encouraged, use `from __future__ import annotations`
- **Docstrings**: Google style, start with imperative verb

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
