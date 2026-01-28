"""Main application window for Andor Spectrometer using PyMeasure.

This module provides the main GUI application that allows users to run
different experiment procedures including:
- Single spectrum acquisition (FVB mode)
- 2D image acquisition
- Wavelength scans
- Pump-probe experiments (with delay stage)

Run with: uv run python -m andor_pymeasure.app
"""

import logging
import sys
from typing import Dict, Type

from pymeasure.display.Qt import QtCore, QtWidgets
from pymeasure.display.windows import ManagedWindow
from pymeasure.experiment import Procedure

from andor_pymeasure.procedures.pump_probe import (
    PumpProbeImageProcedure,
    PumpProbeProcedure,
)
from andor_pymeasure.procedures.spectrum import ImageProcedure, SpectrumProcedure
from andor_pymeasure.procedures.wavelength_scan import (
    WavelengthImageScanProcedure,
    WavelengthScanProcedure,
)

log = logging.getLogger(__name__)


class SpectrumWindow(ManagedWindow):
    """Window for single spectrum (FVB) acquisition."""

    def __init__(self):
        super().__init__(
            procedure_class=SpectrumProcedure,
            inputs=[
                "exposure_time",
                "center_wavelength",
                "grating",
                "num_accumulations",
                "cooler_enabled",
                "target_temperature",
            ],
            displays=["exposure_time", "center_wavelength", "grating"],
            x_axis="Wavelength",
            y_axis="Intensity",
        )
        self.setWindowTitle("Andor Spectrometer - Spectrum (FVB)")


class ImageWindow(ManagedWindow):
    """Window for 2D image acquisition."""

    def __init__(self):
        super().__init__(
            procedure_class=ImageProcedure,
            inputs=[
                "exposure_time",
                "center_wavelength",
                "grating",
                "hbin",
                "vbin",
                "cooler_enabled",
                "target_temperature",
            ],
            displays=["exposure_time", "center_wavelength", "hbin", "vbin"],
            x_axis="Wavelength",
            y_axis="Intensity",
        )
        self.setWindowTitle("Andor Spectrometer - 2D Image")


class WavelengthScanWindow(ManagedWindow):
    """Window for wavelength scan (FVB) acquisition."""

    def __init__(self):
        super().__init__(
            procedure_class=WavelengthScanProcedure,
            inputs=[
                "wavelength_start",
                "wavelength_end",
                "wavelength_step",
                "exposure_time",
                "grating",
                "cooler_enabled",
                "target_temperature",
            ],
            displays=["wavelength_start", "wavelength_end", "exposure_time"],
            x_axis="Pixel_Wavelength",
            y_axis="Intensity",
        )
        self.setWindowTitle("Andor Spectrometer - Wavelength Scan")


class WavelengthImageScanWindow(ManagedWindow):
    """Window for wavelength scan with 2D image acquisition."""

    def __init__(self):
        super().__init__(
            procedure_class=WavelengthImageScanProcedure,
            inputs=[
                "wavelength_start",
                "wavelength_end",
                "wavelength_step",
                "exposure_time",
                "grating",
                "hbin",
                "vbin",
                "cooler_enabled",
                "target_temperature",
            ],
            displays=["wavelength_start", "wavelength_end", "exposure_time"],
            x_axis="Pixel_Wavelength",
            y_axis="Intensity",
        )
        self.setWindowTitle("Andor Spectrometer - Wavelength Image Scan")


class PumpProbeWindow(ManagedWindow):
    """Window for pump-probe spectrum (FVB) acquisition."""

    def __init__(self):
        super().__init__(
            procedure_class=PumpProbeProcedure,
            inputs=[
                "delay_start",
                "delay_end",
                "delay_step",
                "center_wavelength",
                "grating",
                "exposure_time",
                "num_accumulations",
                "cooler_enabled",
                "target_temperature",
                "use_mock_stage",
            ],
            displays=["delay_start", "delay_end", "exposure_time"],
            x_axis="Wavelength",
            y_axis="Intensity",
        )
        self.setWindowTitle("Andor Spectrometer - Pump-Probe")


