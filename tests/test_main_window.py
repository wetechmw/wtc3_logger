"""Tests für das Hauptfenster."""
from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("PySide6", reason="PySide6 nicht verfügbar", exc_type=ImportError)
pytest.importorskip("pyqtgraph", reason="pyqtgraph nicht verfügbar", exc_type=ImportError)

from wtc3_logger.config import AppConfig
from wtc3_logger.databus import DataBus
from wtc3_logger.ui.main_window import MainWindow


def _create_window(qapp: object) -> MainWindow:
    del qapp  # wird nur benötigt, um die QApplication zu initialisieren
    databus = DataBus()
    config = AppConfig()
    window = MainWindow(databus, config)
    return window


def test_voltage_axis_starts_at_zero(qapp) -> None:
    window = _create_window(qapp)
    try:
        setting = window._parameter_settings["P45"]
        window._parameter_settings["P45"] = replace(setting, visible=True)
        window._update_plot_visibility()

        x_data = [0.0, 1.0]
        records = [{"P45": 4.0}, {"P45": 4.5}]
        window._update_curves(x_data, records)

        y_min, y_max = window._unit_plots["V"].plot.getPlotItem().viewRange()[1]
        assert y_min == pytest.approx(0.0)
        assert y_max >= 4.5
    finally:
        window.close()


def test_temperature_axis_uses_meta_limits(qapp) -> None:
    window = _create_window(qapp)
    try:
        meta = {"P73": "0", "P74": "100", "P75": "350", "P76": "450"}
        window._handle_meta_parameters(meta)

        setting = window._parameter_settings["P60"]
        window._parameter_settings["P60"] = replace(setting, visible=True)
        window._update_plot_visibility()

        x_data = [0.0, 1.0]
        records = [{"P60": 21.0}, {"P60": 24.0}]
        window._update_curves(x_data, records)

        y_min, y_max = window._unit_plots["°C"].plot.getPlotItem().viewRange()[1]
        assert y_min == pytest.approx(0.0)
        assert y_max == pytest.approx(45.0)
    finally:
        window.close()
