"""Benchmark dialog for measuring acquisition performance.

Runs multiple acquisitions and reports timing statistics.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


@dataclass
class BenchmarkResult:
    """Results from a benchmark run.

    Attributes:
        iterations: Number of acquisitions performed.
        total_time_ms: Total elapsed time in milliseconds.
        avg_time_ms: Average time per acquisition in milliseconds.
        min_time_ms: Minimum acquisition time in milliseconds.
        max_time_ms: Maximum acquisition time in milliseconds.
    """

    iterations: int
    total_time_ms: float
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float


class BenchmarkDialog(QDialog):
    """Dialog for running acquisition benchmarks.

    Allows the user to specify number of iterations and displays
    timing statistics.

    Signals:
        benchmark_requested: Emitted with iteration count when Start is clicked.
    """

    benchmark_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Acquisition Benchmark")
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Iterations row
        iter_layout = QHBoxLayout()
        iter_layout.addWidget(QLabel("Iterations:"))

        self._iterations_spin = QSpinBox()
        self._iterations_spin.setRange(1, 1000)
        self._iterations_spin.setValue(10)
        iter_layout.addWidget(self._iterations_spin)

        self._start_btn = QPushButton("Start")
        self._start_btn.clicked.connect(
            lambda: self.benchmark_requested.emit(self._iterations_spin.value())
        )
        iter_layout.addWidget(self._start_btn)

        layout.addLayout(iter_layout)

        # Results display
        self._results_label = QLabel("No results yet.")
        self._results_label.setWordWrap(True)
        layout.addWidget(self._results_label)

    def display_results(self, result: BenchmarkResult) -> None:
        """Display benchmark results.

        Args:
            result: Benchmark results to display.
        """
        text = (
            f"Benchmark Results ({result.iterations} iterations)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Total:   {result.total_time_ms:.1f} ms\n"
            f"Average: {result.avg_time_ms:.1f} ms\n"
            f"Min:     {result.min_time_ms:.1f} ms\n"
            f"Max:     {result.max_time_ms:.1f} ms"
        )
        self._results_label.setText(text)

    def set_running(self, running: bool) -> None:
        """Update UI state during benchmark.

        Args:
            running: True if benchmark is in progress.
        """
        self._start_btn.setEnabled(not running)
        self._iterations_spin.setEnabled(not running)
        if running:
            self._results_label.setText("Running benchmark...")
