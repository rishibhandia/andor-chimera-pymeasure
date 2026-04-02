# Andor Chimera PyMeasure

Qt/PySide6 GUI and PyMeasure integration for Andor CCD spectrometer control with transient absorption (TA) pump-probe measurement capabilities.

## Features

### Spectrum Acquisition
- **FVB (Full Vertical Binning)** and **Image** acquisition modes
- Real-time spectrum display with wavelength calibration
- Configurable exposure time, accumulations, and binning
- Up to 20 simultaneous spectrum overlays with individual visibility toggles

### Transient Absorption (TA) Module
- **chopper_2x2** acquisition: hardware-synchronized pump-probe with NI DAQ phase tagging
- **shot_to_shot** mode: 1 kHz single-shot crop-mode acquisition
- **boxcar** mode: software alternation (no NI DAQ required)
- **static_onoff** mode: two-pass scan with user-controlled pump blocking
- Live delta-OD spectrum, kinetic trace, and 2D heatmap display
- HDF5 data files with per-point pump/ref/std saving
- Monitor mode for real-time signal optimization before scanning
- Dark frame acquisition and subtraction
- Configurable delay stage positions in micrometres (Linear, Log, Manual tabs)

### Motion Control
- **Newport ESP302** delay stage (RS-232 or TCP socket)
- **OptoSigma GSC-02C** rotation stage (RS-232)
- Dual readout: position in mm and ps simultaneously
- Jog buttons with software limit enforcement

### PyMeasure Sequencer Integration
- Queue parameter sweeps using PyMeasure's SequencerWidget
- Sequence over exposure time, wavelength, grating, and more
- Background execution with progress tracking

### Hardware Control
- Spectrograph grating and wavelength control
- Camera temperature management with automatic warmup on exit
- NI DAQ PCIe-6353 integration for chopper phase reading and trigger generation

## Requirements

- **Python 3.11+**
- **Andor SDK** at `C:\Program Files\Andor SDK` (Windows)
- **NI DAQ** PCIe-6353 with nidaqmx driver (for TA chopper modes)
- Dependencies managed via `pyproject.toml` (installed automatically by uv)

## Installation

```bash
git clone <repo-url>
cd andor-chimera-pymeasure
uv pip install -e ".[dev]"
```

## Quick Start

### Mock Mode (no hardware)

```bash
uv run python -m andor_qt --mock
```

### Real Hardware

```bash
uv run python -m andor_qt
```

## Hardware Wiring (BNC-2110)

For chopper_2x2 TA acquisition, the NI PCIe-6353 requires:

| BNC-2110 Connector | NI Terminal | Signal |
|---------------------|-------------|--------|
| (dedicated BNC) | PFI0 | 1 kHz laser sync (phase reader sample clock) |
| (dedicated BNC) | PFI12 | SDG 500 Hz (camera trigger + chopper REF IN) |
| User 1 BNC | PFI13 | Camera Fire output (phase reader start trigger) |
| User 2 BNC | P0.0 | Chopper REF OUT (pump phase tags) |

The Camera Fire output on PFI13 ensures deterministic tag-to-frame alignment across camera restarts.

## Testing

```bash
# Run all tests (mock mode, no hardware needed)
uv run pytest

# Run hardware integration tests (requires real camera + NI DAQ)
uv run pytest tests/integration/ --hardware -v
```

The test suite includes 1100+ tests covering widgets, procedures, acquisition logic, and hardware integration.

## Continuous Integration

GitHub Actions runs the test suite automatically on every push and pull request to `master`. The workflow is defined in `.github/workflows/test.yml`.

### What CI does

1. **Lint** — Runs `ruff check src/` (non-blocking; warnings only)
2. **Test** — Runs `pytest` on all non-hardware tests (`tests/integration/` is excluded)
3. **Matrix** — Tests against Python 3.11 and 3.13

### How it works without hardware

The CI environment has no Andor SDK, NI DAQ, or camera hardware. Tests run with `ANDOR_MOCK=1` which activates mock implementations for all hardware (see `tests/conftest.py`). The local Andor SDK Python packages (`pyandorsdk2`, `pyandorspectrograph`) are `file://` dependencies that don't exist in CI, so the workflow installs dependencies individually and installs the project with `--no-deps`.

PySide6 requires system libraries on headless Linux. The workflow installs `libegl1`, `libopengl0`, and `libxkbcommon0`, and sets `QT_QPA_PLATFORM=offscreen` to run Qt without a display server.

### Local ruff hook

A post-edit hook in `.claude/settings.json` runs `ruff check --fix` automatically after every Python file edit in Claude Code, keeping the codebase lint-clean as changes are made.

## Project Structure

```
src/
├── andor_pymeasure/              # PyMeasure instrument drivers
│   └── instruments/              # Camera, spectrograph, delay stage, rotation stage
├── andor_qt/                     # Qt GUI application
│   ├── core/                     # HardwareManager, EventBus, experiment queue
│   ├── ta/                       # Transient absorption module
│   │   ├── acquisition.py        # AcquisitionSession + frame processing
│   │   ├── engine.py             # Scan engine (QThread)
│   │   ├── monitor_engine.py     # Monitor engine (continuous at one position)
│   │   ├── nidaq_phase.py        # NI DAQ phase reader
│   │   ├── nidaq_trigger.py      # NI DAQ trigger generator
│   │   ├── scan_config.py        # Scan parameters dataclass
│   │   └── hdf5_writer.py        # HDF5 data output
│   ├── widgets/                  # UI components (display, hardware, TA config)
│   └── windows/                  # Main window, TA panel, realtime window
tests/
├── ta/                           # TA module unit tests
├── qt/                           # Qt widget tests
├── integration/                  # Hardware integration tests (--hardware flag)
└── conftest.py                   # Mock SDK fixtures
```

## Documentation

- **[User Guide](docs/user_guide.md)** — How to operate the spectrometer and run TA scans
- **[CLAUDE.md](CLAUDE.md)** — Developer reference with architecture, hardware notes, and coding conventions
- **[ESP302-API-Reference.md](ESP302-API-Reference.md)** — Newport delay stage command reference
- **[GSC02-SGSP-YAW-Reference.md](GSC02-SGSP-YAW-Reference.md)** — OptoSigma rotation stage command reference

## License

See LICENSE file for details.
