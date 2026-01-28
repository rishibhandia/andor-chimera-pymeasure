"""PyMeasure demo procedure.

This demo verifies PyMeasure installation and demonstrates:
- Parameter definition in GUI
- Live plotting during acquisition
- Queue functionality
- Abort capability
- Separate hardware controls (cooler) from acquisition parameters

Run with: uv run python examples/pymeasure_demo.py
"""

import logging
import time

import numpy as np
from pymeasure.display.Qt import QtCore, QtWidgets
from pymeasure.display.windows import ManagedWindow
from pymeasure.experiment import (
    BooleanParameter,
    FloatParameter,
    IntegerParameter,
    ListParameter,
    Procedure,
)

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


# Global simulated hardware state (in real app, this would be the actual hardware)
class SimulatedHardware:
    """Simulated hardware state for testing."""

    def __init__(self):
        self.cooler_on = False
        self.target_temperature = -70
        self.current_temperature = 20.0
        self.temperature_status = "OFF"

    def update_temperature(self):
        """Simulate temperature changes."""
        if self.cooler_on:
            if self.current_temperature > self.target_temperature:
                self.current_temperature -= 2.0
                self.current_temperature = max(self.current_temperature, self.target_temperature)
                self.temperature_status = "COOLING"
            elif abs(self.current_temperature - self.target_temperature) < 1:
                self.temperature_status = "STABILIZED"
            else:
                self.temperature_status = "AT_TARGET"
        else:
            if self.current_temperature < 20:
                self.current_temperature += 1.0
                self.current_temperature = min(self.current_temperature, 20)
                self.temperature_status = "WARMING"
            else:
                self.temperature_status = "OFF"


# Global hardware instance
hardware = SimulatedHardware()


