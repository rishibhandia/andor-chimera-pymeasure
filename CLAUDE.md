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

### Camera Shutdown
Always warm up before shutdown to prevent thermal damage:
```python
camera.set_cooler(False)  # Turn off cooler
# Wait for temp > -20°C before calling shutdown()
```
The GUI handles this automatically via `ShutdownDialog`.

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
