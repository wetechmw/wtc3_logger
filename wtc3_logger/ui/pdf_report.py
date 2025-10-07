"""Generate a measurement report PDF in the WeTech style."""
from __future__ import annotations

import base64
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
import html
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


from ..parser import PARAMETERS, Number
from ..status import StatusDetail


# Pantone palette approximated in sRGB hex
PALETTE = {
    "primary": "#0083CA",      # Pantone P 109-8 C
    "primary_light": "#4BA7E9",
    "neutral": "#545456",      # Pantone P 7-7 C
    "highlight": "#FFD64B",    # Pantone P 179-1 C
    "accent": "#EE263C",       # Pantone P 179-13 C
    "accent_light": "#F36C7D",
    "background": "#FFFFFF",
}

SVG_WIDTH = 880
SVG_HEIGHT = 340
SVG_MARGIN_LEFT = 70
SVG_MARGIN_RIGHT = 36
SVG_MARGIN_TOP = 36
SVG_MARGIN_BOTTOM = 60
GRID_LINES_X = 6
GRID_LINES_Y = 5

DEFAULT_META_GROUPS: Dict[str, set[str]] = {
    "Charger": {"P04", "P05", "P07", "P08"},
    "Battery": {"P70", "P71", "P77", "P78", "P79", "P80", "P81"},
    "Thermal Window": {"P73", "P74", "P75", "P76"},
    "Limits": {"P72", "P90", "P91", "P92"},
}
DEFAULT_META_ORDER: List[str] = [
    "Charger",
    "Battery",
    "Thermal Window",
    "Limits",
    "Additional Details",
]


def _ensure_playwright_browsers_path() -> None:
    env_var = "PLAYWRIGHT_BROWSERS_PATH"
    if os.environ.get(env_var):
        return
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(getattr(sys, "_MEIPASS")) / "playwright-browsers")
    candidates.append(Path.cwd() / "playwright-browsers")
    candidates.append(Path(__file__).resolve().parents[2] / "playwright-browsers")
    for candidate in candidates:
        if candidate.exists():
            os.environ[env_var] = str(candidate)
            break


@dataclass(slots=True)
class ParameterStatistic:
    """Key metrics for a measured parameter."""

    key: str
    label: str
    unit: str | None
    min_value: float
    max_value: float
    last_value: float
    color: str
    visible: bool


@dataclass(slots=True)
class StatusMarker:
    """Marker highlighting a status transition on the x axis."""

    position: float
    label: str


@dataclass(slots=True)
class ParameterSeries:
    """Time series that will be rendered inside the PDF."""

    key: str
    label: str
    unit: str | None
    color: str
    x_values: Sequence[float]
    y_values: Sequence[float]
    explanation: str


def _format_number(value: float) -> str:
    text = ("%.3f" % value).rstrip("0").rstrip(".")
    return text if text else "0"


def _format_value(value: float | None, unit: str | None) -> str:
    if value is None:
        return "-"
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


def _meta_label(key: str) -> str:
    info = PARAMETERS.get(key)
    if info and info.description:
        return f"{key} - {info.description}"
    return key


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "-"
    if seconds < 60:
        return f"{seconds:.1f} s"
    delta = timedelta(seconds=seconds)
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d} h"
    return f"{minutes:02d}:{secs:02d} min"


def _build_parameter_table_rows(stats: Sequence[ParameterStatistic]) -> str:
    rows: List[str] = []
    for stat in stats:
        color_box = (
            f"<span style='display:inline-block;width:10px;height:10px;border-radius:5px;background:{html.escape(stat.color)};margin-right:6px;'></span>"
            if stat.color
            else ""
        )
        unit = html.escape(stat.unit) if stat.unit else "-"
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


