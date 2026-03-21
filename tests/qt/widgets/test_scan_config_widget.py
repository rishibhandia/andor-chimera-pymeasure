"""Tests for TAScanConfigWidget."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from andor_qt.widgets.ta.scan_config_widget import TAScanConfigWidget
from andor_qt.ta.scan_config import TAScanConfig


@pytest.fixture
def widget(qt_app):
    w = TAScanConfigWidget()
    yield w
    w.deleteLater()


class TestTAScanConfigWidgetCreation:
    def test_creates_successfully(self, qt_app):
        w = TAScanConfigWidget()
        assert w is not None
        w.deleteLater()

    def test_has_tab_widget(self, widget):
        from PySide6.QtWidgets import QTabWidget
        tabs = widget.findChildren(QTabWidget)
        assert len(tabs) >= 1

    def test_has_n_averages_field(self, widget):
        assert widget.n_averages_spin is not None

    def test_has_n_scans_field(self, widget):
        assert widget.n_scans_spin is not None

    def test_has_sample_name_field(self, widget):
        assert widget.sample_name_edit is not None

    def test_has_preview_label(self, widget):
        assert widget.preview_label is not None

    def test_has_scan_button(self, widget):
        assert widget.scan_button is not None


class TestTAScanConfigWidgetDefaults:
    def test_default_n_averages(self, widget):
        assert widget.n_averages_spin.value() >= 1

    def test_default_n_scans(self, widget):
        assert widget.n_scans_spin.value() >= 1

    def test_preview_shows_delay_count(self, widget):
        text = widget.preview_label.text()
        assert "delay" in text.lower() or "point" in text.lower()


class TestTAScanConfigWidgetSignal:
    def test_scan_requested_signal_exists(self, widget):
        assert hasattr(widget, "scan_requested")

    def test_scan_button_emits_scan_requested(self, widget):
        emitted = []
        widget.scan_requested.connect(lambda cfg: emitted.append(cfg))
        widget.scan_button.click()
        assert len(emitted) == 1

    def test_scan_requested_emits_ta_scan_config(self, widget):
        emitted = []
        widget.scan_requested.connect(lambda cfg: emitted.append(cfg))
        widget.scan_button.click()
        assert isinstance(emitted[0], TAScanConfig)

    def test_config_uses_n_averages(self, widget):
        widget.n_averages_spin.setValue(5)
        emitted = []
        widget.scan_requested.connect(lambda cfg: emitted.append(cfg))
        widget.scan_button.click()
        assert emitted[0].n_averages == 5

    def test_config_uses_sample_name(self, widget):
        widget.sample_name_edit.setText("my_sample")
        emitted = []
        widget.scan_requested.connect(lambda cfg: emitted.append(cfg))
        widget.scan_button.click()
        assert emitted[0].sample_name == "my_sample"


class TestTAScanConfigWidgetYAML:
    def test_save_load_roundtrip(self, widget, tmp_path):
        widget.n_averages_spin.setValue(7)
        widget.sample_name_edit.setText("roundtrip_test")

        path = tmp_path / "config.yaml"
        widget.save_config(str(path))
        assert path.exists()

        widget.n_averages_spin.setValue(1)
        widget.sample_name_edit.setText("")
        widget.load_config(str(path))

        assert widget.n_averages_spin.value() == 7
        assert widget.sample_name_edit.text() == "roundtrip_test"
