"""Tests for metadata serialization utility.

TDD: Tests written first, then implementation.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest


class TestMetadataEncoder:
    """Tests for MetadataEncoder JSON encoder."""

    def test_metadata_encoder_handles_numpy_int(self):
        """MetadataEncoder handles numpy int types."""
        from andor_qt.utils.metadata import MetadataEncoder

        data = {"value": np.int64(42)}
        result = json.dumps(data, cls=MetadataEncoder)
        parsed = json.loads(result)

        assert parsed["value"] == 42
        assert isinstance(parsed["value"], int)

    def test_metadata_encoder_handles_numpy_float(self):
        """MetadataEncoder handles numpy float types."""
        from andor_qt.utils.metadata import MetadataEncoder

        data = {"value": np.float64(3.14159)}
        result = json.dumps(data, cls=MetadataEncoder)
        parsed = json.loads(result)

        assert abs(parsed["value"] - 3.14159) < 0.0001
        assert isinstance(parsed["value"], float)

    def test_metadata_encoder_handles_numpy_array(self):
        """MetadataEncoder handles numpy arrays."""
        from andor_qt.utils.metadata import MetadataEncoder

        data = {"values": np.array([1, 2, 3, 4, 5])}
        result = json.dumps(data, cls=MetadataEncoder)
        parsed = json.loads(result)

        assert parsed["values"] == [1, 2, 3, 4, 5]
        assert isinstance(parsed["values"], list)

    def test_metadata_encoder_handles_datetime(self):
        """MetadataEncoder handles datetime objects."""
        from andor_qt.utils.metadata import MetadataEncoder

        dt = datetime(2024, 1, 15, 14, 30, 45)
        data = {"timestamp": dt}
        result = json.dumps(data, cls=MetadataEncoder)
        parsed = json.loads(result)

        assert "2024-01-15" in parsed["timestamp"]
        assert "14:30:45" in parsed["timestamp"]


class TestSaveMetadata:
    """Tests for save_metadata function."""

    def test_save_metadata_creates_json_file(self, tmp_path):
        """save_metadata creates a .meta.json sidecar file."""
        from andor_qt.utils.metadata import save_metadata

        data_file = tmp_path / "spectrum_001.csv"
        data_file.touch()

        params = {"exposure_time": 0.5, "grating": 1}
        session_meta = {"sample_id": "SAMPLE-001", "operator": "Tester"}

        meta_path = save_metadata(data_file, params, session_meta)

        assert meta_path.exists()
        assert meta_path.suffix == ".json"
        assert "meta" in meta_path.name

    def test_metadata_file_has_version_field(self, tmp_path):
        """Metadata JSON has a version field."""
        from andor_qt.utils.metadata import save_metadata

        data_file = tmp_path / "spectrum_001.csv"
        data_file.touch()

        meta_path = save_metadata(data_file, {}, {})

        with open(meta_path) as f:
            metadata = json.load(f)

        assert "version" in metadata
        assert metadata["version"] == "1.0"

    def test_metadata_file_has_acquisition_section(self, tmp_path):
        """Metadata JSON has acquisition parameters."""
        from andor_qt.utils.metadata import save_metadata

        data_file = tmp_path / "spectrum_001.csv"
        data_file.touch()

        params = {
            "exposure_time": 0.5,
            "grating": 1,
            "center_wavelength": 550.0,
        }

        meta_path = save_metadata(data_file, params, {})

        with open(meta_path) as f:
            metadata = json.load(f)

        assert "acquisition" in metadata
        assert metadata["acquisition"]["exposure_time"] == 0.5
        assert metadata["acquisition"]["grating"] == 1
        assert metadata["acquisition"]["center_wavelength"] == 550.0

    def test_metadata_file_has_session_section(self, tmp_path):
        """Metadata JSON has session information."""
        from andor_qt.utils.metadata import save_metadata

        data_file = tmp_path / "spectrum_001.csv"
        data_file.touch()

        session_meta = {
            "sample_id": "SAMPLE-001",
            "operator": "Test User",
            "notes": "Test acquisition",
        }

        meta_path = save_metadata(data_file, {}, session_meta)

        with open(meta_path) as f:
            metadata = json.load(f)

        assert "session" in metadata
        assert metadata["session"]["sample_id"] == "SAMPLE-001"
        assert metadata["session"]["operator"] == "Test User"
        assert metadata["session"]["notes"] == "Test acquisition"

    def test_metadata_file_has_created_timestamp(self, tmp_path):
        """Metadata JSON has a creation timestamp."""
        from andor_qt.utils.metadata import save_metadata

        data_file = tmp_path / "spectrum_001.csv"
        data_file.touch()

        meta_path = save_metadata(data_file, {}, {})

        with open(meta_path) as f:
            metadata = json.load(f)

        assert "created" in metadata
        # Should be an ISO format timestamp
        assert "T" in metadata["created"] or "-" in metadata["created"]

    def test_metadata_file_has_data_file_reference(self, tmp_path):
        """Metadata JSON references the data file name."""
        from andor_qt.utils.metadata import save_metadata

        data_file = tmp_path / "spectrum_001.csv"
        data_file.touch()

        meta_path = save_metadata(data_file, {}, {})

        with open(meta_path) as f:
            metadata = json.load(f)

        assert "data_file" in metadata
        assert metadata["data_file"] == "spectrum_001.csv"


class TestLoadMetadata:
    """Tests for load_metadata function."""

    def test_load_metadata_reads_file(self, tmp_path):
        """load_metadata reads and returns metadata dict."""
        from andor_qt.utils.metadata import load_metadata, save_metadata

        data_file = tmp_path / "spectrum_001.csv"
        data_file.touch()

        params = {"exposure_time": 0.5}
        session_meta = {"sample_id": "SAMPLE-001"}

        save_metadata(data_file, params, session_meta)
        loaded = load_metadata(data_file)

        assert loaded is not None
        assert loaded["acquisition"]["exposure_time"] == 0.5
        assert loaded["session"]["sample_id"] == "SAMPLE-001"

    def test_load_metadata_returns_none_if_missing(self, tmp_path):
        """load_metadata returns None if metadata file doesn't exist."""
        from andor_qt.utils.metadata import load_metadata

        data_file = tmp_path / "nonexistent.csv"

        result = load_metadata(data_file)

        assert result is None