class PumpProbeImageWindow(ManagedWindow):
    """Window for pump-probe 2D image acquisition."""

    def __init__(self):
        super().__init__(
            procedure_class=PumpProbeImageProcedure,
            inputs=[
                "delay_start",
                "delay_end",
                "delay_step",
                "center_wavelength",
                "grating",
                "exposure_time",
                "hbin",
                "vbin",
                "cooler_enabled",
                "target_temperature",
                "use_mock_stage",
            ],
            displays=["delay_start", "delay_end", "exposure_time"],
            x_axis="Wavelength",
            y_axis="Intensity",
        )
        self.setWindowTitle("Andor Spectrometer - Pump-Probe Image")


class MainLauncher(QtWidgets.QMainWindow):
    """Main launcher window to select experiment type."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Andor Spectrometer - PyMeasure")
        self.setMinimumSize(400, 300)

        # Track open windows
        self._windows: Dict[str, ManagedWindow] = {}

        # Create central widget
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)

        # Title
        title = QtWidgets.QLabel("Andor Spectrometer Control")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 20px;")
        layout.addWidget(title)

        # Description
        desc = QtWidgets.QLabel(
            "Select an experiment type to open the corresponding window.\n"
            "Each window allows you to queue and run experiments."
        )
        desc.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(20)

        # Buttons for each experiment type
        self._add_button(
            layout,
            "Spectrum (FVB)",
            "Acquire a single 1D spectrum using Full Vertical Binning",
            self._open_spectrum,
        )

        self._add_button(
            layout,
            "2D Image",
            "Acquire a 2D image from the CCD with wavelength calibration",
            self._open_image,
        )

        self._add_button(
            layout,
            "Wavelength Scan",
            "Scan across wavelengths, acquiring a spectrum at each position",
            self._open_wavelength_scan,
        )

        self._add_button(
            layout,
            "Wavelength Image Scan",
            "Scan across wavelengths, acquiring a 2D image at each position",
            self._open_wavelength_image_scan,
        )

        # Separator
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # Pump-probe section label
        pump_probe_label = QtWidgets.QLabel("Pump-Probe Experiments")
        pump_probe_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(pump_probe_label)

        self._add_button(
            layout,
            "Pump-Probe Spectrum",
            "Scan delay stage, acquire spectrum (FVB) at each delay",
            self._open_pump_probe,
        )

        self._add_button(
            layout,
            "Pump-Probe Image",
            "Scan delay stage, acquire 2D image at each delay",
            self._open_pump_probe_image,
        )

        layout.addStretch()

        # Status
        self._status = QtWidgets.QLabel("Ready")
        self._status.setStyleSheet("color: gray; margin: 10px;")
        layout.addWidget(self._status)

    def _add_button(
        self,
        layout: QtWidgets.QVBoxLayout,
        text: str,
        tooltip: str,
        callback,
    ) -> None:
        """Add a button to the layout."""
        btn = QtWidgets.QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setMinimumHeight(40)
        btn.clicked.connect(callback)
        layout.addWidget(btn)

    def _open_window(self, name: str, window_class: Type[ManagedWindow]) -> None:
        """Open or focus a window."""
        if name in self._windows:
            # Window already exists - bring to front
            window = self._windows[name]
            window.raise_()
            window.activateWindow()
        else:
            # Create new window
            window = window_class()
            window.show()
            self._windows[name] = window
            self._status.setText(f"Opened: {name}")

    def _open_spectrum(self) -> None:
        self._open_window("spectrum", SpectrumWindow)

    def _open_image(self) -> None:
        self._open_window("image", ImageWindow)

    def _open_wavelength_scan(self) -> None:
        self._open_window("wavelength_scan", WavelengthScanWindow)

    def _open_wavelength_image_scan(self) -> None:
        self._open_window("wavelength_image_scan", WavelengthImageScanWindow)

    def _open_pump_probe(self) -> None:
        self._open_window("pump_probe", PumpProbeWindow)

    def _open_pump_probe_image(self) -> None:
        self._open_window("pump_probe_image", PumpProbeImageWindow)


def main():
    """Run the main application."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    app = QtWidgets.QApplication(sys.argv)
    launcher = MainLauncher()
    launcher.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
