"""Data I/O utilities for saving spectrum and image data.

Provides functions for saving data in various formats with or without
embedded metadata.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


def save_csv_data_only(
    filepath: Path,
    wavelengths: np.ndarray,
    intensities: np.ndarray,
) -> Path:
    """Save spectrum data to CSV without metadata comments.

    Creates a clean CSV file with just header row and data, suitable for
    use with separate metadata JSON sidecar files.

    Args:
        filepath: Path to save the CSV file.
        wavelengths: Array of wavelength values (nm).
        intensities: Array of intensity values.

    Returns:
        Path to the saved file.
    """
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Wavelength (nm)", "Intensity"])

        for wl, intensity in zip(wavelengths, intensities):
            writer.writerow([f"{wl:.3f}", f"{intensity:.1f}"])

    return filepath


def save_csv_with_metadata(
    filepath: Path,
    wavelengths: np.ndarray,
    intensities: np.ndarray,
    params: dict,
    session_meta: dict,
) -> Path:
    """Save spectrum data to CSV with embedded metadata comments.

    Creates a CSV file with metadata in comment lines at the top,
    for legacy compatibility.

    Args:
        filepath: Path to save the CSV file.
        wavelengths: Array of wavelength values (nm).
        intensities: Array of intensity values.
        params: Acquisition parameters to embed.
        session_meta: Session metadata to embed.

    Returns:
        Path to the saved file.
    """
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Write metadata as comments
        writer.writerow(["# Andor Spectrum Data"])
        for key, value in params.items():
            writer.writerow([f"# {key}", value])
        for key, value in session_meta.items():
            if value:  # Only write non-empty values
                writer.writerow([f"# {key}", value])
        writer.writerow([])

        # Write header and data
        writer.writerow(["Wavelength (nm)", "Intensity"])
        for wl, intensity in zip(wavelengths, intensities):
            writer.writerow([f"{wl:.3f}", f"{intensity:.1f}"])

    return filepath


def save_npz_data_only(
    filepath: Path,
    wavelengths: np.ndarray,
    data: np.ndarray,
) -> Path:
    """Save data to NPZ without embedded parameters.

    Creates a minimal NPZ file with just data and wavelength arrays,
    suitable for use with separate metadata JSON sidecar files.

    Args:
        filepath: Path to save the NPZ file.
        wavelengths: Array of wavelength values (nm).
        data: Data array (1D spectrum or 2D image).

    Returns:
        Path to the saved file.
    """
    np.savez(filepath, data=data, wavelengths=wavelengths)
    return filepath


def save_npz_with_metadata(
    filepath: Path,
    wavelengths: np.ndarray,
    data: np.ndarray,
    params: dict,
    session_meta: dict,
) -> Path:
    """Save data to NPZ with embedded parameters.

    Creates an NPZ file with data arrays plus parameter values,
    for legacy compatibility.

    Args:
        filepath: Path to save the NPZ file.
        wavelengths: Array of wavelength values (nm).
        data: Data array (1D spectrum or 2D image).
        params: Acquisition parameters to embed.
        session_meta: Session metadata to embed.

    Returns:
        Path to the saved file.
    """
    # Merge all metadata into kwargs
    all_meta = {**params, **session_meta}
    np.savez(filepath, data=data, wavelengths=wavelengths, **all_meta)
    return filepath