class DemoProcedure(Procedure):
    """Test procedure that simulates spectrum acquisition (no hardware).

    Note: Cooler control is NOT a procedure parameter - it's controlled
    separately via the hardware panel. The procedure just reads the
    current hardware state.
    """

    # Acquisition parameters
    exposure_time = FloatParameter(
        "Exposure Time",
        units="s",
        default=0.1,
        minimum=0.001,
        maximum=600.0,
    )
    acquisition_mode = ListParameter(
        "Acquisition Mode",
        choices=["Single Scan", "Accumulate"],
        default="Single Scan",
    )
    num_accumulations = IntegerParameter(
        "Accumulations",
        default=1,
        minimum=1,
        maximum=1000,
    )

    # Read mode
    read_mode = ListParameter(
        "Read Mode",
        choices=["FVB (Spectrum)", "Image (2D)"],
        default="FVB (Spectrum)",
    )
    hbin = IntegerParameter(
        "H Binning",
        default=1,
        minimum=1,
        maximum=16,
    )
    vbin = IntegerParameter(
        "V Binning",
        default=1,
        minimum=1,
        maximum=16,
    )

    # Spectrograph parameters
    grating = IntegerParameter(
        "Grating",
        default=1,
        minimum=1,
        maximum=3,
    )
    center_wavelength = FloatParameter(
        "Center Wavelength",
        units="nm",
        default=500.0,
        minimum=200.0,
        maximum=1100.0,
    )

    # Simulation parameter (not for real hardware)
    noise_level = FloatParameter(
        "Noise Level",
        units="%",
        default=5.0,
        minimum=0.0,
        maximum=100.0,
    )

    DATA_COLUMNS = ["Wavelength", "Intensity"]

    def startup(self):
        """Called once at start."""
        log.info("=== Test Acquisition Starting ===")
        log.info(f"Exposure: {self.exposure_time}s")
        log.info(f"Mode: {self.acquisition_mode}")
        log.info(f"Read Mode: {self.read_mode}")
        log.info(f"Grating: {self.grating}")
        log.info(f"Center wavelength: {self.center_wavelength}nm")
        log.info(f"Current temp: {hardware.current_temperature:.1f}C ({hardware.temperature_status})")

    def execute(self):
        """Main measurement loop - generates fake spectrum."""
        # Check if in FVB mode - ignore vbin
        is_fvb = "FVB" in self.read_mode
        effective_hbin = self.hbin
        effective_vbin = 1 if is_fvb else self.vbin

        # Simulate 1024 pixels (typical CCD)
        num_pixels = 1024 // effective_hbin

        # Calculate wavelength range
        dispersion = 100 / self.grating
        wl_start = self.center_wavelength - dispersion / 2
        wl_end = self.center_wavelength + dispersion / 2
        wavelengths = np.linspace(wl_start, wl_end, num_pixels)

        log.info(f"Wavelength range: {wl_start:.1f} - {wl_end:.1f} nm")
        log.info(f"Simulating {num_pixels} pixels (hbin={effective_hbin})")

        # Generate spectrum with peaks
        base_intensity = 100
        spectrum = np.ones(num_pixels) * base_intensity

        peak_positions = [
            self.center_wavelength - 30,
            self.center_wavelength,
            self.center_wavelength + 20,
        ]
        peak_widths = [5, 8, 3]
        peak_heights = [500, 800, 300]

        for pos, width, height in zip(peak_positions, peak_widths, peak_heights):
            if wl_start < pos < wl_end:
                peak = height * np.exp(-((wavelengths - pos) ** 2) / (2 * width**2))
                spectrum += peak

        # Simulate acquisition
        total_acquisitions = self.num_accumulations if self.acquisition_mode == "Accumulate" else 1
        accumulated = np.zeros(num_pixels)

        for acq_num in range(total_acquisitions):
            if self.should_stop():
                log.warning("Acquisition aborted")
                return

            # Add noise
            noise = np.random.normal(0, self.noise_level, num_pixels)
            this_spectrum = spectrum + noise

            # Dark noise depends on temperature
            dark_noise = (hardware.current_temperature + 100) / 100 * 5
            this_spectrum += np.random.normal(0, dark_noise, num_pixels)

            accumulated += this_spectrum

            # Simulate exposure time
            steps = 10
            for i in range(steps):
                if self.should_stop():
                    return
                time.sleep(self.exposure_time / steps)

            progress = 100 * (acq_num + 1) / total_acquisitions
            self.emit("progress", progress)

        final_spectrum = accumulated / total_acquisitions

        for wl, intensity in zip(wavelengths, final_spectrum):
            self.emit("results", {"Wavelength": wl, "Intensity": max(0, intensity)})

        log.info("Acquisition complete")

    def shutdown(self):
        """Cleanup."""
        log.info("=== Test Acquisition Finished ===")


class HardwareControlPanel(QtWidgets.QGroupBox):
    """Panel for immediate hardware controls (not queued parameters)."""

    def __init__(self, parent=None):
        super().__init__("Hardware Controls", parent)
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Temperature section
        temp_group = QtWidgets.QGroupBox("Temperature")
        temp_layout = QtWidgets.QGridLayout(temp_group)

        # Cooler checkbox
        self._cooler_checkbox = QtWidgets.QCheckBox("Cooler ON")
        self._cooler_checkbox.stateChanged.connect(self._on_cooler_changed)
        temp_layout.addWidget(self._cooler_checkbox, 0, 0)

        # Target temperature
        temp_layout.addWidget(QtWidgets.QLabel("Target:"), 0, 1)
        self._target_spin = QtWidgets.QSpinBox()
        self._target_spin.setRange(-100, 20)
        self._target_spin.setValue(-70)
        self._target_spin.setSuffix(" °C")
        self._target_spin.valueChanged.connect(self._on_target_changed)
        temp_layout.addWidget(self._target_spin, 0, 2)

        # Current temperature display
        temp_layout.addWidget(QtWidgets.QLabel("Current:"), 1, 0)
        self._temp_label = QtWidgets.QLabel("20.0 °C")
        self._temp_label.setStyleSheet("font-weight: bold;")
        temp_layout.addWidget(self._temp_label, 1, 1)

        # Status
        self._status_label = QtWidgets.QLabel("OFF")
        self._status_label.setStyleSheet("color: gray;")
        temp_layout.addWidget(self._status_label, 1, 2)

        layout.addWidget(temp_group)

    def _setup_timer(self):
        """Setup timer for temperature updates."""
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._update_display)
        self._timer.start(1000)  # Update every second

    def _on_cooler_changed(self, state):
        """Handle cooler checkbox change - immediate action."""
        hardware.cooler_on = bool(state)
        hardware.target_temperature = self._target_spin.value()
        log.info(f"Cooler {'ON' if hardware.cooler_on else 'OFF'}, target: {hardware.target_temperature}°C")

    def _on_target_changed(self, value):
        """Handle target temperature change."""
        hardware.target_temperature = value
        if hardware.cooler_on:
            log.info(f"Target temperature changed to {value}°C")

    def _update_display(self):
        """Update temperature display."""
        hardware.update_temperature()

        self._temp_label.setText(f"{hardware.current_temperature:.1f} °C")

        status = hardware.temperature_status
        self._status_label.setText(status)

        # Color based on status
        if status == "STABILIZED":
            self._status_label.setStyleSheet("color: green; font-weight: bold;")
        elif status in ("COOLING", "WARMING"):
            self._status_label.setStyleSheet("color: orange;")
        else:
            self._status_label.setStyleSheet("color: gray;")


