"""Menu bar for the Andor Spectrometer application.

Provides File, Acquisition, and Help menus with keyboard shortcuts
and signal-based action communication.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenuBar
from PySide6.QtCore import Signal


class AndorMenuBar(QMenuBar):
    """Main application menu bar.

    Signals:
        save_requested: Emitted when user requests to save.
        load_calibration_requested: Emitted when user wants to load calibration.
        exit_requested: Emitted when user wants to exit.
        acquire_requested: Emitted when user wants to start acquisition.
        abort_requested: Emitted when user wants to abort acquisition.
        benchmark_requested: Emitted when user wants to run benchmark.
        about_requested: Emitted when user requests about dialog.
    """

    save_requested = Signal()
    load_calibration_requested = Signal()
    exit_requested = Signal()
    acquire_requested = Signal()
    abort_requested = Signal()
    benchmark_requested = Signal()
    about_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._create_file_menu()
        self._create_acquisition_menu()
        self._create_help_menu()

    def _create_file_menu(self) -> None:
        """Create the File menu."""
        file_menu = self.addMenu("&File")

        self.save_action = QAction("&Save Data", self)
        self.save_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_action.triggered.connect(self.save_requested.emit)
        file_menu.addAction(self.save_action)

        self.load_calibration_action = QAction("&Load Calibration...", self)
        self.load_calibration_action.triggered.connect(
            self.load_calibration_requested.emit
        )
        file_menu.addAction(self.load_calibration_action)

        file_menu.addSeparator()

        self.exit_action = QAction("E&xit", self)
        self.exit_action.setShortcut(QKeySequence("Alt+F4"))
        self.exit_action.triggered.connect(self.exit_requested.emit)
        file_menu.addAction(self.exit_action)

    def _create_acquisition_menu(self) -> None:
        """Create the Acquisition menu."""
        acq_menu = self.addMenu("&Acquisition")

        self.acquire_action = QAction("&Acquire", self)
        self.acquire_action.setShortcut(QKeySequence("Return"))
        self.acquire_action.triggered.connect(self.acquire_requested.emit)
        acq_menu.addAction(self.acquire_action)

        self.abort_action = QAction("A&bort", self)
        self.abort_action.setShortcut(QKeySequence("Escape"))
        self.abort_action.triggered.connect(self.abort_requested.emit)
        acq_menu.addAction(self.abort_action)

        acq_menu.addSeparator()

        self.benchmark_action = QAction("&Benchmark...", self)
        self.benchmark_action.triggered.connect(self.benchmark_requested.emit)
        acq_menu.addAction(self.benchmark_action)

    def _create_help_menu(self) -> None:
        """Create the Help menu."""
        help_menu = self.addMenu("&Help")

        self.about_action = QAction("&About", self)
        self.about_action.triggered.connect(self.about_requested.emit)
        help_menu.addAction(self.about_action)
