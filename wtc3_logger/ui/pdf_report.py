"""Erzeuge ein Messprotokoll als PDF im WeTech-Stil."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import html
from pathlib import Path
from typing import Dict, Iterable, Sequence

from PySide6 import QtCore, QtGui
from PySide6.QtPrintSupport import QPrinter

from ..parser import PARAMETERS, Number
from ..status import StatusDetail
from . import colors


@dataclass(slots=True)
class ParameterStatistic:
    """Kennzahlen zu einem gemessenen Parameter."""

    key: str
    label: str
    unit: str | None
    min_value: float
    max_value: float
    last_value: float
    color: str
    visible: bool


def _format_number(value: float) -> str:
    text = ("%.3f" % value).rstrip("0").rstrip(".")
    return text if text else "0"


def _format_value(value: float | None, unit: str | None) -> str:
    if value is None:
        return "–"
    text = _format_number(value)
    if unit:
        return f"{text} {html.escape(unit)}"
    return text


def _format_meta_value(key: str, raw: str) -> str:
    info = PARAMETERS.get(key)
    if not info:
        return html.escape(str(raw))
    casted = info.cast(raw)
    if isinstance(casted, (int, float)):
        formatted = _format_number(float(casted))
    else:
        formatted = html.escape(str(casted))
    if info.unit:
        return f"{formatted} {html.escape(info.unit)}"
    return formatted


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "–"
    if seconds < 60:
        return f"{seconds:.1f} s"
    delta = timedelta(seconds=seconds)
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d} h"
    return f"{minutes:02d}:{secs:02d} min"


def _build_meta_rows(meta: Dict[str, str], status_value: Number | str | None) -> Iterable[tuple[str, str]]:
    for key in sorted(meta.keys()):
        info = PARAMETERS.get(key)
        label = f"{key} – {info.description}" if info and info.description else key
        yield label, _format_meta_value(key, meta[key])
    if status_value is not None:
        label = "P05 – Statuswort"
        yield label, html.escape(str(status_value))


def _build_parameter_table_rows(stats: Sequence[ParameterStatistic]) -> str:
    rows: list[str] = []
    for stat in stats:
        color_box = (
            f"<span style=\"display:inline-block;width:10px;height:10px;border-radius:5px;background:{html.escape(stat.color)};margin-right:6px;\"></span>"
            if stat.color
            else ""
        )
        unit = html.escape(stat.unit) if stat.unit else "–"
        rows.append(
            "<tr>"
            f"<td>{color_box}{html.escape(stat.key)}</td>"
            f"<td>{html.escape(stat.label)}</td>"
            f"<td>{unit}</td>"
            f"<td>{_format_number(stat.min_value)}</td>"
            f"<td>{_format_number(stat.max_value)}</td>"
            f"<td>{_format_number(stat.last_value)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_measurement_report(
    path: Path | str,
    meta: Dict[str, str],
    status_value: Number | str | None,
    status_detail: StatusDetail | None,
    strategy_code: str | None,
    strategy_label: str | None,
    visible_stats: Sequence[ParameterStatistic],
    hidden_stats: Sequence[ParameterStatistic],
    sample_count: int,
    duration_seconds: float,
    x_axis_caption: str,
    x_axis_unit: str | None,
    start_x: float | None,
    end_x: float | None,
    generated_at: datetime,
) -> None:
    """Exportiere einen Messbericht als PDF."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    doc = QtGui.QTextDocument()
    doc.setDefaultFont(QtGui.QFont("Segoe UI", 10))

    meta_rows_html = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{value}</td></tr>"
        for label, value in _build_meta_rows(meta, status_value)
    )

    status_details_html = """<p>Keine weiteren Statusdetails verfügbar.</p>"""
    if status_detail and status_detail.details:
        items = "".join(f"<li>{html.escape(text)}</li>" for text in status_detail.details)
        status_details_html = f"<ul>{items}</ul>"

    badges_html = """<p>–</p>"""
    if status_detail and status_detail.badges:
        badges_html = "".join(
            f"<span style=\"background:{colors.PRIMARY_DARK};color:white;border-radius:12px;padding:4px 10px;margin-right:6px;\">{html.escape(badge)}</span>"
            for badge in status_detail.badges
        )

    visible_table_rows = _build_parameter_table_rows(visible_stats)
    hidden_table_rows = _build_parameter_table_rows(hidden_stats)

    start_text = _format_value(start_x, x_axis_unit)
    end_text = _format_value(end_x, x_axis_unit)
    duration_text = _format_duration(duration_seconds)
    timestamp_text = generated_at.strftime("%d.%m.%Y %H:%M:%S")

    strategy_parts = []
    if strategy_label:
        strategy_parts.append(f"<strong>Strategie:</strong> {html.escape(strategy_label)}")
    if strategy_code:
        strategy_parts.append(f"<strong>Code:</strong> {html.escape(strategy_code)}")
    strategy_line = " &nbsp;•&nbsp; ".join(strategy_parts) if strategy_parts else "<strong>Strategie:</strong> –"

    html_content = f"""
    <html>
    <head>
    <meta charset='utf-8'>
    <style>
    body {{ font-family: 'Segoe UI', sans-serif; color: {colors.TEXT}; }}
    h1 {{ color: {colors.PRIMARY}; font-size: 26px; margin-bottom: 4px; }}
    h2 {{ color: {colors.PRIMARY_DARK}; font-size: 18px; margin-top: 28px; margin-bottom: 8px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border-bottom: 1px solid {colors.PRIMARY_LIGHT}; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ width: 30%; background: {colors.BACKGROUND}; font-weight: 600; }}
    .stats-table th {{ background: {colors.PRIMARY}; color: white; }}
    .stats-table td {{ border-bottom: 1px solid {colors.PRIMARY_LIGHT}; }}
    .meta-table th {{ width: 35%; }}
    .meta-table td {{ width: 65%; }}
    .header-meta {{ margin-top: 4px; color: {colors.MUTED_TEXT}; }}
    .badges {{ margin-top: 6px; }}
    .info-grid {{ display: table; width: 100%; margin-top: 6px; }}
    .info-grid span {{ display: table-cell; padding-right: 16px; color: {colors.MUTED_TEXT}; }}
    </style>
    </head>
    <body>
    <h1>Messprotokoll</h1>
    <div class='header-meta'>Erstellt am {timestamp_text}</div>
    <div class='info-grid'>
        <span><strong>Messpunkte:</strong> {sample_count}</span>
        <span><strong>Dauer:</strong> {duration_text}</span>
        <span><strong>X-Achse:</strong> {html.escape(x_axis_caption)}</span>
        <span><strong>Start:</strong> {start_text}</span>
        <span><strong>Ende:</strong> {end_text}</span>
    </div>

    <h2>Geräteinformationen</h2>
    <p>{strategy_line}</p>
    <table class='meta-table'>
        {meta_rows_html}
    </table>

    <h2>Status</h2>
    <div class='badges'>{badges_html}</div>
    {status_details_html}

    <h2>Parameter in Diagrammen</h2>
    <table class='stats-table'>
        <tr><th>Parameter</th><th>Beschreibung</th><th>Einheit</th><th>Min</th><th>Max</th><th>Letzter Wert</th></tr>
        {visible_table_rows or '<tr><td colspan="6">Keine Parameter aktiv.</td></tr>'}
    </table>

    <h2>Weitere überwachte Parameter</h2>
    <table class='stats-table'>
        <tr><th>Parameter</th><th>Beschreibung</th><th>Einheit</th><th>Min</th><th>Max</th><th>Letzter Wert</th></tr>
        {hidden_table_rows or '<tr><td colspan="6">Keine zusätzlichen Parameter aufgezeichnet.</td></tr>'}
    </table>
    </body>
    </html>
    """

    doc.setHtml(html_content)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setPageSize(QtGui.QPageSize(QtGui.QPageSize.PageSizeId.A4))
    printer.setPageMargins(QtCore.QMarginsF(12, 16, 12, 16))
    printer.setOutputFileName(str(target))

    doc.setPageSize(QtCore.QSizeF(printer.pageRect().size()))
    doc.print(printer)


__all__ = ["ParameterStatistic", "render_measurement_report"]