class TestMetadataWithNumpy:
    """Tests for metadata with numpy data types."""

    def test_save_metadata_handles_numpy_params(self, tmp_path):
        """save_metadata correctly serializes numpy values in params."""
        from andor_qt.utils.metadata import load_metadata, save_metadata

        data_file = tmp_path / "spectrum_001.csv"
        data_file.touch()

        params = {
            "exposure_time": np.float64(0.5),
            "grating": np.int32(1),
            "wavelength_range": np.array([400.0, 800.0]),
        }

        meta_path = save_metadata(data_file, params, {})

        # Should be readable as valid JSON
        with open(meta_path) as f:
            metadata = json.load(f)

        assert metadata["acquisition"]["exposure_time"] == 0.5
        assert metadata["acquisition"]["grating"] == 1
        assert metadata["acquisition"]["wavelength_range"] == [400.0, 800.0]


class TestDataSettingsMetadataFormat:
    """Tests for metadata format option in DataSettingsWidget."""

    def test_data_settings_has_metadata_combo(self, qt_app):
        """DataSettingsWidget has a metadata format combo box."""
        from andor_qt.widgets.hardware.data_settings import DataSettingsWidget

        widget = DataSettingsWidget()

        assert hasattr(widget, "_metadata_combo")
        assert widget._metadata_combo is not None

    def test_metadata_format_defaults_to_separate(self, qt_app):
        """Metadata format defaults to 'separate' (JSON sidecar)."""
        from andor_qt.widgets.hardware.data_settings import DataSettingsWidget

        widget = DataSettingsWidget()

        assert widget.metadata_format == "separate"

    def test_metadata_format_property_returns_value(self, qt_app):
        """metadata_format property returns the selected value."""
        from andor_qt.widgets.hardware.data_settings import DataSettingsWidget

        widget = DataSettingsWidget()

        # Default is 'separate'
        assert widget.metadata_format == "separate"

        # Change to 'embedded'
        index = widget._metadata_combo.findData("embedded")
        widget._metadata_combo.setCurrentIndex(index)

        assert widget.metadata_format == "embedded"

    def test_get_metadata_returns_session_info(self, qt_app):
        """get_metadata() returns session information dict."""
        from andor_qt.widgets.hardware.data_settings import DataSettingsWidget

        widget = DataSettingsWidget()
        widget.sample_id = "SAMPLE-001"
        widget.operator = "Test User"
        widget.notes = "Test notes"

        metadata = widget.get_metadata()

        assert metadata["sample_id"] == "SAMPLE-001"
        assert metadata["operator"] == "Test User"
        assert metadata["notes"] == "Test notes"
        assert "timestamp" in metadata


class TestSaveDataWithSeparateMetadata:
    """Tests for save_data with separate metadata files."""

    def test_save_csv_data_only_creates_clean_file(self, tmp_path):
        """save_csv_data_only creates CSV without comment headers."""
        import numpy as np
        from andor_qt.utils.metadata import save_metadata

        # Create test data
        wavelengths = np.linspace(400, 800, 100)
        intensities = np.random.rand(100) * 1000

        # Import the helper function we'll create
        from andor_qt.utils.data_io import save_csv_data_only

        filepath = tmp_path / "spectrum_001.csv"
        save_csv_data_only(filepath, wavelengths, intensities)

        # Read file and check format
        with open(filepath) as f:
            lines = f.readlines()

        # First line should be header (not a comment)
        assert not lines[0].startswith("#")
        assert "Wavelength" in lines[0] or "wavelength" in lines[0].lower()

    def test_save_npz_data_only_has_minimal_keys(self, tmp_path):
        """save_npz_data_only creates NPZ with only data arrays."""
        import numpy as np

        from andor_qt.utils.data_io import save_npz_data_only

        # Create test data
        wavelengths = np.linspace(400, 800, 100)
        data = np.random.rand(100)

        filepath = tmp_path / "spectrum_001.npz"
        save_npz_data_only(filepath, wavelengths, data)

        # Load and verify
        loaded = np.load(filepath)

        assert "data" in loaded
        assert "wavelengths" in loaded
        # Should not have parameter keys like exposure_time, grating, etc.
        assert "exposure_time" not in loaded
        assert "grating" not in loaded

    def test_separate_metadata_creates_two_files(self, tmp_path):
        """Saving with separate metadata creates data and .meta.json files."""
        import numpy as np

        from andor_qt.utils.data_io import save_csv_data_only
        from andor_qt.utils.metadata import save_metadata

        wavelengths = np.linspace(400, 800, 100)
        intensities = np.random.rand(100) * 1000
        params = {"exposure_time": 0.5, "grating": 1}
        session = {"sample_id": "TEST-001"}

        filepath = tmp_path / "spectrum_001.csv"
        save_csv_data_only(filepath, wavelengths, intensities)
        save_metadata(filepath, params, session)

        # Both files should exist
        assert filepath.exists()
        meta_path = filepath.with_suffix(".meta.json")
        assert meta_path.exists()
