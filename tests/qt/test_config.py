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


class TestConfigYAML:
    """Tests for YAML serialization/deserialization."""

    def test_config_to_yaml(self, tmp_path):
        """AppConfig can be saved to YAML file."""
        from andor_qt.core.config import AppConfig

        config = AppConfig.default()
        yaml_path = tmp_path / "config.yaml"

        config.to_yaml(yaml_path)

        assert yaml_path.exists()
        content = yaml_path.read_text()
        assert "hardware:" in content
        assert "ui:" in content
        assert "calibration:" in content

    def test_config_from_yaml(self, tmp_path):
        """AppConfig can be loaded from YAML file."""
        from andor_qt.core.config import AppConfig

        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(
            """
hardware:
  sdk_path: "D:\\\\Custom\\\\SDK"
  mock_mode: true
  default_temperature: -80
  warmup_temperature: -10
ui:
  window_title: "Custom Title"
  temperature_poll_interval_ms: 5000
calibration:
  source: file
  file_path: "C:\\\\cal.csv"
"""
        )

        config = AppConfig.from_yaml(yaml_path)

        assert config.hardware.sdk_path == "D:\\Custom\\SDK"
        assert config.hardware.mock_mode is True
        assert config.hardware.default_temperature == -80
        assert config.ui.window_title == "Custom Title"
        assert config.calibration.source == "file"

    def test_config_roundtrip(self, tmp_path):
        """AppConfig survives save/load roundtrip."""
        from andor_qt.core.config import (
            AppConfig,
            CalibrationConfig,
            HardwareConfig,
            UIConfig,
        )

        original = AppConfig(
            hardware=HardwareConfig(
                sdk_path="D:\\Test",
                mock_mode=True,
                default_temperature=-75,
            ),
            ui=UIConfig(
                window_title="Test App",
                temperature_poll_interval_ms=3000,
            ),
            calibration=CalibrationConfig(
                source="file",
                file_path="C:\\test.csv",
            ),
        )

        yaml_path = tmp_path / "config.yaml"
        original.to_yaml(yaml_path)
        loaded = AppConfig.from_yaml(yaml_path)

        assert loaded.hardware.sdk_path == original.hardware.sdk_path
        assert loaded.hardware.mock_mode == original.hardware.mock_mode
        assert loaded.hardware.default_temperature == original.hardware.default_temperature
        assert loaded.ui.window_title == original.ui.window_title
        assert loaded.calibration.source == original.calibration.source
        assert loaded.calibration.file_path == original.calibration.file_path

    def test_config_missing_file_returns_default(self, tmp_path, monkeypatch):
        """load_or_default returns default config if file missing."""
        from andor_qt.core.config import AppConfig

        # Clear ANDOR_MOCK env var for this test
        monkeypatch.delenv("ANDOR_MOCK", raising=False)

        yaml_path = tmp_path / "nonexistent.yaml"
        config = AppConfig.load_or_default(yaml_path)

        assert config.hardware.mock_mode is False
        assert config.ui.window_title == "Andor Spectrometer Control"

    def test_env_var_override_mock_mode(self, tmp_path, monkeypatch):
        """ANDOR_MOCK env var overrides config mock_mode."""
        from andor_qt.core.config import AppConfig

        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(
            """
hardware:
  mock_mode: false
ui:
  window_title: "Test"
calibration:
  source: sdk
"""
        )

        monkeypatch.setenv("ANDOR_MOCK", "1")
        config = AppConfig.load_or_default(yaml_path)

        # Env var should override file setting
        assert config.hardware.mock_mode is True