class CustomInputsWidget(QtWidgets.QWidget):
    """Custom inputs widget that handles conditional visibility."""

    def __init__(self, procedure_class, inputs, parent=None):
        super().__init__(parent)
        self._procedure_class = procedure_class
        self._input_names = inputs
        self._widgets = {}
        self._labels = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QFormLayout(self)

        for name in self._input_names:
            param = getattr(self._procedure_class, name)
            label = param.name if hasattr(param, 'name') else name

            # Create appropriate widget based on parameter type
            if isinstance(param, ListParameter):
                widget = QtWidgets.QComboBox()
                widget.addItems(param.choices)
                if param.default in param.choices:
                    widget.setCurrentText(param.default)
            elif isinstance(param, BooleanParameter):
                widget = QtWidgets.QCheckBox()
                widget.setChecked(param.default)
                label = ""  # Checkbox has its own label
            elif isinstance(param, IntegerParameter):
                widget = QtWidgets.QSpinBox()
                widget.setRange(param.minimum or 0, param.maximum or 9999)
                widget.setValue(param.default)
            elif isinstance(param, FloatParameter):
                widget = QtWidgets.QDoubleSpinBox()
                widget.setRange(param.minimum or 0, param.maximum or 9999)
                widget.setValue(param.default)
                widget.setDecimals(3)
                if hasattr(param, 'units') and param.units:
                    widget.setSuffix(f" {param.units}")
            else:
                widget = QtWidgets.QLineEdit(str(param.default))

            # Add units suffix for spin boxes
            if isinstance(param, (IntegerParameter, FloatParameter)):
                if hasattr(param, 'units') and param.units:
                    widget.setSuffix(f" {param.units}")

            # Create label widget
            label_text = param.name if hasattr(param, 'name') else name.replace('_', ' ').title()
            label_widget = QtWidgets.QLabel(label_text + ":")

            self._widgets[name] = widget
            self._labels[name] = label_widget

            if isinstance(param, BooleanParameter):
                # For checkboxes, put the label in the checkbox text
                widget.setText(label_text)
                layout.addRow("", widget)
            else:
                layout.addRow(label_widget, widget)

        # Connect read_mode to show/hide vbin
        if 'read_mode' in self._widgets and 'vbin' in self._widgets:
            self._widgets['read_mode'].currentTextChanged.connect(self._on_read_mode_changed)
            # Set initial state
            self._on_read_mode_changed(self._widgets['read_mode'].currentText())

    def _on_read_mode_changed(self, mode_text):
        """Show/hide V Binning based on read mode."""
        is_image_mode = "Image" in mode_text
        self._widgets['vbin'].setVisible(is_image_mode)
        self._labels['vbin'].setVisible(is_image_mode)

    def get_procedure(self):
        """Create a procedure instance with current parameter values."""
        proc = self._procedure_class()

        for name, widget in self._widgets.items():
            if isinstance(widget, QtWidgets.QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QtWidgets.QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                value = widget.value()
            elif isinstance(widget, QtWidgets.QLineEdit):
                value = widget.text()
            else:
                continue

            setattr(proc, name, value)

        return proc


class DemoWindow(ManagedWindow):
    """Test window with hardware controls and conditional parameter visibility."""

    def __init__(self):
        # Don't include cooler parameters - they're in the hardware panel
        super().__init__(
            procedure_class=DemoProcedure,
            inputs=[
                "exposure_time",
                "acquisition_mode",
                "num_accumulations",
                "read_mode",
                "hbin",
                "vbin",
                "grating",
                "center_wavelength",
                "noise_level",
            ],
            displays=[
                "exposure_time",
                "grating",
                "center_wavelength",
            ],
            x_axis="Wavelength",
            y_axis="Intensity",
        )
        self.setWindowTitle("Andor Spectrometer Test (No Hardware)")

        # Add hardware control panel
        self._add_hardware_panel()

        # Setup conditional visibility for vbin
        self._setup_vbin_visibility()

    def _add_hardware_panel(self):
        """Add the hardware control panel to the window."""
        # Create hardware panel
        self._hardware_panel = HardwareControlPanel()

        # Find the inputs dock and add hardware panel above it
        # The inputs are in a dock widget, we'll add our panel to the same area
        dock = QtWidgets.QDockWidget("Hardware", self)
        dock.setWidget(self._hardware_panel)
        dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _setup_vbin_visibility(self):
        """Setup V Binning visibility based on read mode."""
        try:
            # Find the inputs widget and its layout
            inputs_dock = None
            for dock in self.findChildren(QtWidgets.QDockWidget):
                if dock.windowTitle() == "Inputs":
                    inputs_dock = dock
                    break

            if not inputs_dock:
                return

            inputs_widget = inputs_dock.widget()
            if not inputs_widget:
                return

            # Find the form layout
            layout = None
            for child in inputs_widget.findChildren(QtWidgets.QFormLayout):
                layout = child
                break

            if not layout:
                # Try QGridLayout
                for child in inputs_widget.findChildren(QtWidgets.QGridLayout):
                    layout = child
                    break

            if not layout:
                return

            # Find read_mode combobox and vbin widgets
            self._read_mode_combo = None
            self._vbin_widget = None
            self._vbin_label = None

            # Search through all comboboxes to find read_mode
            for combo in inputs_widget.findChildren(QtWidgets.QComboBox):
                items = [combo.itemText(i) for i in range(combo.count())]
                if "FVB (Spectrum)" in items:
                    self._read_mode_combo = combo
                    break

            # Search for vbin by finding spinbox after "V Binning" label
            for label in inputs_widget.findChildren(QtWidgets.QLabel):
                if "V Bin" in label.text():
                    self._vbin_label = label
                    # Find the associated spinbox
                    # In a form layout, it should be the next widget
                    if isinstance(layout, QtWidgets.QFormLayout):
                        for row in range(layout.rowCount()):
                            label_item = layout.itemAt(row, QtWidgets.QFormLayout.ItemRole.LabelRole)
                            field_item = layout.itemAt(row, QtWidgets.QFormLayout.ItemRole.FieldRole)
                            if label_item and label_item.widget() == label:
                                if field_item:
                                    self._vbin_widget = field_item.widget()
                                break
                    break

            # Connect signal
            if self._read_mode_combo:
                self._read_mode_combo.currentTextChanged.connect(self._on_read_mode_changed)
                # Set initial state
                self._on_read_mode_changed(self._read_mode_combo.currentText())

        except Exception as e:
            log.warning(f"Could not setup vbin visibility: {e}")

    def _on_read_mode_changed(self, mode_text):
        """Show/hide V Binning based on read mode."""
        is_image_mode = "Image" in str(mode_text)

        if self._vbin_widget:
            self._vbin_widget.setVisible(is_image_mode)
            self._vbin_widget.setEnabled(is_image_mode)

        if self._vbin_label:
            self._vbin_label.setVisible(is_image_mode)


def main():
    """Run the test application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    app = QtWidgets.QApplication([])
    window = DemoWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
