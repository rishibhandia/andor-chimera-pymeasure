"""Metadata serialization utility for separate JSON sidecar files.

Provides functions to save and load metadata separately from data files,
using JSON sidecar files with .meta.json extension.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np


class MetadataEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types and datetime objects."""

    def default(self, obj: Any) -> Any:
        """Convert non-serializable objects to JSON-compatible types."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def save_metadata(
    filepath: Path,
    params: dict,
    session_meta: dict,
) -> Path:
    """Save metadata to a JSON sidecar file.

    Creates a .meta.json file alongside the data file containing
    acquisition parameters and session information.

    Args:
        filepath: Path to the data file (CSV, NPZ, etc.).
        params: Acquisition parameters (exposure, grating, wavelength, etc.).
        session_meta: Session information (sample_id, operator, notes, etc.).

    Returns:
        Path to the created metadata file.
    """
    # Construct metadata path: data_001.csv -> data_001.meta.json
    meta_path = filepath.with_suffix(".meta.json")

    metadata = {
        "version": "1.0",
        "created": datetime.now().isoformat(),
        "data_file": filepath.name,
        "acquisition": params,
        "session": session_meta,
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, cls=MetadataEncoder)

    return meta_path


def load_metadata(filepath: Path) -> Optional[dict]:
    """Load metadata from a JSON sidecar file.

    Args:
        filepath: Path to the data file (the .meta.json will be derived).

    Returns:
        Metadata dict if found, None if metadata file doesn't exist.
    """
    meta_path = filepath.with_suffix(".meta.json")

    if not meta_path.exists():
        return None

    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)
