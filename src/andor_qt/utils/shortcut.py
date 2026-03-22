"""Desktop shortcut creation utility for Windows.

Provides functions to create Windows .lnk shortcut files for launching
the Andor Spectrometer application.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def get_desktop_path() -> Path:
    """Get the Windows Desktop folder path.

    Returns:
        Path to the current user's Desktop folder.
    """
    userprofile = os.environ.get("USERPROFILE", "")
    if not userprofile:
        userprofile = os.path.expanduser("~")
    return Path(userprofile) / "Desktop"


def get_entry_point_path() -> Optional[Path]:
    """Find the andor-qt entry point script/executable path.

    Searches for andor-qt.exe or andor-qt script in the Python
    Scripts directory.

    Returns:
        Path to the entry point executable, or None if not found.
    """
    search_bases = [sys.prefix, sys.base_prefix]
    script_names = ["andor-qt.exe", "andor-qt"]

    for base in search_bases:
        scripts_dir = Path(base) / "Scripts"
        for name in script_names:
            script_path = scripts_dir / name
            if script_path.exists():
                return script_path

    return None


def create_desktop_shortcut(
    name: str = "Andor Spectrometer",
    mock_mode: bool = False,
) -> Path:
    """Create a Windows .lnk shortcut on the Desktop.

    Uses PowerShell to create the shortcut file since Python doesn't
    have native support for Windows shortcuts.

    Args:
        name: Display name for the shortcut (without .lnk extension).
        mock_mode: If True, adds --mock argument to run in mock mode.

    Returns:
        Path to the created shortcut file.

    Raises:
        RuntimeError: If the entry point script cannot be found or
            shortcut creation fails.
    """
    entry_point = get_entry_point_path()
    if entry_point is None:
        raise RuntimeError(
            "Could not find andor-qt entry point. "
            "Make sure the package is installed correctly."
        )

    desktop = get_desktop_path()
    shortcut_path = desktop / f"{name}.lnk"

    # Build arguments string
    arguments = "--mock" if mock_mode else ""

    # PowerShell script to create shortcut
    ps_script = f"""
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{entry_point}"
$Shortcut.Arguments = "{arguments}"
$Shortcut.WorkingDirectory = "{desktop}"
$Shortcut.Description = "Launch Andor Spectrometer GUI"
$Shortcut.Save()
"""

    # Execute PowerShell command
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to create shortcut: {result.stderr}"
        )

    return shortcut_path
