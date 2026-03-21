"""Tests for TADataWriter (HDF5 output) and CSV export."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
import pytest

try:
    import h5py
    HAS_H5PY = True
except ImportError:
    HAS_H5PY = False

from andor_qt.ta.hdf5_writer import TADataWriter, auto_filename, export_csv


pytestmark = pytest.mark.skipif(not HAS_H5PY, reason="h5py not installed")


# ---------------------------------------------------------------------------
# auto_filename
# ---------------------------------------------------------------------------


class TestAutoFilename:
    def test_contains_sample_name(self, tmp_path):
        name = auto_filename("rhodamine_6g", tmp_path)
        assert "rhodamine_6g" in name

    def test_contains_TA(self, tmp_path):
        name = auto_filename("sample", tmp_path)
        assert "TA" in name

    def test_has_h5_extension(self, tmp_path):
        name = auto_filename("sample", tmp_path)
        assert name.endswith(".h5")

    def test_timestamp_format(self, tmp_path):
        name = Path(auto_filename("s", tmp_path)).name
        # YYYYMMDD_HHMMSS_TA_s.h5
        assert re.match(r"\d{8}_\d{6}_TA_", name)


# ---------------------------------------------------------------------------
# TADataWriter
# ---------------------------------------------------------------------------


class TestTADataWriter:
    def test_context_manager_creates_file(self, tmp_path):
        path = tmp_path / "test.h5"
        wavelengths = np.linspace(400.0, 800.0, 64)
        with TADataWriter(path, wavelengths=wavelengths, sample_name="test") as writer:
            pass
        assert path.exists()

    def test_writes_wavelengths_dataset(self, tmp_path):
        path = tmp_path / "test.h5"
        wavelengths = np.linspace(400.0, 800.0, 64)
        with TADataWriter(path, wavelengths=wavelengths, sample_name="test") as writer:
            pass
        with h5py.File(path, "r") as f:
            assert "wavelengths" in f
            assert np.allclose(f["wavelengths"][:], wavelengths)

    def test_writes_sample_name_metadata(self, tmp_path):
        path = tmp_path / "test.h5"
        wavelengths = np.linspace(400.0, 800.0, 10)
        with TADataWriter(path, wavelengths=wavelengths, sample_name="mytest") as writer:
            pass
        with h5py.File(path, "r") as f:
            assert f["metadata"].attrs["sample_name"] == "mytest"

    def test_begin_scan_creates_group(self, tmp_path):
        path = tmp_path / "test.h5"
        wavelengths = np.linspace(400.0, 800.0, 10)
        with TADataWriter(path, wavelengths=wavelengths, sample_name="s") as writer:
            writer.begin_scan(0)
        with h5py.File(path, "r") as f:
            assert "scan_000" in f

    def test_write_point_stores_data(self, tmp_path):
        path = tmp_path / "test.h5"
        wavelengths = np.linspace(400.0, 800.0, 10)
        delta_od = np.random.rand(10)
        with TADataWriter(path, wavelengths=wavelengths, sample_name="s") as writer:
            writer.begin_scan(0)
            writer.write_point(scan_idx=0, delay_ps=1.0, delta_od=delta_od)
        with h5py.File(path, "r") as f:
            assert "scan_000" in f
            assert "time_delays" in f["scan_000"]
            assert "delta_OD" in f["scan_000"]
            assert f["scan_000/time_delays"][0] == pytest.approx(1.0)
            assert np.allclose(f["scan_000/delta_OD"][0], delta_od)

    def test_multiple_points_per_scan(self, tmp_path):
        path = tmp_path / "test.h5"
        wavelengths = np.linspace(400.0, 800.0, 10)
        delays = [0.5, 1.0, 5.0, 10.0]
        with TADataWriter(path, wavelengths=wavelengths, sample_name="s") as writer:
            writer.begin_scan(0)
            for d in delays:
                writer.write_point(0, d, np.ones(10) * d)
        with h5py.File(path, "r") as f:
            assert len(f["scan_000/time_delays"]) == len(delays)

    def test_multiple_scans(self, tmp_path):
        path = tmp_path / "test.h5"
        wavelengths = np.linspace(400.0, 800.0, 5)
        with TADataWriter(path, wavelengths=wavelengths, sample_name="s") as writer:
            for scan in range(3):
                writer.begin_scan(scan)
                writer.write_point(scan, 1.0, np.ones(5))
        with h5py.File(path, "r") as f:
            assert "scan_000" in f
            assert "scan_001" in f
            assert "scan_002" in f

    def test_open_close_explicit(self, tmp_path):
        path = tmp_path / "test.h5"
        wavelengths = np.linspace(400.0, 800.0, 5)
        writer = TADataWriter(path, wavelengths=wavelengths, sample_name="s")
        writer.open()
        writer.begin_scan(0)
        writer.write_point(0, 1.0, np.ones(5))
        writer.finalize()
        assert path.exists()


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------


class TestExportCSV:
    def _make_h5(self, tmp_path, n_wavelengths=5, n_delays=3, n_scans=2):
        path = tmp_path / "data.h5"
        wavelengths = np.linspace(400.0, 800.0, n_wavelengths)
        with TADataWriter(path, wavelengths=wavelengths, sample_name="test") as writer:
            for scan in range(n_scans):
                writer.begin_scan(scan)
                for i in range(n_delays):
                    delay = float(i + 1)
                    writer.write_point(scan, delay, np.ones(n_wavelengths) * delay)
        return path

    def test_creates_csv(self, tmp_path):
        h5_path = self._make_h5(tmp_path)
        csv_path = tmp_path / "out.csv"
        export_csv(h5_path, csv_path)
        assert csv_path.exists()

    def test_csv_has_header(self, tmp_path):
        h5_path = self._make_h5(tmp_path)
        csv_path = tmp_path / "out.csv"
        export_csv(h5_path, csv_path)
        with open(csv_path) as f:
            reader = csv.reader(f)
            header = next(reader)
        assert "delay_ps" in header[0]

    def test_csv_column_count(self, tmp_path):
        n_wl = 5
        h5_path = self._make_h5(tmp_path, n_wavelengths=n_wl)
        csv_path = tmp_path / "out.csv"
        export_csv(h5_path, csv_path)
        with open(csv_path) as f:
            reader = csv.reader(f)
            header = next(reader)
        # delay_ps + n_wavelengths columns
        assert len(header) == 1 + n_wl
