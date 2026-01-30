"""Custom SequencerWidget with user feedback on validation errors.

PyMeasure's SequencerWidget logs errors silently. This wrapper adds
visual feedback via message boxes and status bar updates.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox
from pymeasure.display.widgets.sequencer_widget import SequencerWidget
from pymeasure.experiment.sequencer import SequenceEvaluationError

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)


class FeedbackSequencerWidget(SequencerWidget):
    """SequencerWidget with user-visible feedback on validation errors.

    Extends PyMeasure's SequencerWidget to show message boxes when:
    - Sequence validation fails (invalid syntax)
    - No sequences are entered
    - Queuing 0 measurements (empty sequence)

    Usage:
        widget = FeedbackSequencerWidget(
            inputs=["exposure_time", "center_wavelength"],
            parent=sequencer_adapter,
        )
    """

    def __init__(self, inputs=None, sequence_file=None, parent=None):
        super().__init__(inputs=inputs, sequence_file=sequence_file, parent=parent)
        self._last_queue_count = 0

    def queue_sequence(self):
        """Queue sequence with user feedback on errors.

        Overrides parent to show message boxes for common issues.
        """
        self.queue_button.setEnabled(False)

        try:
            sequence = self.get_sequence()
        except SequenceEvaluationError as e:
            log.error(f"Sequence evaluation error: {e}")
            self._show_error(
                "Invalid Sequence",
                "One or more sequence expressions could not be evaluated.\n\n"
                "Please check your sequence syntax. Valid examples:\n"
                "  • [0.1, 0.5, 1.0, 2.0]\n"
                "  • range(400, 600, 50)\n"
                "  • arange(0, 100, 10)\n\n"
                f"Error: {e}"
            )
            self.queue_button.setEnabled(True)
            return
        except TypeError as e:
            log.error(f"Sequence type error: {e}")
            self._show_error(
                "Missing Sequence",
                "No sequence values entered.\n\n"
                "To create a sequence:\n"
                "1. Click 'Add root item' to add a parameter\n"
                "2. Select a parameter from the dropdown\n"
                "3. Enter a sequence expression (e.g., range(450, 550, 50))\n"
                "4. Click 'Queue sequence'"
            )
            self.queue_button.setEnabled(True)
            return

        self._last_queue_count = len(sequence)

        if len(sequence) == 0:
            self._show_warning(
                "Empty Sequence",
                "No measurements to queue.\n\n"
                "Add sequence items using 'Add root item' and enter\n"
                "sequence values before clicking 'Queue sequence'."
            )
            self.queue_button.setEnabled(True)
            return

        # Queue the procedures
        log.info(f"Queuing {len(sequence)} measurements based on the entered sequences.")

        from collections import ChainMap
        from PySide6.QtWidgets import QApplication

        for entry in sequence:
            QApplication.processEvents()
            parameters = dict(ChainMap(*entry[::-1]))

            procedure = self._parent.make_procedure()
            procedure.set_parameters(parameters)
            self._parent.queue(procedure=procedure)

        self._show_info(
            "Sequence Queued",
            f"Successfully queued {len(sequence)} measurements."
        )

        self.queue_button.setEnabled(True)

    def _show_error(self, title: str, message: str) -> None:
        """Show an error message box."""
        QMessageBox.critical(self, title, message)

    def _show_warning(self, title: str, message: str) -> None:
        """Show a warning message box."""
        QMessageBox.warning(self, title, message)

    def _show_info(self, title: str, message: str) -> None:
        """Show an info message box."""
        QMessageBox.information(self, title, message)

    @property
    def last_queue_count(self) -> int:
        """Return the number of procedures queued in the last queue_sequence call."""
        return self._last_queue_count
