"""Tests for apply_camera_settings hbin/vbin/trigger_mode and get_spectrum."""

from __future__ import annotations
import numpy as np
import pytest


@pytest.fixture
def cam(initialized_camera):
    """Initialized camera with mock SDK."""
    return initialized_camera


class TestGetSpectrum:
    def test_get_spectrum_returns_ndarray(self, cam):
        result = cam.get_spectrum()
        assert isinstance(result, np.ndarray)

    def test_get_spectrum_default_length(self, cam):
        result = cam.get_spectrum()
        assert len(result) == cam.xpixels

    def test_get_spectrum_with_hbin_2(self, cam):
        cam.apply_camera_settings({"hbin": 2})
        result = cam.get_spectrum()
        assert len(result) == cam.xpixels // 2

    def test_get_spectrum_resets_after_hbin_1(self, cam):
        cam.apply_camera_settings({"hbin": 2})
        cam.apply_camera_settings({"hbin": 1})
        result = cam.get_spectrum()
        assert len(result) == cam.xpixels


class TestApplyCameraSettingsHbin:
    def test_hbin_stored_on_camera(self, cam):
        cam.apply_camera_settings({"hbin": 4})
        assert cam._current_hbin == 4

    def test_hbin_default_is_1(self, cam):
        cam.apply_camera_settings({})
        assert cam._current_hbin == 1


class TestApplyCameraSettingsTriggerMode:
    def test_trigger_internal_sets_sdk_0(self, cam):
        cam.apply_camera_settings({"trigger_mode": "internal"})
        assert cam._sdk._state.trigger_mode == 0

    def test_trigger_external_sets_sdk_1(self, cam):
        cam.apply_camera_settings({"trigger_mode": "external"})
        assert cam._sdk._state.trigger_mode == 1

    def test_missing_trigger_key_does_not_change_mode(self, cam):
        cam.apply_camera_settings({"trigger_mode": "external"})
        cam.apply_camera_settings({"hbin": 1})  # no trigger_mode key
        assert cam._sdk._state.trigger_mode == 1


class TestApplyCameraSettingsCropBinning:
    def test_crop_mode_passes_hbin_vbin_to_sdk(self, cam):
        cam.apply_camera_settings({
            "read_area_mode": "crop",
            "crop_height": 20,
            "crop_width": 800,
            "hbin": 2,
            "vbin": 4,
        })
        state = cam._sdk._state
        assert state.hbin == 2
        assert state.vbin == 4
        assert state.crop_mode_active


class TestGetReadoutTime:
    def test_get_readout_time_returns_float(self, cam):
        t = cam.get_readout_time()
        assert isinstance(t, float)

    def test_get_readout_time_positive(self, cam):
        t = cam.get_readout_time()
        assert t > 0

    def test_get_readout_time_fvb_3mhz_under_2ms(self, cam):
        cam.apply_camera_settings({"vs_speed_index": 0, "hs_speed_index": 0})
        t_ms = cam.get_readout_time() * 1000.0
        assert t_ms < 2.0

    def test_get_readout_time_crop_faster_than_full(self, cam):
        cam.apply_camera_settings({"read_area_mode": "full"})
        t_full = cam.get_readout_time()
        cam.apply_camera_settings({
            "read_area_mode": "crop", "crop_height": 20, "crop_width": 1600,
            "hbin": 1, "vbin": 1,
        })
        t_crop = cam.get_readout_time()
        assert t_crop < t_full

    def test_get_readout_time_hbin2_faster_than_hbin1(self, cam):
        cam.apply_camera_settings({"hbin": 1, "hs_speed_index": 2})
        t1 = cam.get_readout_time()
        cam.apply_camera_settings({"hbin": 2, "hs_speed_index": 2})
        t2 = cam.get_readout_time()
        assert t2 < t1
