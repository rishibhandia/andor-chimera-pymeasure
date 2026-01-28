"""Tests for BenchmarkDialog.

These tests verify the benchmark dialog UI and result calculation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestBenchmarkDialogStructure:
    """Tests for benchmark dialog UI structure."""

    def test_dialog_has_iterations_spinbox(self, qt_app):
        """Benchmark dialog has an iterations spinbox."""
        from andor_qt.widgets.dialogs.benchmark_dialog import BenchmarkDialog

        dialog = BenchmarkDialog()

        assert hasattr(dialog, "_iterations_spin")

    def test_dialog_has_start_button(self, qt_app):
        """Benchmark dialog has a Start button."""
        from andor_qt.widgets.dialogs.benchmark_dialog import BenchmarkDialog

        dialog = BenchmarkDialog()

        assert hasattr(dialog, "_start_btn")
        assert dialog._start_btn.text() == "Start"

    def test_dialog_has_results_label(self, qt_app):
        """Benchmark dialog has a results display."""
        from andor_qt.widgets.dialogs.benchmark_dialog import BenchmarkDialog

        dialog = BenchmarkDialog()

        assert hasattr(dialog, "_results_label")


class TestBenchmarkResult:
    """Tests for BenchmarkResult data class."""

    def test_benchmark_result_fields(self):
        """BenchmarkResult has all required fields."""
        from andor_qt.widgets.dialogs.benchmark_dialog import BenchmarkResult

        result = BenchmarkResult(
            iterations=10,
            total_time_ms=1000.0,
            avg_time_ms=100.0,
            min_time_ms=90.0,
            max_time_ms=110.0,
        )

        assert result.iterations == 10
        assert result.total_time_ms == 1000.0
        assert result.avg_time_ms == 100.0
        assert result.min_time_ms == 90.0
        assert result.max_time_ms == 110.0


class TestBenchmarkDialogSignals:
    """Tests for benchmark dialog signals."""

    def test_start_button_emits_signal(self, qt_app, handler_factory):
        """Start button emits benchmark_requested signal."""
        from andor_qt.widgets.dialogs.benchmark_dialog import BenchmarkDialog

        dialog = BenchmarkDialog()
        handler = handler_factory("bench_handler")
        dialog.benchmark_requested.connect(handler)

        dialog._start_btn.click()

        handler.assert_called_once()

    def test_display_results(self, qt_app):
        """display_results updates the results label."""
        from andor_qt.widgets.dialogs.benchmark_dialog import (
            BenchmarkDialog,
            BenchmarkResult,
        )

        dialog = BenchmarkDialog()
        result = BenchmarkResult(
            iterations=10,
            total_time_ms=1000.0,
            avg_time_ms=100.0,
            min_time_ms=90.0,
            max_time_ms=110.0,
        )

        dialog.display_results(result)

        text = dialog._results_label.text()
        assert "100.0" in text  # avg time
        assert "10" in text  # iterations
