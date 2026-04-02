"""Application entry point for the Andor Qt GUI.

This module provides the main entry point for running the application.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from datetime import datetime
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


def setup_file_logging(
    log_directory: str,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.handlers.RotatingFileHandler:
    """Add a RotatingFileHandler that writes session logs to a file.

    Creates the log directory if it does not exist. The log filename
    is timestamped as ``YYYYMMDD_HHMMSS_andor.log``.

    Args:
        log_directory: Directory where log files are written.
        max_bytes: Maximum size per log file in bytes (default 10 MB).
        backup_count: Number of rotated backup files to keep (default 5).

    Returns:
        The RotatingFileHandler that was added to the root logger.
    """
    log_dir = Path(log_directory)
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{timestamp}_andor.log"
    log_path = log_dir / log_filename

    handler = logging.handlers.RotatingFileHandler(
        str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    # Ensure the root logger level allows INFO messages to reach the file
    # handler.  The root logger defaults to WARNING (30); lower it to INFO (20)
    # so that INFO-level messages propagate through.
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)
    return handler


def create_argument_parser():
    """Create and return the argument parser.

    Returns:
        argparse.ArgumentParser: Configured argument parser.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Andor Spectrometer Qt GUI")
    parser.add_argument(
        "--mock", action="store_true", help="Run in mock mode (no hardware required)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--config", type=Path, help="Path to configuration file")
    parser.add_argument(
        "--create-shortcut",
        action="store_true",
        help="Create a desktop shortcut and exit",
    )
    return parser


def main() -> int:
    """Main entry point for the Andor Qt GUI application.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    # Parse command line arguments
    parser = create_argument_parser()
    args = parser.parse_args()

    # Handle --create-shortcut flag
    if args.create_shortcut:
        try:
            from andor_qt.utils.shortcut import create_desktop_shortcut

            shortcut_path = create_desktop_shortcut(
                name="Andor Spectrometer",
                mock_mode=args.mock,
            )
            print(f"Desktop shortcut created: {shortcut_path}")
            return 0
        except Exception as e:
            print(f"Failed to create shortcut: {e}")
            return 1

    # Set environment variables from command line
    if args.mock:
        os.environ["ANDOR_MOCK"] = "1"
    if args.debug:
        os.environ["ANDOR_DEBUG"] = "1"

    # Set up logging
    log_level = logging.DEBUG if os.environ.get("ANDOR_DEBUG") else logging.INFO
    setup_logging(log_level)

    log = logging.getLogger(__name__)

    # Set up file logging from persisted QSettings directory
    try:
        from PySide6.QtCore import QSettings

        settings = QSettings("AndorSpectrometer", "Logging")
        log_dir = settings.value("log_directory", str(Path.home() / "andor_logs"))
        setup_file_logging(str(log_dir))
    except Exception as e:
        # File logging is best-effort — don't prevent app startup
        logging.getLogger(__name__).warning(f"Could not set up file logging: {e}")

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

        # Create and show main window maximized (dense lab UI needs full screen)
        window = AndorSpectrometerWindow(config=config)
        window.showMaximized()

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
