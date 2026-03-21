"""StageControlWidget — delay stage jog and readout panel.

Displays current position in both mm and ps, provides jog buttons
at multiple step sizes, and enforces software limits by disabling buttons
at the axis boundaries.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

#: Jog step sizes in mm (±)
JOG_STEPS_MM = [0.01, 0.1, 1.0]


class StageControlWidget(QGroupBox):
    """Jog control and readout widget for a single motion axis.

    Args:
        axis: Motion axis object (must have ``position``, ``position_ps``,
            ``position_min``, ``position_max`` attributes).
        axis_name: Display name for the axis.
        parent: Optional parent widget.
    """

    jog_requested = Signal(float)  # target position in mm

    def __init__(self, axis, axis_name: str = "delay", parent=None):
        super().__init__(f"Stage: {axis_name}", parent)
        self._axis = axis
        self._axis_name = axis_name
        self._jog_buttons: List[QPushButton] = []

        self._build_ui()
        self.update_position(axis.position, getattr(axis, "position_ps", 0.0))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- Readout row ---
        readout_row = QHBoxLayout()
        self._mm_label = QLabel("0.000 mm")
        self._mm_label.setAlignment(Qt.AlignCenter)
        self._ps_label = QLabel("0.00 ps")
        self._ps_label.setAlignment(Qt.AlignCenter)
        readout_row.addWidget(QLabel("Position:"))
        readout_row.addWidget(self._mm_label)
        readout_row.addWidget(self._ps_label)
        root.addLayout(readout_row)

        # --- Jog buttons row ---
        jog_row = QHBoxLayout()
        for step in reversed(JOG_STEPS_MM):
            btn = self._make_jog_button(f"-{step:.2g}mm", -step)
            jog_row.addWidget(btn)
        for step in JOG_STEPS_MM:
            btn = self._make_jog_button(f"+{step:.2g}mm", +step)
            jog_row.addWidget(btn)
        root.addLayout(jog_row)

    def _make_jog_button(self, label: str, step_mm: float) -> QPushButton:
        btn = QPushButton(label)
        direction = "+" if step_mm >= 0 else "-"
        btn.setProperty("jog_direction", direction)
        btn.setProperty("jog_step_mm", step_mm)
        btn.clicked.connect(lambda checked=False, s=step_mm: self._on_jog(s))
        self._jog_buttons.append(btn)
        return btn

    def _on_jog(self, step_mm: float) -> None:
        """Handle jog button click."""
        try:
            current = self._axis.position
            target = current + step_mm
            target = max(self._axis.position_min, min(target, self._axis.position_max))
            self._axis.position = target
            self.update_position(self._axis.position,
                                 getattr(self._axis, "position_ps", 0.0))
        except Exception as exc:
            log.error(f"Jog failed: {exc}")

    # -- public API --------------------------------------------------------

    @property
    def mm_label(self) -> QLabel:
        return self._mm_label

    @property
    def ps_label(self) -> QLabel:
        return self._ps_label

    @property
    def jog_buttons(self) -> List[QPushButton]:
        return list(self._jog_buttons)

    def update_position(self, position_mm: float, position_ps: float) -> None:
        """Update position readout labels and button states.

        Args:
            position_mm: Current position in mm.
            position_ps: Current position in ps.
        """
        self._mm_label.setText(f"{position_mm:.3f} mm")
        self._ps_label.setText(f"{position_ps:.2f} ps")

        at_min = position_mm <= self._axis.position_min
        at_max = position_mm >= self._axis.position_max

        for btn in self._jog_buttons:
            direction = btn.property("jog_direction")
            if direction == "+" and at_max:
                btn.setEnabled(False)
            elif direction == "-" and at_min:
                btn.setEnabled(False)
            else:
                btn.setEnabled(True)
