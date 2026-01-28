"""Tests for configuration classes.

These tests verify the configuration data classes and their behavior.
"""

from __future__ import annotations

import pytest


class TestHardwareConfig:
    """Tests for HardwareConfig data class."""

    def test_hardware_config_defaults(self):
        """HardwareConfig has sensible defaults."""
        from andor_qt.core.config import HardwareConfig

        config = HardwareConfig()

        assert config.sdk_path == r"C:\Program Files\Andor SDK"
        assert config.mock_mode is False
        assert config.default_temperature == -60
        assert config.warmup_temperature == -20

    def test_hardware_config_custom_values(self):
        """HardwareConfig accepts custom values."""
        from andor_qt.core.config import HardwareConfig

        config = HardwareConfig(
            sdk_path=r"D:\Custom\SDK",
            mock_mode=True,
            default_temperature=-80,
            warmup_temperature=-10,
        )

        assert config.sdk_path == r"D:\Custom\SDK"
        assert config.mock_mode is True
        assert config.default_temperature == -80
        assert config.warmup_temperature == -10

    def test_hardware_config_immutable(self):
        """HardwareConfig is frozen (immutable)."""
        from andor_qt.core.config import HardwareConfig

        config = HardwareConfig()

        with pytest.raises(AttributeError):
            config.sdk_path = "new_path"


class TestUIConfig:
    """Tests for UIConfig data class."""

    def test_ui_config_defaults(self):
        """UIConfig has sensible defaults."""
        from andor_qt.core.config import UIConfig

        config = UIConfig()

        assert config.window_title == "Andor Spectrometer Control"
        assert config.temperature_poll_interval_ms == 2000

    def test_ui_config_custom_values(self):
        """UIConfig accepts custom values."""
        from andor_qt.core.config import UIConfig

        config = UIConfig(
            window_title="Custom Title",
            temperature_poll_interval_ms=5000,
        )

        assert config.window_title == "Custom Title"
        assert config.temperature_poll_interval_ms == 5000

    def test_ui_config_immutable(self):
        """UIConfig is frozen (immutable)."""
        from andor_qt.core.config import UIConfig

        config = UIConfig()

        with pytest.raises(AttributeError):
            config.window_title = "new_title"


class TestCalibrationConfig:
    """Tests for CalibrationConfig data class."""

    def test_calibration_config_defaults(self):
        """CalibrationConfig has sensible defaults."""
        from andor_qt.core.config import CalibrationConfig

        config = CalibrationConfig()

        assert config.source == "sdk"
        assert config.file_path is None

    def test_calibration_config_file_source(self):
        """CalibrationConfig can be set to file source."""
        from andor_qt.core.config import CalibrationConfig

        config = CalibrationConfig(
            source="file",
            file_path=r"C:\calibration\cal.csv",
        )

        assert config.source == "file"
        assert config.file_path == r"C:\calibration\cal.csv"

    def test_calibration_config_immutable(self):
        """CalibrationConfig is frozen (immutable)."""
        from andor_qt.core.config import CalibrationConfig

        config = CalibrationConfig()

        with pytest.raises(AttributeError):
            config.source = "file"


class TestAppConfig:
    """Tests for AppConfig data class."""

    def test_app_config_default_factory(self):
        """AppConfig.default() creates config with defaults."""
        from andor_qt.core.config import AppConfig

        config = AppConfig.default()

        assert config.hardware is not None
        assert config.ui is not None
        assert config.calibration is not None
        assert config.hardware.mock_mode is False
        assert config.ui.window_title == "Andor Spectrometer Control"
        assert config.calibration.source == "sdk"

    def test_app_config_custom_components(self):
        """AppConfig accepts custom component configs."""
        from andor_qt.core.config import (
            AppConfig,
            CalibrationConfig,
            HardwareConfig,
            UIConfig,
        )

        hardware = HardwareConfig(mock_mode=True)
        ui = UIConfig(window_title="Custom")
        calibration = CalibrationConfig(source="file")

        config = AppConfig(hardware=hardware, ui=ui, calibration=calibration)

        assert config.hardware.mock_mode is True
        assert config.ui.window_title == "Custom"
        assert config.calibration.source == "file"

    def test_app_config_not_frozen(self):
        """AppConfig is mutable (for runtime updates)."""
        from andor_qt.core.config import AppConfig, HardwareConfig

        config = AppConfig.default()
        new_hardware = HardwareConfig(mock_mode=True)

        # Should not raise
        config.hardware = new_hardware
        assert config.hardware.mock_mode is True
