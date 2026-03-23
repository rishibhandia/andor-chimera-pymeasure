"""Tests for CameraSettingsWidget — VS/HS speed, amplifier, EM gain, pre-amp gain,
single track and crop mode controls."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


@pytest.fixture
def widget(qt_app):
    from andor_qt.widgets.hardware.camera_settings import CameraSettingsWidget
    w = CameraSettingsWidget()
    w.show()
    return w


class TestCameraSettingsWidgetBasic:
    def test_widget_instantiates(self, qt_app):
        from andor_qt.widgets.hardware.camera_settings import CameraSettingsWidget
        w = CameraSettingsWidget()
        assert w is not None

    def test_has_vs_speed_combo(self, widget):
        assert widget.vs_speed_combo is not None
        assert isinstance(widget.vs_speed_combo, QComboBox)

    def test_vs_speed_combo_has_5_options(self, widget):
        assert widget.vs_speed_combo.count() == 5

    def test_has_hs_speed_combo(self, widget):
        assert widget.hs_speed_combo is not None
        assert isinstance(widget.hs_speed_combo, QComboBox)

    def test_hs_speed_combo_has_3_options(self, widget):
        assert widget.hs_speed_combo.count() == 3

    def test_has_amplifier_combo(self, widget):
        assert widget.amplifier_combo is not None
        assert isinstance(widget.amplifier_combo, QComboBox)

    def test_amplifier_combo_has_em_and_conventional(self, widget):
        items = [widget.amplifier_combo.itemText(i) for i in range(widget.amplifier_combo.count())]
        assert any("EM" in t for t in items)
        assert any("Conv" in t or "Conventional" in t for t in items)

    def test_has_em_gain_spinbox(self, widget):
        assert widget.em_gain_spin is not None
        assert isinstance(widget.em_gain_spin, QSpinBox)

    def test_has_preamp_gain_combo(self, widget):
        assert widget.preamp_gain_combo is not None
        assert isinstance(widget.preamp_gain_combo, QComboBox)


class TestCameraSettingsAmplifierLogic:
    def test_em_gain_enabled_when_em_selected(self, widget):
        # Select EM (index 0)
        widget.amplifier_combo.setCurrentIndex(0)
        assert widget.em_gain_spin.isEnabled()

    def test_em_gain_disabled_when_conventional_selected(self, widget):
        # Select Conventional (index 1)
        widget.amplifier_combo.setCurrentIndex(1)
        assert not widget.em_gain_spin.isEnabled()

    def test_hs_speeds_repopulated_on_amplifier_change(self, widget):
        # Both amplifier types have 3 HS speed options on DU970P
        widget.amplifier_combo.setCurrentIndex(0)
        count_em = widget.hs_speed_combo.count()
        widget.amplifier_combo.setCurrentIndex(1)
        count_conv = widget.hs_speed_combo.count()
        assert count_em == 3
        assert count_conv == 3


class TestCameraSettingsGetSettings:
    def test_get_settings_returns_dict(self, widget):
        s = widget.get_settings()
        assert isinstance(s, dict)

    def test_get_settings_has_required_keys(self, widget):
        s = widget.get_settings()
        for key in ("vs_speed_index", "hs_speed_index", "amplifier_type", "em_gain", "preamp_gain_index"):
            assert key in s, f"Missing key: {key}"

    def test_get_settings_vs_speed_index_is_int(self, widget):
        assert isinstance(widget.get_settings()["vs_speed_index"], int)

    def test_get_settings_amplifier_type_em(self, widget):
        widget.amplifier_combo.setCurrentIndex(0)
        assert widget.get_settings()["amplifier_type"] == 0

    def test_get_settings_amplifier_type_conventional(self, widget):
        widget.amplifier_combo.setCurrentIndex(1)
        assert widget.get_settings()["amplifier_type"] == 1

    def test_get_settings_em_gain_reflects_spinbox(self, widget):
        widget.amplifier_combo.setCurrentIndex(0)
        widget.em_gain_spin.setValue(200)
        assert widget.get_settings()["em_gain"] == 200

    def test_get_settings_includes_read_area_mode(self, widget):
        s = widget.get_settings()
        assert "read_area_mode" in s

    def test_get_settings_default_read_area_is_full(self, widget):
        assert widget.get_settings()["read_area_mode"] == "full"


class TestCameraSettingsSignals:
    def test_settings_changed_emits_on_vs_speed_change(self, widget):
        fired = []
        widget.settings_changed.connect(lambda: fired.append(1))
        widget.vs_speed_combo.setCurrentIndex(2)
        assert len(fired) >= 1

    def test_settings_changed_emits_on_amplifier_change(self, widget):
        fired = []
        widget.settings_changed.connect(lambda: fired.append(1))
        widget.amplifier_combo.setCurrentIndex(1)
        assert len(fired) >= 1

    def test_settings_changed_emits_on_hs_speed_change(self, widget):
        fired = []
        widget.settings_changed.connect(lambda: fired.append(1))
        widget.hs_speed_combo.setCurrentIndex(1)
        assert len(fired) >= 1


class TestCameraSettingsReadAreaMode:
    def test_has_read_area_mode_selector(self, widget):
        assert hasattr(widget, "read_area_combo")

    def test_single_track_fields_hidden_by_default(self, widget):
        assert not widget._single_track_group.isVisible()

    def test_crop_mode_fields_hidden_by_default(self, widget):
        assert not widget._crop_mode_group.isVisible()

    def test_single_track_fields_shown_when_single_track_selected(self, widget):
        idx = widget.read_area_combo.findData("single_track")
        widget.read_area_combo.setCurrentIndex(idx)
        assert widget._single_track_group.isVisible()

    def test_crop_mode_fields_shown_when_crop_selected(self, widget):
        idx = widget.read_area_combo.findData("crop")
        widget.read_area_combo.setCurrentIndex(idx)
        assert widget._crop_mode_group.isVisible()

    def test_single_track_fields_hidden_when_crop_selected(self, widget):
        idx = widget.read_area_combo.findData("crop")
        widget.read_area_combo.setCurrentIndex(idx)
        assert not widget._single_track_group.isVisible()

    def test_get_settings_single_track_returns_centre_height(self, widget):
        idx = widget.read_area_combo.findData("single_track")
        widget.read_area_combo.setCurrentIndex(idx)
        widget._st_centre_spin.setValue(80)
        widget._st_height_spin.setValue(15)
        s = widget.get_settings()
        assert s["read_area_mode"] == "single_track"
        assert s["single_track_centre"] == 80
        assert s["single_track_height"] == 15

    def test_get_settings_crop_mode_returns_dimensions(self, widget):
        idx = widget.read_area_combo.findData("crop")
        widget.read_area_combo.setCurrentIndex(idx)
        widget._crop_height_spin.setValue(20)
        widget._crop_width_spin.setValue(1600)
        s = widget.get_settings()
        assert s["read_area_mode"] == "crop"
        assert s["crop_height"] == 20
        assert s["crop_width"] == 1600


class TestCameraSettingsPopulateFromCamera:
    def test_populate_from_camera_updates_preamp_gains(self, widget):
        from unittest.mock import MagicMock
        mock_camera = MagicMock()
        mock_camera.get_preamp_gains.return_value = [(0, 1.0), (1, 2.0), (2, 4.0)]
        widget.populate_from_camera(mock_camera)
        assert widget.preamp_gain_combo.count() == 3

    def test_populate_from_camera_updates_em_gain_range(self, widget):
        from unittest.mock import MagicMock
        mock_camera = MagicMock()
        mock_camera.get_preamp_gains.return_value = [(0, 1.0)]
        mock_camera.info.em_gain_range = (1, 1000)
        widget.populate_from_camera(mock_camera)
        assert widget.em_gain_spin.minimum() == 1
        assert widget.em_gain_spin.maximum() == 1000