def _build_meta_blocks(meta: Dict[str, str], status_value: Number | str | None) -> str:
    grouped: Dict[str, List[tuple[str, str]]] = {title: [] for title in DEFAULT_META_ORDER}
    for key in sorted(meta.keys()):
        value = meta[key]
        section = next((title for title, keys in DEFAULT_META_GROUPS.items() if key in keys), "Additional Details")
        grouped.setdefault(section, []).append((_meta_label(key), _format_meta_value(key, value)))
    if status_value is not None:
        grouped.setdefault("Charger", []).append(("P05 - Status Word", html.escape(str(status_value))))
    blocks: List[str] = []
    for title in DEFAULT_META_ORDER:
        entries = grouped.get(title, [])
        if not entries or title == "Additional Details":
            continue
        entries_html = "".join(
            f"<dt class='meta-term'>{html.escape(label)}</dt><dd class='meta-detail'>{value}</dd>"
            for label, value in entries
        )
        blocks.append(
            "<div class='meta-block'>"
            f"<div class='meta-block-title'>{html.escape(title)}</div>"
            f"<dl class='meta-grid'>{entries_html}</dl>"
            "</div>"
        )
    return "".join(blocks)


def _load_logo_data() -> str | None:
    root = Path(__file__).resolve().parents[2]
    for name in ("wetech_logo.svg", "wetech_logo.png"):
        logo_path = root / "assets" / name
        if logo_path.exists():
            encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
            mime = "image/svg+xml" if logo_path.suffix.lower() == ".svg" else "image/png"
            return f"data:{mime};base64,{encoded}"
    return None


def _to_svg_coords(xs: Sequence[float], ys: Sequence[float]):
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    if x_max - x_min < 1e-9:
        x_min -= 1.0
        x_max += 1.0
    if y_max - y_min < 1e-9:
        y_min -= 1.0
        y_max += 1.0
    width = SVG_WIDTH - SVG_MARGIN_LEFT - SVG_MARGIN_RIGHT
    height = SVG_HEIGHT - SVG_MARGIN_TOP - SVG_MARGIN_BOTTOM

    def sx(x: float) -> float:
        return SVG_MARGIN_LEFT + (x - x_min) * width / (x_max - x_min)

    def sy(y: float) -> float:
        return SVG_MARGIN_TOP + height - (y - y_min) * height / (y_max - y_min)

    return sx, sy, (x_min, x_max, y_min, y_max)


