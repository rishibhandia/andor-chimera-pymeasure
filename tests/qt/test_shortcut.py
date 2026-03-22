"""Tests for desktop shortcut creation utility.

TDD: Tests written first, then implementation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGetDesktopPath:
    """Tests for get_desktop_path function."""

    def test_get_desktop_path_returns_valid_path(self):
        """Desktop path should be a Path object pointing to Desktop folder."""
        from andor_qt.utils.shortcut import get_desktop_path

        desktop = get_desktop_path()
        assert isinstance(desktop, Path)
        assert "Desktop" in str(desktop)

    def test_get_desktop_path_uses_userprofile_on_windows(self):
        """On Windows, should use USERPROFILE environment variable."""
        from andor_qt.utils.shortcut import get_desktop_path

        with patch.dict(os.environ, {"USERPROFILE": r"C:\Users\TestUser"}):
            with patch("sys.platform", "win32"):
                desktop = get_desktop_path()
                assert str(desktop).endswith("Desktop")


class TestGetEntryPointPath:
    """Tests for get_entry_point_path function."""

    def test_get_entry_point_path_finds_script(self, tmp_path):
        """Should find andor-qt executable in Scripts folder."""
        from andor_qt.utils.shortcut import get_entry_point_path

        # Create a mock Scripts directory with andor-qt.exe
        scripts_dir = tmp_path / "Scripts"
        scripts_dir.mkdir()
        exe_path = scripts_dir / "andor-qt.exe"
        exe_path.touch()

        with patch.object(sys, "prefix", str(tmp_path)):
            with patch.object(sys, "base_prefix", str(tmp_path)):
                result = get_entry_point_path()
                assert result is not None
                assert result.name in ("andor-qt.exe", "andor-qt")

    def test_get_entry_point_path_returns_none_if_not_found(self, tmp_path):
        """Should return None if no entry point script found."""
        from andor_qt.utils.shortcut import get_entry_point_path

        # Point to empty directory
        with patch.object(sys, "prefix", str(tmp_path)):
            with patch.object(sys, "base_prefix", str(tmp_path)):
                result = get_entry_point_path()
                assert result is None


class TestCreateDesktopShortcut:
    """Tests for create_desktop_shortcut function."""

    @pytest.fixture
    def mock_powershell(self):
        """Mock subprocess.run for PowerShell commands."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            yield mock_run

    def test_create_shortcut_generates_lnk_file(self, tmp_path, mock_powershell):
        """create_desktop_shortcut should create a .lnk file."""
        from andor_qt.utils.shortcut import create_desktop_shortcut

        # Mock dependencies
        with patch("andor_qt.utils.shortcut.get_desktop_path", return_value=tmp_path):
            with patch(
                "andor_qt.utils.shortcut.get_entry_point_path",
                return_value=Path(r"C:\Python\Scripts\andor-qt.exe"),
            ):
                result = create_desktop_shortcut(name="Andor Spectrometer")

                # Should return path to shortcut
                assert result is not None
                assert result.suffix == ".lnk"
                assert "Andor Spectrometer" in result.name

    def test_create_shortcut_calls_powershell(self, tmp_path, mock_powershell):
        """Should use PowerShell to create Windows shortcut."""
        from andor_qt.utils.shortcut import create_desktop_shortcut

        with patch("andor_qt.utils.shortcut.get_desktop_path", return_value=tmp_path):
            with patch(
                "andor_qt.utils.shortcut.get_entry_point_path",
                return_value=Path(r"C:\Python\Scripts\andor-qt.exe"),
            ):
                create_desktop_shortcut(name="Test Shortcut")

                # PowerShell should have been called
                assert mock_powershell.called

    def test_create_shortcut_includes_mock_argument_when_enabled(
        self, tmp_path, mock_powershell
    ):
        """When mock_mode=True, shortcut should include --mock argument."""
        from andor_qt.utils.shortcut import create_desktop_shortcut

        with patch("andor_qt.utils.shortcut.get_desktop_path", return_value=tmp_path):
            with patch(
                "andor_qt.utils.shortcut.get_entry_point_path",
                return_value=Path(r"C:\Python\Scripts\andor-qt.exe"),
            ):
                create_desktop_shortcut(name="Test Shortcut", mock_mode=True)

                # Check that --mock was included in the PowerShell command
                call_args = mock_powershell.call_args
                assert call_args is not None
                command = " ".join(str(arg) for arg in call_args[0][0])
                assert "--mock" in command

    def test_create_shortcut_raises_if_no_entry_point(self, tmp_path):
        """Should raise RuntimeError if entry point not found."""
        from andor_qt.utils.shortcut import create_desktop_shortcut

        with patch("andor_qt.utils.shortcut.get_desktop_path", return_value=tmp_path):
            with patch("andor_qt.utils.shortcut.get_entry_point_path", return_value=None):
                with pytest.raises(RuntimeError, match="entry point"):
                    create_desktop_shortcut(name="Test")
