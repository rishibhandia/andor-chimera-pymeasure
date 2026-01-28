"""Adapter providing ManagedWindow-like interface for SequencerWidget.

PyMeasure's SequencerWidget expects its parent to have procedure_class,
make_procedure(), and queue(procedure=...) methods. This adapter wraps
our widgets and queue runner to provide that interface.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Type

if TYPE_CHECKING:
    from pymeasure.experiment import Procedure

    from andor_qt.core.experiment_queue import ExperimentQueueRunner
    from andor_qt.core.hardware_manager import HardwareManager
    from andor_qt.widgets.inputs import DynamicInputsWidget

log = logging.getLogger(__name__)

# Sequenceable parameters per procedure type
_FVB_INPUTS = [
    "exposure_time", "center_wavelength", "grating",
    "hbin", "num_accumulations",
]
_IMAGE_INPUTS = [
    "exposure_time", "center_wavelength", "grating",
    "hbin", "vbin",
]


class SequencerAdapter:
    """Adapts our app to provide the ManagedWindow-like interface
    that PyMeasure's SequencerWidget expects.

    Attributes:
        procedure_class: The current Procedure class (SpectrumProcedure or ImageProcedure).
        sequenceable_inputs: List of parameter names for the sequencer UI.
    """

    def __init__(
        self,
        inputs_widget: DynamicInputsWidget,
        hw_manager: HardwareManager,
        queue_runner: ExperimentQueueRunner,
    ):
        self._inputs = inputs_widget
        self._hw_manager = hw_manager
        self._queue_runner = queue_runner

    @property
    def procedure_class(self) -> Type["Procedure"]:
        """Return the current procedure class based on read mode."""
        from andor_qt.procedures import ImageProcedure, SpectrumProcedure

        if self._inputs.read_mode == "fvb":
            return SpectrumProcedure
        return ImageProcedure

    @property
    def sequenceable_inputs(self) -> List[str]:
        """Return the list of sequenceable parameter names."""
        if self._inputs.read_mode == "fvb":
            return list(_FVB_INPUTS)
        return list(_IMAGE_INPUTS)

    def make_procedure(self) -> "Procedure":
        """Create a procedure with current form values."""
        wl = 500.0
        grating = 1
        if self._hw_manager.spectrograph:
            wl = self._hw_manager.spectrograph.wavelength
            grating = self._hw_manager.spectrograph.grating

        return self._inputs.create_procedure(
            center_wavelength=wl,
            grating=grating,
        )

    def queue(self, procedure: Optional["Procedure"] = None) -> None:
        """Queue a procedure for execution.

        Args:
            procedure: Procedure to queue. If None, creates one from
                       the current form values.
        """
        if procedure is None:
            procedure = self.make_procedure()
        self._queue_runner.add(procedure)