def _render_chart_svg(
    series: ParameterSeries,
    markers: Sequence[StatusMarker],
    x_caption: str,
    x_unit: str | None,
) -> str:
    xs = list(series.x_values)
    ys = list(series.y_values)
    if len(xs) < 2 or len(ys) < 2:
        return ""

    is_temperature = False
    unit_text = (series.unit or "").lower()
    if "°c" in unit_text or unit_text.strip() in {"c", "degc"}:
        is_temperature = True
    if "temp" in series.label.lower():
        is_temperature = True

    raw_min = min(ys)
    raw_max = max(ys)
    if is_temperature:
        y_min = -20.0
        y_max = 80.0
    else:
        y_min = min(raw_min, 0.0)
        y_max = max(raw_max, 0.0)
        if raw_max > y_min:
            y_max = max(y_max, y_min + (raw_max - y_min) * 1.1)
    if y_max - y_min < 1e-6:
        y_max = y_min + 1.0

    x_min = xs[0]
    x_max = xs[-1]
    width = SVG_WIDTH - SVG_MARGIN_LEFT - SVG_MARGIN_RIGHT
    height = SVG_HEIGHT - SVG_MARGIN_TOP - SVG_MARGIN_BOTTOM

    def sx(value: float) -> float:
        span = x_max - x_min
        if span <= 0:
            span = 1.0
        return SVG_MARGIN_LEFT + (value - x_min) * width / span

    def sy(value: float) -> float:
        span = y_max - y_min
        if span <= 0:
            span = 1.0
        return SVG_MARGIN_TOP + height - (value - y_min) * height / span

    grid_elements: List[str] = []
    for i in range(GRID_LINES_Y + 1):
        y_value = y_min + (y_max - y_min) * i / GRID_LINES_Y
        y = sy(y_value)
        grid_elements.append(
            f"<line x1='{SVG_MARGIN_LEFT:.2f}' y1='{y:.2f}' x2='{SVG_WIDTH - SVG_MARGIN_RIGHT:.2f}' y2='{y:.2f}' stroke='{PALETTE['neutral']}' stroke-width='0.6' stroke-dasharray='2 4' />"
        )
        grid_elements.append(
            f"<text x='{SVG_MARGIN_LEFT - 8:.2f}' y='{y + 4:.2f}' text-anchor='end' font-size='10' fill='{PALETTE['neutral']}'>{html.escape(_format_number(y_value))}</text>"
        )

    for i in range(GRID_LINES_X + 1):
        x_value = x_min + (x_max - x_min) * i / GRID_LINES_X
        x = sx(x_value)
        grid_elements.append(
            f"<line x1='{x:.2f}' y1='{SVG_MARGIN_TOP:.2f}' x2='{x:.2f}' y2='{SVG_HEIGHT - SVG_MARGIN_BOTTOM:.2f}' stroke='{PALETTE['neutral']}' stroke-width='0.6' stroke-dasharray='2 4' />"
        )
        grid_elements.append(
            f"<text x='{x:.2f}' y='{SVG_HEIGHT - SVG_MARGIN_BOTTOM + 18:.2f}' text-anchor='middle' font-size='10' fill='{PALETTE['neutral']}'>{html.escape(_format_number(x_value))}</text>"
        )

    color = series.color or PALETTE['primary']
    points = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in zip(xs, ys))
    series_path = f"<polyline points='{points}' fill='none' stroke='{color}' stroke-width='2.4' />"

    marker_elements: List[str] = []
    marker_stacks: Dict[int, int] = {}
    for marker in markers:
        if marker.position < x_min or marker.position > x_max:
            continue
        x_pos = sx(marker.position)
        bucket = int(round(x_pos / 12))
        offset = marker_stacks.get(bucket, 0)
        marker_stacks[bucket] = offset + 1
        label_y = SVG_MARGIN_TOP + 14 + offset * 14
        marker_elements.append(
            f"<line x1='{x_pos:.2f}' y1='{SVG_MARGIN_TOP:.2f}' x2='{x_pos:.2f}' y2='{SVG_HEIGHT - SVG_MARGIN_BOTTOM:.2f}' stroke='{PALETTE['accent']}' stroke-width='1.2' stroke-dasharray='6 4' />"
        )
        label = html.escape(marker.label)
        marker_elements.append(
            f"<text x='{x_pos + 4:.2f}' y='{label_y:.2f}' font-size='10' fill='{PALETTE['accent']}'>{label}</text>"
        )

    x_axis_label = html.escape(f"{x_caption}{' [' + x_unit + ']' if x_unit else ''}")
    y_axis_label = html.escape(series.label + (f" [{series.unit}]" if series.unit else ""))

    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='{SVG_WIDTH}' height='{SVG_HEIGHT}' viewBox='0 0 {SVG_WIDTH} {SVG_HEIGHT}'>
      <rect x='0' y='0' width='{SVG_WIDTH}' height='{SVG_HEIGHT}' fill='white' />
      {''.join(grid_elements)}
      <line x1='{SVG_MARGIN_LEFT:.2f}' y1='{SVG_MARGIN_TOP:.2f}' x2='{SVG_MARGIN_LEFT:.2f}' y2='{SVG_HEIGHT - SVG_MARGIN_BOTTOM:.2f}' stroke='{PALETTE['primary']}' stroke-width='1.2' />
      <line x1='{SVG_MARGIN_LEFT:.2f}' y1='{SVG_HEIGHT - SVG_MARGIN_BOTTOM:.2f}' x2='{SVG_WIDTH - SVG_MARGIN_RIGHT:.2f}' y2='{SVG_HEIGHT - SVG_MARGIN_BOTTOM:.2f}' stroke='{PALETTE['primary']}' stroke-width='1.2' />
      {series_path}
      {''.join(marker_elements)}
      <text x='{SVG_MARGIN_LEFT - 46:.2f}' y='{SVG_MARGIN_TOP - 12:.2f}' font-size='11' fill='{PALETTE['primary']}'>{y_axis_label}</text>
      <text x='{(SVG_MARGIN_LEFT + width / 2):.2f}' y='{SVG_HEIGHT - 16:.2f}' text-anchor='middle' font-size='11' fill='{PALETTE['primary']}'>{x_axis_label}</text>
    </svg>
    """
    return svg.strip()



def _build_charts_section(
    series: Sequence[ParameterSeries],
    markers: Sequence[StatusMarker],
    x_caption: str,
    x_unit: str | None,
) -> str:
    blocks: List[str] = []
    for entry in series:
        svg = _render_chart_svg(entry, markers, x_caption, x_unit)
        if not svg:
            continue
        blocks.append(
            "<div class='chart'>"
            f"<div class='chart-title'>{html.escape(entry.label)}</div>"
            f"<p class='chart-note'>{html.escape(entry.explanation)}</p>"
            f"{svg}"
            "</div>"
        )
    if not blocks:
        return "<h2>Charts</h2><p>No chartable parameters found. Activate parameters with numeric data before exporting.</p>"
    return "<h2>Charts</h2><div class='charts'>" + "".join(blocks) + "</div>"


def _build_html(
    meta: Dict[str, str],
    status_value: Number | str | None,
    status_detail: StatusDetail | None,
    strategy_line: str,
    visible_table_rows: str,
    hidden_table_rows: str,
    series: Sequence[ParameterSeries],
    status_markers: Sequence[StatusMarker],
    sample_count: int,
    duration_text: str,
    x_axis_caption: str,
    x_axis_unit: str | None,
    start_text: str,
    end_text: str,
    generated_at: datetime,
) -> str:
    meta_blocks_html = _build_meta_blocks(meta, status_value)

    logo_uri = _load_logo_data()
    logo_html = (
        f"<img src='{logo_uri}' alt='WeTech logo' class='logo-image' />"
        if logo_uri
        else "<div class='logo-placeholder'>WeTech</div>"
    )

    header_html = (
        "<div class='page-header'>"
        f"<div class='header-logo'>{logo_html}</div>"
        "<div>"
        "<div class='report-title'>WeTech Measurement Report</div>"
        "<div class='report-subtitle'>Telemetry export overview</div>"
        "<div class='report-links'>www.wetech.de</div>"
        "</div>"
        "</div>"
    )

    summary_entries = [
        ("Samples", str(sample_count)),
        ("Duration", duration_text),
        ("X axis", x_axis_caption),
        ("Start", start_text),
        ("End", end_text),
        ("Status changes", str(len(status_markers))),
    ]
    if strategy_line and "Strategy:" in strategy_line:
        summary_entries.append(("Strategy", strategy_line.replace("<strong>Strategy:</strong> ", "")))

    overview_items = "".join(
        f"<div class='overview-item'><span class='overview-term'>{html.escape(label)}</span><span class='overview-detail'>{html.escape(value)}</span></div>"
        for label, value in summary_entries
    )
    overview_block = (
        "<div class='meta-block meta-block-overview'>"
        "<div class='meta-block-title'>Measurement Overview</div>"
        f"<div class='overview-grid'>{overview_items}</div>"
        "</div>"
    )

    footer_text = html.escape(
        f"WeTech · www.wetech.de · Generated {generated_at.strftime('%d.%m.%Y %H:%M:%S')}"
    )
    footer_html = f"<div class='page-footer'>{footer_text}</div>"

    first_page_sections: list[str] = []
    first_page_sections.append("<h2>Device Information</h2>")
    meta_section_html = "<div class='meta-section'>" + overview_block + meta_blocks_html + "</div>"
    first_page_sections.append(meta_section_html)

    first_page_sections.append("<h2>Active Parameters</h2>")
    first_page_sections.append(
        "<table class='stats-table'>"
        "<tr><th>Parameter</th><th>Description</th><th>Unit</th><th>Min</th><th>Max</th><th>Last</th></tr>"
        f"{visible_table_rows or '<tr><td colspan="6">No active parameters recorded.</td></tr>'}"
        "</table>"
    )

    first_page_sections.append("<h2>Additional Parameters</h2>")
    first_page_sections.append(
        "<table class='stats-table'>"
        "<tr><th>Parameter</th><th>Description</th><th>Unit</th><th>Min</th><th>Max</th><th>Last</th></tr>"
        f"{hidden_table_rows or '<tr><td colspan="6">No additional parameters recorded.</td></tr>'}"
        "</table>"
    )

    first_page = (
        "<div class='page first-page'>"
        f"{header_html}"
        f"<div class='page-body'>{''.join(first_page_sections)}</div>"
        f"{footer_html}"
        "</div>"
    )

    
    chart_pages: List[str] = []
    for entry in series:
        svg = _render_chart_svg(entry, status_markers, x_axis_caption, x_axis_unit)
        if not svg:
            continue
        chart_pages.append(
            "<div class='page chart-page'>"
            f"{header_html}"
            "<div class='page-body chart-body'>"
            "<div class='chart-full'>"
            f"<div class='chart-title'>{html.escape(entry.label)}</div>"
            f"<p class='chart-note'>{html.escape(entry.explanation)}</p>"
            f"{svg}"
            "</div>"
            "</div>"
            f"{footer_html}"
            "</div>"
        )


    pages_html = first_page + "".join(chart_pages)

    return f"""
    <html>
    <head>
    <meta charset='utf-8'>
    <style>
    @page {{ size: A4 landscape; margin: 12mm 16mm 14mm 16mm; }}
    body {{ font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; color: #1b1b1b; background: #ffffff; margin: 0; font-size: 11px; }}
    .page {{ display: grid; grid-template-rows: auto 1fr auto; min-height: 100vh; page-break-after: always; padding: 0 0 16px 0; box-sizing: border-box; }}
    .page:last-child {{ page-break-after: auto; }}
    .page-body {{ display: flex; flex-direction: column; gap: 24px; padding: 12px 0; }}
    .chart-body {{ justify-content: center; }}
    .page-header {{ display: flex; align-items: center; gap: 18px; border-bottom: 2px solid {PALETTE['primary']}; padding-bottom: 12px; }}
    .logo-image {{ height: 46px; }}
    .report-title {{ font-size: 22px; font-weight: 600; color: {PALETTE['primary']}; }}
    .report-subtitle {{ font-size: 12px; color: {PALETTE['neutral']}; margin-top: 4px; }}
    .report-links {{ font-size: 11px; color: {PALETTE['highlight']}; margin-top: 2px; }}
    h2 {{ color: {PALETTE['primary']}; font-size: 15px; margin: 12px 0 8px 0; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 6px; }}
    th, td {{ border: 1px solid {PALETTE['neutral']}; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: {PALETTE['primary']}15; font-weight: 600; }}
    .stats-table th {{ background: {PALETTE['accent_light']}40; color: {PALETTE['primary']}; }}
    .stats-table td:nth-child(n+3) {{ text-align: right; font-variant: tabular-nums; }}
    .meta-section {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; }}
    .meta-block {{ border: 1px solid {PALETTE['neutral']}66; border-radius: 12px; padding: 18px 20px; background: {PALETTE['primary']}0d; display: flex; flex-direction: column; gap: 12px; }}
    .meta-block-title {{ font-weight: 600; margin-bottom: 4px; color: {PALETTE['primary']}; letter-spacing: 0.3px; }}
    .meta-grid {{ display: grid; grid-template-columns: max-content 1fr; column-gap: 16px; row-gap: 8px; align-items: baseline; }}
    .meta-term {{ margin: 0; font-weight: 600; color: {PALETTE['neutral']}; text-transform: none; }}
    .meta-term::after {{ content: ':'; margin-left: 4px; color: {PALETTE['neutral']}; }}
    .meta-detail {{ margin: 0; color: #1b1b1b; font-variant: tabular-nums; text-align: left; word-break: break-word; line-height: 1.35; }}
    .overview-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px 20px; }}
    .overview-item {{ display: flex; justify-content: space-between; gap: 8px; align-items: baseline; padding: 4px 0; border-bottom: 1px dashed {PALETTE['neutral']}33; }}
    .overview-item:last-child {{ border-bottom: none; }}
    .overview-term {{ font-weight: 600; color: {PALETTE['neutral']}; }}
    .overview-term::after {{ content: ':'; margin-left: 4px; color: {PALETTE['neutral']}; }}
    .overview-detail {{ flex: 1; text-align: right; color: #1b1b1b; font-variant: tabular-nums; }}
    .chart-page .chart-full {{ border: 1px solid {PALETTE['neutral']}66; border-radius: 16px; padding: 20px 24px; background: white; box-shadow: 0 6px 18px rgba(0,0,0,0.06); display: flex; flex-direction: column; gap: 16px; min-height: 0; }}
    .chart-page .chart-title {{ font-weight: 600; color: {PALETTE['primary']}; font-size: 16px; }}
    .chart-page .chart-note {{ font-size: 11px; color: {PALETTE['neutral']}; line-height: 1.5; }}
    .chart-page .chart-full svg {{ flex: 1; width: 100%; height: auto; max-height: calc(100vh - 220px); display: block; border-radius: 10px; border: 1px solid {PALETTE['neutral']}40; background: white; }}
    .page-footer {{ border-top: 1px solid {PALETTE['primary']}55; padding-top: 8px; font-size: 10px; color: {PALETTE['neutral']}; text-align: right; align-self: stretch; break-inside: avoid; }}
    </style>
    </head>
    <body>
    {pages_html}
    </body>
    </html>
    """

def render_measurement_report(
    path: Path | str,
    meta: Dict[str, str],
    status_value: Number | str | None,
    status_detail: StatusDetail | None,
    strategy_code: str | None,
    strategy_label: str | None,
    visible_stats: Sequence[ParameterStatistic],
    hidden_stats: Sequence[ParameterStatistic],
    series: Sequence[ParameterSeries],
    status_markers: Sequence[StatusMarker],
    sample_count: int,
    duration_seconds: float,
    x_axis_caption: str,
    x_axis_unit: str | None,
    start_x: float | None,
    end_x: float | None,
    generated_at: datetime,
) -> None:
    """Render a measurement report PDF."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    visible_table_rows = _build_parameter_table_rows(visible_stats)
    hidden_table_rows = _build_parameter_table_rows(hidden_stats)

    start_text = _format_value(start_x, x_axis_unit)
    end_text = _format_value(end_x, x_axis_unit)
    duration_text = _format_duration(duration_seconds)

    strategy_parts: List[str] = []
    if strategy_label:
        strategy_parts.append(f"<strong>Strategy:</strong> {html.escape(strategy_label)}")
    strategy_line = " &nbsp;&nbsp; ".join(strategy_parts) if strategy_parts else "<strong>Strategy:</strong> -"

    html_content = _build_html(
        meta,
        status_value,
        status_detail,
        strategy_line,
        visible_table_rows,
        hidden_table_rows,
        series,
        status_markers,
        sample_count,
        duration_text,
        x_axis_caption,
        x_axis_unit,
        start_text,
        end_text,
        generated_at,
    )

    debug_dir = Path.cwd() / "logs"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_file = debug_dir / f"{target.stem}_preview.html"
    try:
        debug_file.write_text(html_content, encoding="utf-8")
    except Exception:
        pass

    _ensure_playwright_browsers_path()
    try:
        from playwright.sync_api import sync_playwright  # type: ignore import
    except ImportError as exc:
        raise RuntimeError("Playwright is required for PDF export. Install it via 'pip install playwright' and run 'playwright install chromium'.") from exc

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            raise RuntimeError("Playwright Chromium could not start. Run 'playwright install chromium'.") from exc
        page = browser.new_page()
        page.set_content(html_content, wait_until="networkidle")
        pdf_bytes = page.pdf(
            format="A4",
            landscape=True,
            margin={"top": "12mm", "bottom": "14mm", "left": "16mm", "right": "16mm"},
            display_header_footer=False,
        )
        page.close()
        browser.close()
    target.write_bytes(pdf_bytes)


__all__ = [
    "ParameterStatistic",
    "ParameterSeries",
    "StatusMarker",
    "render_measurement_report",
]
