"""Tests für PDF-Export und UI-Helfer."""
from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("PySide6")
try:
    from playwright.sync_api import sync_playwright  # type: ignore import
except ImportError as exc:
    pytest.skip(f"Playwright unavailable: {exc}", allow_module_level=True)
else:
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium unavailable: {exc}", allow_module_level=True)
            else:
                browser.close()
    except Exception as exc:
        pytest.skip(f"Playwright initialization failed: {exc}", allow_module_level=True)

from wtc3_logger.status import decode_status

try:  # pragma: no cover - Abhängigkeiten fehlen ggf. im CI
    from wtc3_logger.ui.main_window import ParameterSetting, ParameterSidebar
except ImportError as exc:  # pragma: no cover
    pytest.skip(f"UI-Komponenten nicht verfügbar: {exc}", allow_module_level=True)

from wtc3_logger.ui.pdf_report import ParameterSeries, ParameterStatistic, StatusMarker, render_measurement_report


def test_render_measurement_report_creates_pdf(tmp_path, qapp):
    target = tmp_path / "protokoll.pdf"

    meta = {
        "P04": "CC_CV",
        "P07": "Halter",
        "P08": "Lademodul",
    }
    status_detail = decode_status(31248)

    visible_stats = [
        ParameterStatistic(
            key="P40",
            label="Eingangsspannung",
            unit="mV",
            min_value=1000.0,
            max_value=2000.0,
            last_value=1800.0,
            color="#ff0000",
            visible=True,
        )
    ]

    series = [
        ParameterSeries(
            key="P40",
            label="Eingangsspannung",
            unit="mV",
            color="#ff0000",
            x_values=(0.0, 60.0, 125.5),
            y_values=(1000.0, 1500.0, 1800.0),
            explanation="Input voltage across the measured duration.",
        )
    ]
    markers = [StatusMarker(position=60.0, label="Batteriespannung: Tief -> Normal")]

    render_measurement_report(
        target,
        meta,
        31248,
        status_detail,
        meta["P04"],
        "CC-CV",
        visible_stats,
        [],
        series,
        markers,
        sample_count=3,
        duration_seconds=125.5,
        x_axis_caption="P06 – Laufzeit",
        x_axis_unit="s",
        start_x=0.0,
        end_x=125.5,
        generated_at=datetime(2023, 1, 1, 12, 0, 0),
    )

    assert target.exists()
    assert target.read_bytes().startswith(b"%PDF")


def test_parameter_sidebar_adjusts_width(tmp_path, qapp):
    sidebar = ParameterSidebar()
    short = ParameterSetting(
        key="P40",
        label="Kurz",
        unit="mV",
        color="#123456",
        visible=True,
    )
    sidebar.populate([short])
    qapp.processEvents()
    base_width = sidebar.minimumWidth()

    long = ParameterSetting(
        key="P41",
        label="Sehr langer Parametername zur Breitenmessung",
        unit="mV",
        color="#654321",
        visible=True,
    )
    sidebar.populate([long])
    qapp.processEvents()

    assert sidebar.minimumWidth() >= base_width
