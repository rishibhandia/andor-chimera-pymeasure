"""Configuration classes for the Qt GUI.

This module provides data classes for application configuration,
including hardware settings, UI preferences, and calibration options.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class HardwareConfig:
    """Configuration for hardware devices.

    Attributes:
        sdk_path: Path to the Andor SDK installation.
        mock_mode: Whether to use mock hardware for development.
        default_temperature: Default cooling target temperature (°C).
        warmup_temperature: Temperature to warm up to before shutdown (°C).
    """

    sdk_path: str = r"C:\Program Files\Andor SDK"
    mock_mode: bool = False
    default_temperature: int = -60
    warmup_temperature: int = -20


@dataclass(frozen=True)
class UIConfig:
    """Configuration for the user interface.

    Attributes:
        window_title: Main window title.
        temperature_poll_interval_ms: Temperature polling interval in ms.
    """

    window_title: str = "Andor Spectrometer Control"
    temperature_poll_interval_ms: int = 2000


@dataclass(frozen=True)
class CalibrationConfig:
    """Configuration for wavelength calibration.

    Attributes:
        source: Calibration source - "sdk" for SDK-computed or "file" for file.
        file_path: Path to calibration file (when source is "file").
    """

    source: str = "sdk"
    file_path: Optional[str] = None


@dataclass
class AppConfig:
    """Main application configuration.

    This is the top-level configuration container that holds all
    configuration sections. It is mutable to allow runtime updates.

    Attributes:
        hardware: Hardware device configuration.
        ui: User interface configuration.
        calibration: Calibration settings.
    """

    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)

    @classmethod
    def default(cls) -> "AppConfig":
        """Create a configuration with default values.

        Returns:
            AppConfig with all default settings.
        """
        return cls(
            hardware=HardwareConfig(),
            ui=UIConfig(),
            calibration=CalibrationConfig(),
        )
