"""Smoke tests for Qt widgets.

These tests verify that widgets can be instantiated without errors.
They do not test functionality, just that the classes load correctly.
"""

from __future__ import annotations

import pytest


class TestWidgetInstantiation:
    """Test that widgets can be instantiated."""

    def test_spectrograph_control_widget(self, hardware_manager, qt_app):
        """SpectrographControlWidget can be instantiated."""
        from andor_qt.widgets.hardware.spectrograph_control import SpectrographControlWidget

        widget = SpectrographControlWidget(hardware_manager)
        assert widget is not None
        assert widget.windowTitle() == ""  # QGroupBox doesn't set window title

    def test_temperature_control_widget(self, hardware_manager, qt_app):
        """TemperatureControlWidget can be instantiated."""
        from andor_qt.widgets.hardware.temperature_control import TemperatureControlWidget

        widget = TemperatureControlWidget(hardware_manager)
        assert widget is not None

    def test_data_settings_widget(self, qt_app):
        """DataSettingsWidget can be instantiated."""
        from andor_qt.widgets.hardware.data_settings import DataSettingsWidget

        widget = DataSettingsWidget()
        assert widget is not None

    def test_spectrum_plot_widget(self, qt_app):
        """SpectrumPlotWidget can be instantiated."""
        from andor_qt.widgets.display.spectrum_plot import SpectrumPlotWidget

        widget = SpectrumPlotWidget()
        assert widget is not None

    def test_image_plot_widget(self, qt_app):
        """ImagePlotWidget can be instantiated."""
        from andor_qt.widgets.display.image_plot import ImagePlotWidget

        widget = ImagePlotWidget()
        assert widget is not None

    def test_results_table_widget(self, qt_app):
        """ResultsTableWidget can be instantiated."""
        from andor_qt.widgets.display.results_table import ResultsTableWidget

        widget = ResultsTableWidget()
        assert widget is not None

    def test_dynamic_inputs_widget(self, qt_app):
        """DynamicInputsWidget can be instantiated."""
        from andor_qt.widgets.inputs.dynamic_inputs import DynamicInputsWidget

        widget = DynamicInputsWidget()
        assert widget is not None

    def test_queue_control_widget(self, qt_app):
        """QueueControlWidget can be instantiated."""
        from andor_qt.widgets.inputs.queue_control import QueueControlWidget

        widget = QueueControlWidget()
        assert widget is not None


class TestWidgetModuleImports:
    """Test that widget modules can be imported."""

    def test_hardware_widgets_import(self):
        """Hardware widget module can be imported."""
        from andor_qt.widgets import hardware
        assert hardware is not None

    def test_display_widgets_import(self):
        """Display widget module can be imported."""
        from andor_qt.widgets import display
        assert display is not None

    def test_input_widgets_import(self):
        """Input widget module can be imported."""
        from andor_qt.widgets import inputs
        assert inputs is not None
