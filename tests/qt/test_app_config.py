"""Tests for app configuration integration.

These tests verify that the application correctly loads and uses
configuration from files and command-line arguments.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestAppConfigIntegration:
    """Tests for app.py configuration integration."""

    def test_app_loads_config_on_startup(self, tmp_path, monkeypatch):
        """Application loads config file when specified."""
        from andor_qt.core.config import AppConfig

        # Create test config file
        config_path = tmp_path / "config.yaml"
        config = AppConfig.default()
        config.to_yaml(config_path)

        # Import load_config function
        from andor_qt.app import load_config

        loaded = load_config(config_path)

        assert loaded is not None
        assert isinstance(loaded, AppConfig)

    def test_cli_mock_flag_overrides_config(self, tmp_path, monkeypatch):
        """--mock CLI flag overrides config file mock_mode."""
        from andor_qt.core.config import AppConfig

        # Create config with mock_mode=False
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
hardware:
  mock_mode: false
ui:
  window_title: "Test"
calibration:
  source: sdk
"""
        )

        # Set ANDOR_MOCK to simulate --mock flag
        monkeypatch.setenv("ANDOR_MOCK", "1")

        from andor_qt.app import load_config

        loaded = load_config(config_path)

        # CLI flag should override file setting
        assert loaded.hardware.mock_mode is True

    def test_hardware_manager_uses_config_sdk_path(
        self, tmp_path, monkeypatch, qt_app, reset_hardware_manager
    ):
        """HardwareManager uses SDK path from config."""
        from andor_qt.core.config import AppConfig, HardwareConfig

        # Create config with custom SDK path
        config = AppConfig(
            hardware=HardwareConfig(
                sdk_path=r"D:\Custom\SDK\Path",
                mock_mode=True,  # Use mock to avoid real hardware
            ),
        )

        HardwareManager = reset_hardware_manager
        manager = HardwareManager.instance()
        manager.set_config(config)

        assert manager.sdk_path == r"D:\Custom\SDK\Path"

    def test_config_default_path(self):
        """get_default_config_path returns platform-appropriate path."""
        from andor_qt.app import get_default_config_path

        path = get_default_config_path()

        assert path is not None
        assert isinstance(path, Path)
        # Should be in user's home or app data directory
        assert "andor" in str(path).lower() or "config" in str(path).lower()
