"""Dynamic inputs widget with conditional visibility.

This widget provides procedure parameter inputs that show/hide fields
based on the selected read mode (FVB vs Image).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Type

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from pymeasure.experiment import Procedure

log = logging.getLogger(__name__)


class DynamicInputsWidget(QGroupBox):
    """Widget for procedure parameter inputs with conditional visibility.

    Features:
    - Read mode selector (FVB, Image)
    - Exposure time input
    - H Binning (always visible)
    - V Binning (only visible in Image mode)
    - Number of accumulations (only for FVB)

    Signals:
        parameters_changed: Emitted when any parameter changes
        read_mode_changed: Emitted when read mode changes (str)
    """

    parameters_changed = Signal()
    read_mode_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Acquisition Parameters", parent)

        self._setup_ui()
        self._connect_signals()

        # Apply initial visibility
        self._on_read_mode_changed(0)

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(8)

        # Read mode selector
        self._read_mode_combo = QComboBox()
        self._read_mode_combo.addItem("FVB (1D Spectrum)", "fvb")
        self._read_mode_combo.addItem("Image (2D)", "image")
        self._read_mode_combo.setToolTip("Select acquisition mode")
        form.addRow("Read Mode:", self._read_mode_combo)

        # Exposure time
        self._exposure_spin = QDoubleSpinBox()
        self._exposure_spin.setRange(0.001, 600.0)
        self._exposure_spin.setValue(0.1)
        self._exposure_spin.setSuffix(" s")
        self._exposure_spin.setDecimals(3)
        self._exposure_spin.setToolTip("Exposure time in seconds")
        form.addRow("Exposure:", self._exposure_spin)

        # Number of accumulations (FVB only)
        self._accum_spin = QSpinBox()
        self._accum_spin.setRange(1, 1000)
        self._accum_spin.setValue(1)
        self._accum_spin.setToolTip("Number of accumulations (FVB mode only)")
        self._accum_label = QLabel("Accumulations:")
        form.addRow(self._accum_label, self._accum_spin)

        # H Binning (always visible)
        self._hbin_spin = QSpinBox()
        self._hbin_spin.setRange(1, 16)
        self._hbin_spin.setValue(1)
        self._hbin_spin.setToolTip("Horizontal binning factor")
        form.addRow("H Binning:", self._hbin_spin)

        # V Binning (Image only)
        self._vbin_spin = QSpinBox()
        self._vbin_spin.setRange(1, 16)
        self._vbin_spin.setValue(1)
        self._vbin_spin.setToolTip("Vertical binning factor (Image mode only)")
        self._vbin_label = QLabel("V Binning:")
        form.addRow(self._vbin_label, self._vbin_spin)

        layout.addLayout(form)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._read_mode_combo.currentIndexChanged.connect(self._on_read_mode_changed)
        self._exposure_spin.valueChanged.connect(self._emit_parameters_changed)
        self._accum_spin.valueChanged.connect(self._emit_parameters_changed)
        self._hbin_spin.valueChanged.connect(self._emit_parameters_changed)
        self._vbin_spin.valueChanged.connect(self._emit_parameters_changed)

    @Slot(int)
    def _on_read_mode_changed(self, index: int) -> None:
        """Handle read mode change, updating field visibility."""
        mode = self._read_mode_combo.itemData(index)

        if mode == "image":
            # Image mode: show V Binning, hide Accumulations
            self._vbin_label.show()
            self._vbin_spin.show()
            self._accum_label.hide()
            self._accum_spin.hide()
        else:
            # FVB mode: hide V Binning, show Accumulations
            self._vbin_label.hide()
            self._vbin_spin.hide()
            self._accum_label.show()
            self._accum_spin.show()

        self.read_mode_changed.emit(mode)
        self._emit_parameters_changed()

    @Slot()
    def _emit_parameters_changed(self) -> None:
        """Emit parameters_changed signal."""
        self.parameters_changed.emit()

    @property
    def read_mode(self) -> str:
        """Get current read mode ('fvb' or 'image')."""
        return self._read_mode_combo.currentData()

    @property
    def exposure_time(self) -> float:
        """Get exposure time in seconds."""
        return self._exposure_spin.value()

    @exposure_time.setter
    def exposure_time(self, value: float) -> None:
        """Set exposure time."""
        self._exposure_spin.setValue(value)

    @property
    def num_accumulations(self) -> int:
        """Get number of accumulations."""
        return self._accum_spin.value()

    @property
    def hbin(self) -> int:
        """Get horizontal binning."""
        return self._hbin_spin.value()

    @hbin.setter
    def hbin(self, value: int) -> None:
        """Set horizontal binning."""
        self._hbin_spin.setValue(value)

    @property
    def vbin(self) -> int:
        """Get vertical binning."""
        return self._vbin_spin.value()

    @vbin.setter
    def vbin(self, value: int) -> None:
        """Set vertical binning."""
        self._vbin_spin.setValue(value)

    def get_parameters(self) -> Dict[str, any]:
        """Get all current parameters as a dictionary.

        Returns:
            Dictionary of parameter name to value.
        """
        params = {
            "read_mode": self.read_mode,
            "exposure_time": self.exposure_time,
            "hbin": self.hbin,
        }

        if self.read_mode == "fvb":
            params["num_accumulations"] = self.num_accumulations
        else:
            params["vbin"] = self.vbin

        return params

    def create_procedure(
        self,
        center_wavelength: float,
        grating: int,
    ) -> "Procedure":
        """Create a procedure instance with current parameters.

        Args:
            center_wavelength: Center wavelength in nm.
            grating: Grating index.

        Returns:
            Configured procedure instance (SpectrumProcedure or ImageProcedure).
        """
        from andor_qt.procedures import ImageProcedure, SpectrumProcedure

        if self.read_mode == "fvb":
            procedure = SpectrumProcedure()
            procedure.exposure_time = self.exposure_time
            procedure.center_wavelength = center_wavelength
            procedure.grating = grating
            procedure.hbin = self.hbin
            procedure.num_accumulations = self.num_accumulations
        else:
            procedure = ImageProcedure()
            procedure.exposure_time = self.exposure_time
            procedure.center_wavelength = center_wavelength
            procedure.grating = grating
            procedure.hbin = self.hbin
            procedure.vbin = self.vbin

        return procedure
