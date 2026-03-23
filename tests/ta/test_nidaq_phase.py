"""Tests for NIDAQPhaseReader and MockNIDAQPhaseReader.

All tests use MockNIDAQPhaseReader — no NI hardware required.
The real NIDAQPhaseReader is exercised only when nidaqmx is importable
and NI hardware is present.
"""

from __future__ import annotations

import numpy as np
import pytest

from andor_qt.ta.nidaq_phase import MockNIDAQPhaseReader, NIDAQPhaseReader


# ---------------------------------------------------------------------------
# MockNIDAQPhaseReader
# ---------------------------------------------------------------------------


class TestMockNIDAQPhaseReaderDefaults:
    def test_creates_without_args(self):
        reader = MockNIDAQPhaseReader()
        assert reader is not None

    def test_default_pattern_alternates(self):
        reader = MockNIDAQPhaseReader()
        reader.start()
        tags = reader.read_tags(4)
        assert list(tags) == [1, 0, 1, 0]

    def test_pattern_continues_across_calls(self):
        reader = MockNIDAQPhaseReader()
        reader.start()
        first = reader.read_tags(2)
        second = reader.read_tags(2)
        assert list(first) == [1, 0]
        assert list(second) == [1, 0]

    def test_read_one_returns_single_int(self):
        reader = MockNIDAQPhaseReader()
        reader.start()
        tag = reader.read_one()
        assert tag in (0, 1)

    def test_read_one_advances_state(self):
        reader = MockNIDAQPhaseReader()
        reader.start()
        t0 = reader.read_one()
        t1 = reader.read_one()
        assert t0 != t1

    def test_stop_is_safe(self):
        reader = MockNIDAQPhaseReader()
        reader.start()
        reader.stop()  # must not raise

    def test_context_manager(self):
        with MockNIDAQPhaseReader() as reader:
            tags = reader.read_tags(2)
        assert len(tags) == 2


class TestMockNIDAQPhaseReaderCustomPattern:
    def test_custom_pattern_repeats(self):
        # Pattern starts at pump-off
        reader = MockNIDAQPhaseReader(initial_phase=0)
        reader.start()
        tags = reader.read_tags(4)
        assert list(tags) == [0, 1, 0, 1]

    def test_large_read(self):
        reader = MockNIDAQPhaseReader()
        reader.start()
        tags = reader.read_tags(1000)
        assert len(tags) == 1000
        # All values must be 0 or 1
        assert set(tags).issubset({0, 1})
        # Must alternate strictly
        diffs = np.diff(tags.astype(int))
        assert np.all(np.abs(diffs) == 1)

    def test_returns_numpy_array(self):
        reader = MockNIDAQPhaseReader()
        reader.start()
        tags = reader.read_tags(4)
        assert isinstance(tags, np.ndarray)

    def test_dtype_is_int(self):
        reader = MockNIDAQPhaseReader()
        reader.start()
        tags = reader.read_tags(4)
        assert np.issubdtype(tags.dtype, np.integer)


# ---------------------------------------------------------------------------
# NIDAQPhaseReader interface contract (mock-backed)
# ---------------------------------------------------------------------------


class TestNIDAQPhaseReaderInterface:
    """Verify NIDAQPhaseReader exposes the expected public API."""

    def test_has_start(self):
        assert callable(NIDAQPhaseReader.start)

    def test_has_stop(self):
        assert callable(NIDAQPhaseReader.stop)

    def test_has_read_tags(self):
        assert callable(NIDAQPhaseReader.read_tags)

    def test_has_read_one(self):
        assert callable(NIDAQPhaseReader.read_one)

    def test_is_context_manager(self):
        assert hasattr(NIDAQPhaseReader, "__enter__")
        assert hasattr(NIDAQPhaseReader, "__exit__")


# ---------------------------------------------------------------------------
# Integration: MockNIDAQPhaseReader + ChopperSync
# ---------------------------------------------------------------------------


class TestPhaseReaderWithChopperSync:
    def test_tags_split_correctly(self):
        from andor_qt.ta.chopper import ChopperSync

        reader = MockNIDAQPhaseReader()
        reader.start()
        tags = reader.read_tags(6)  # [1,0,1,0,1,0]

        spectra = np.arange(6 * 10).reshape(6, 10).astype(float)
        chopper = ChopperSync(mode="hardware")
        on_list, off_list = chopper.tag_shots(spectra, tags)

        assert len(on_list) == 3
        assert len(off_list) == 3
        # on_list rows should match even indices (tags==1)
        np.testing.assert_array_equal(on_list[0], spectra[0])
        np.testing.assert_array_equal(off_list[0], spectra[1])

    def test_phase_inverted_splits_correctly(self):
        from andor_qt.ta.chopper import ChopperSync

        reader = MockNIDAQPhaseReader(initial_phase=0)  # starts pump-off
        reader.start()
        tags = reader.read_tags(4)  # [0,1,0,1]

        spectra = np.ones((4, 10))
        chopper = ChopperSync(mode="hardware")
        on_list, off_list = chopper.tag_shots(spectra, tags)

        assert len(on_list) == 2
        assert len(off_list) == 2
