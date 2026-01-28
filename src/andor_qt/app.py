"""Application entry point for the Andor Qt GUI.

This module provides the main entry point for running the application.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from andor_qt.core.config import AppConfig


def get_default_config_path() -> Path:
    """Get the default configuration file path.

    Returns platform-appropriate path:
    - Windows: %APPDATA%/AndorSpectrometer/config.yaml
    - macOS: ~/Library/Application Support/AndorSpectrometer/config.yaml
    - Linux: ~/.config/andor-spectrometer/config.yaml

    Returns:
        Path to the default config file.
    """
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(app_data) / "AndorSpectrometer" / "config.yaml"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AndorSpectrometer" / "config.yaml"
    else:
        # Linux and other Unix-like systems
        xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return Path(xdg_config) / "andor-spectrometer" / "config.yaml"


def load_config(path: Optional[Path] = None) -> AppConfig:
    """Load configuration from file or return defaults.

    Args:
        path: Path to config file. If None, uses default path.

    Returns:
        Loaded or default AppConfig.
    """
    if path is None:
        path = get_default_config_path()

    return AppConfig.load_or_default(path)


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
    parser.add_argument("--config", type=Path, help="Path to configuration file")
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

    # Load configuration
    config = load_config(args.config)
    log.info(f"Configuration loaded (mock_mode={config.hardware.mock_mode})")

    # Check for mock mode
    if config.hardware.mock_mode:
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
