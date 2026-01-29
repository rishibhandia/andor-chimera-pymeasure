# CLAUDE.md

Project-specific guidance for Claude Code when working on andor-chimera-pymeasure.

## Project Overview

Qt/PySide6 GUI and PyMeasure integration for Andor CCD spectrometer control. Two packages:
- **andor_qt** — Main GUI application
- **andor_pymeasure** — PyMeasure procedures and instrument drivers

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
