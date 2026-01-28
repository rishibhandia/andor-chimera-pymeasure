"""Application entry point for the Andor Qt GUI.

This module provides the main entry point for running the application.
"""

from __future__ import annotations

import logging
import os
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Set up logging configuration.

    Args:
        level: Logging level.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    """Main entry point for the Andor Qt GUI application.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    # Parse command line arguments
    import argparse

    parser = argparse.ArgumentParser(description="Andor Spectrometer Qt GUI")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no hardware required)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Set environment variables from command line
    if args.mock:
        os.environ["ANDOR_MOCK"] = "1"
    if args.debug:
        os.environ["ANDOR_DEBUG"] = "1"

    # Set up logging
    log_level = logging.DEBUG if os.environ.get("ANDOR_DEBUG") else logging.INFO
    setup_logging(log_level)

    log = logging.getLogger(__name__)
    log.info("Starting Andor Spectrometer Qt GUI")

    # Check for mock mode
    if os.environ.get("ANDOR_MOCK", "0") == "1":
        log.info("Running in MOCK mode (no hardware required)")

    try:
        from PySide6.QtWidgets import QApplication

        from andor_qt.windows import AndorSpectrometerWindow

        # Create application
        app = QApplication(sys.argv)
        app.setApplicationName("Andor Spectrometer")
        app.setOrganizationName("Katsumi Lab")

        # Create and show main window
        window = AndorSpectrometerWindow()
        window.show()

        # Run event loop
        return app.exec()

    except ImportError as e:
        log.error(f"Failed to import required module: {e}")
        print(f"Error: Missing required dependency: {e}")
        print("Please install PySide6: uv pip install pyside6")
        return 1

    except Exception as e:
        log.exception(f"Application error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
