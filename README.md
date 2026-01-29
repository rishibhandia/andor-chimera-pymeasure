# Andor Chimera PyMeasure

Qt-based GUI and PyMeasure integration for Andor spectrometer control. This package provides a modern PySide6 interface for acquiring spectra from Andor CCD cameras and spectrographs, with support for automated parameter sweeps via PyMeasure's sequencer.

## Features

### Spectrum Acquisition
- **FVB (Full Vertical Binning)** and **Image** acquisition modes
- Real-time spectrum display with wavelength calibration
- Configurable exposure time, accumulations, and binning

### Spectrum Overlay
- Multiple traces displayed on a single plot
- Individual visibility toggles for each trace
- Color-coded traces with automatic cycling
- Up to 20 simultaneous overlays

### PyMeasure Sequencer Integration
- Queue parameter sweeps using PyMeasure's SequencerWidget
- Sequence over exposure time, wavelength, grating, and more
- CSV, nested lists, or range-based parameter definitions
- Background execution with progress tracking

### Temperature Monitoring
- Color-coded temperature status indicator
- Real-time current and target temperature display
- Status states: Stabilized (green), Cooling (orange), Off (gray)

### Session Management
- Sample ID and operator name fields
- Notes field for experiment documentation
- Auto-save with configurable directory
- Timestamp or counter-based file naming

### Hardware Control
- Spectrograph grating and wavelength control
- Camera temperature management with warmup on exit
- Graceful shutdown with progress dialog

## Requirements

- **Python 3.8+**
- **Andor SDK** (for real hardware operation)
- Dependencies from pyproject.toml:
  - numpy >= 1.20
  - matplotlib >= 3.5
  - pymeasure >= 0.15.0
  - pyqtgraph >= 0.13.3
  - PySide6 >= 6.6.3.1
  - pyyaml >= 6.0

## Installation

### Clone the Repository

```bash
git clone https://github.com/rishibhandia/andor-chimera-pymeasure.git
cd andor-chimera-pymeasure
```

### Install with uv (Recommended)

```bash
uv pip install -e .
```

### Install with pip

```bash
pip install -e .
```

### Install Development Dependencies

```bash
uv pip install -e ".[dev]"
```

## Usage

### Qt GUI (Mock Mode - No Hardware Required)

Test the interface without connected hardware:

```bash
andor-qt --mock
```

Or using the module directly:

```bash
python -m andor_qt --mock
```

### Qt GUI (Real Hardware)

```bash
andor-qt
```

Additional options:
- `--debug` - Enable debug logging
- `--config PATH` - Specify a custom configuration file

### PyMeasure CLI

For command-line operation using PyMeasure procedures:

```bash
andor-pymeasure
```

## Hardware Setup

### Andor SDK Installation

1. **Install the Andor SDK** to `C:\Program Files\Andor SDK` (default Windows location)

2. **Verify DLL access**: The following DLLs must be accessible:
   - `atmcd64d.dll` (camera control)
   - `ShamrockCIF.dll` (spectrograph control)

3. **Connect hardware** via USB:
   - Andor CCD camera (e.g., Newton, iDus)
   - Andor spectrograph (e.g., Shamrock)

4. **Driver installation**: Install Andor drivers from the SDK package

### Environment Variables

- `ANDOR_MOCK=1` - Force mock mode (useful for development)
- `ANDOR_DEBUG=1` - Enable debug logging

### Configuration File

The application looks for configuration at platform-specific locations:
- **Windows**: `%APPDATA%\AndorSpectrometer\config.yaml`
- **macOS**: `~/Library/Application Support/AndorSpectrometer/config.yaml`
- **Linux**: `~/.config/andor-spectrometer/config.yaml`

## Development

### Running Tests

```bash
uv run pytest
```

The test suite includes 349 tests covering:
- Qt widget functionality
- PyMeasure procedures
- Hardware mock implementations
- End-to-end integration tests

### Running Tests with Coverage

```bash
uv run pytest --cov=andor_qt --cov=andor_pymeasure
```

### Code Formatting

```bash
uv run ruff check src/
uv run ruff format src/
```

## Project Structure

```
src/
├── andor_pymeasure/           # PyMeasure-based procedures
│   ├── instruments/           # Instrument drivers
│   │   ├── andor_camera.py    # Camera instrument
│   │   ├── andor_spectrograph.py
│   │   ├── delay_stage.py     # For pump-probe experiments
│   │   └── mock.py            # Mock implementations
│   ├── procedures/            # Experiment procedures
│   │   ├── spectrum.py        # Basic spectrum acquisition
│   │   ├── wavelength_scan.py
│   │   └── pump_probe.py
│   └── app.py                 # CLI entry point
│
├── andor_qt/                  # Qt GUI application
│   ├── core/                  # Core functionality
│   │   ├── config.py          # Configuration management
│   │   ├── event_bus.py       # Inter-widget communication
│   │   ├── experiment_queue.py
│   │   ├── hardware_manager.py
│   │   ├── sequencer_adapter.py  # PyMeasure integration
│   │   └── signals.py
│   ├── widgets/               # UI components
│   │   ├── display/           # Data visualization
│   │   │   ├── spectrum_plot.py   # Multi-trace plot
│   │   │   ├── trace_list.py      # Trace management
│   │   │   ├── image_plot.py
│   │   │   └── results_table.py
│   │   ├── hardware/          # Hardware control panels
│   │   │   ├── spectrograph_control.py
│   │   │   ├── temperature_control.py
│   │   │   ├── temperature_monitor.py
│   │   │   └── data_settings.py
│   │   ├── inputs/            # Parameter inputs
│   │   │   ├── dynamic_inputs.py
│   │   │   ├── acquire_control.py
│   │   │   └── queue_control.py
│   │   └── dialogs/           # Modal dialogs
│   │       ├── shutdown_dialog.py
│   │       └── benchmark_dialog.py
│   ├── windows/               # Main windows
│   │   └── main_window.py
│   ├── procedures/            # Qt-specific procedures
│   │   ├── base.py
│   │   └── spectrum.py
│   └── app.py                 # GUI entry point
│
tests/                         # Test suite (349 tests)
```

## License

See LICENSE file for details.
