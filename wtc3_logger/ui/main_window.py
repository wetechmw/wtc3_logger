"""Qt UI für den Telemetrie-Viewer im Wetech-Stil."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..config import AppConfig
from ..databus import DataBus
from ..parser import PARAMETERS, Number
from ..status import StatusDetail, decode_status, label_strategy
from . import colors
from .pdf_report import ParameterStatistic, render_measurement_report


SERIES_DEFAULT: List[str] = []
META_PARAMETER_KEYS = {
    "P04",
    "P05",
    "P07",
    "P08",
    "P70",
    "P71",
    "P72",
    "P73",
    "P74",
    "P75",
    "P76",
    "P77",
    "P78",
    "P79",
    "P80",
    "P81",
    "P90",
    "P91",
    "P92",
}


@dataclass(slots=True)
class ParameterSetting:
    """Konfiguration für einen Telemetrie-Parameter."""

    key: str
    label: str
    unit: str | None
    color: str
    visible: bool
    allow_graph: bool = True


class ColorIndicator(QtWidgets.QFrame):
    """Passives Farbfeld, das die Linienfarbe zeigt."""

    def __init__(self, color: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QtGui.QColor(color)
        self.setFixedSize(18, 18)
        self.setStyleSheet(
            "QFrame {border-radius: 9px; border: 2px solid %s; background-color: %s;}"
            % (colors.PRIMARY_LIGHT, self._color.name())
        )


class ParameterRow(QtWidgets.QWidget):
    """Eine Zeile in der Sidebar zur Steuerung eines Parameters."""

    changed = QtCore.Signal(ParameterSetting)

    def __init__(self, setting: ParameterSetting, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._setting = setting

        container = QtWidgets.QFrame()
        container.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        container.setStyleSheet(
            "QFrame {background: %s; border: 1px solid %s; border-radius: 8px;}"
            % ("white", colors.PRIMARY_LIGHT)
        )
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        self._visible_box = QtWidgets.QCheckBox()
        self._visible_box.setChecked(setting.visible)
        self._visible_box.setToolTip("Sichtbarkeit umschalten")
        self._visible_box.toggled.connect(self._emit_change)
        layout.addWidget(self._visible_box)

        unit = f" [{setting.unit}]" if setting.unit else ""
        self._info_label = QtWidgets.QLabel(f"{setting.key} – {setting.label}{unit}")
        self._info_label.setStyleSheet(
            "QLabel {color: %s; font-weight: 500;}" % colors.TEXT
        )
        layout.addWidget(self._info_label, 1)

        self._value_label = QtWidgets.QLabel("–")
        self._value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self._value_label.setStyleSheet(
            "QLabel {color: %s; font-weight: 600; background: %s; border-radius: 8px; padding: 4px 10px;}"
            % (colors.PRIMARY_DARK, colors.BACKGROUND)
        )
        layout.addWidget(self._value_label)

        indicator = ColorIndicator(setting.color)
        indicator.setToolTip("Linienfarbe im Diagramm")
        layout.addWidget(indicator)

        wrapper = QtWidgets.QHBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(container)

        self._update_enabled_state()

    def setting(self) -> ParameterSetting:
        return self._setting

    def _emit_change(self) -> None:
        visible = self._visible_box.isChecked()
        self._setting = replace(
            self._setting,
            visible=visible,
        )
        self._update_enabled_state()
        self.changed.emit(self._setting)

    def _update_enabled_state(self) -> None:
        if self._visible_box.isChecked():
            self._info_label.setStyleSheet(
                "QLabel {color: %s; font-weight: 500;}" % colors.TEXT
            )
        else:
            self._info_label.setStyleSheet(
                "QLabel {color: %s; font-weight: 500;}" % colors.MUTED_TEXT
            )

    def update_value(self, display_value: str) -> None:
        self._value_label.setText(display_value)


class ParameterSidebar(QtWidgets.QWidget):
    """Zusammenklappbare Sidebar zur Parameterauswahl."""

    changed = QtCore.Signal(str, ParameterSetting)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: Dict[str, ParameterRow] = {}
        self._values: Dict[str, str] = {}

        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(colors.BACKGROUND))
        self.setPalette(palette)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._toggle = QtWidgets.QToolButton()
        self._toggle.setText("Parameter")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        self._toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setStyleSheet(
            "QToolButton {color: %s; font-weight: 600; border: none;}" % colors.PRIMARY
        )
        self._toggle.toggled.connect(self._toggle_sidebar)
        layout.addWidget(self._toggle)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        layout.addWidget(self._scroll, 1)

        self._scroll_content = QtWidgets.QWidget()
        self._scroll_layout = QtWidgets.QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(6)
        self._scroll_layout.addStretch(1)
        self._scroll.setWidget(self._scroll_content)

        self._update_dynamic_width(force=True)

    def populate(self, settings: Iterable[ParameterSetting]) -> None:
        # Entferne Platzhalter-Stretch, damit neue Elemente korrekt eingefügt werden.
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._rows.clear()

        settings_list = list(settings)
        active = [s for s in settings_list if s.visible]
        inactive = [s for s in settings_list if not s.visible]

        self._add_section("Aktive Parameter", active)
        self._add_section("Weitere Parameter", inactive)

        self._scroll_layout.addStretch(1)

        self._update_dynamic_width()

    def _add_section(self, title: str, entries: List[ParameterSetting]) -> None:
        if not entries:
            return
        header = QtWidgets.QLabel(title)
        header.setStyleSheet(
            "QLabel {color: %s; font-size: 15px; font-weight: 600;}" % colors.PRIMARY_DARK
        )
        self._scroll_layout.addWidget(header)

        grouped: Dict[str, list[ParameterSetting]] = {}
        for setting in entries:
            grouped.setdefault(setting.unit or "Allgemein", []).append(setting)

        for unit, unit_entries in sorted(grouped.items(), key=lambda kv: kv[0]):
            unit_label = QtWidgets.QLabel(unit)
            unit_label.setStyleSheet(
                "QLabel {color: %s; font-size: 13px; font-weight: 600;}" % colors.MUTED_TEXT
            )
            self._scroll_layout.addWidget(unit_label)
            for setting in sorted(unit_entries, key=lambda s: s.label):
                row = ParameterRow(setting)
                row.changed.connect(self._on_row_changed)
                self._scroll_layout.addWidget(row)
                self._rows[setting.key] = row
                self._apply_value_to_row(setting.key)

    def setting(self, key: str) -> ParameterSetting | None:
        row = self._rows.get(key)
        return row.setting() if row else None

    def _on_row_changed(self, setting: ParameterSetting) -> None:
        self.changed.emit(setting.key, setting)

    def _toggle_sidebar(self, expanded: bool) -> None:
        self._toggle.setArrowType(
            QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow
        )
        self._scroll.setVisible(expanded)
        if expanded:
            self._update_dynamic_width(force=True)
        else:
            collapsed = max(48, self._toggle.sizeHint().width() + 16)
            self.setMinimumWidth(collapsed)
            self.setMaximumWidth(collapsed)

    def _update_dynamic_width(self, force: bool = False) -> None:
        self._scroll_content.adjustSize()
        content_width = self._scroll_content.sizeHint().width()
        scrollbar_width = self._scroll.verticalScrollBar().sizeHint().width()
        width = content_width + scrollbar_width + 24
        width = max(260, min(520, width))
        if force or self._toggle.isChecked():
            self.setMinimumWidth(width)
            self.setMaximumWidth(width)

    def update_value(self, key: str, value: Number | str | None, unit: str | None) -> None:
        formatted = self._format_value(value, unit)
        self._values[key] = formatted
        row = self._rows.get(key)
        if row:
            row.update_value(formatted)

    def clear_values(self) -> None:
        self._values.clear()
        for row in self._rows.values():
            row.update_value("–")

    def forget_value(self, key: str) -> None:
        self._values.pop(key, None)

    def _apply_value_to_row(self, key: str) -> None:
        value = self._values.get(key, "–")
        row = self._rows.get(key)
        if row:
            row.update_value(value)

    def _format_value(self, value: Number | str | None, unit: str | None) -> str:
        if value is None:
            return "–"
        if isinstance(value, float):
            text = ("%.3f" % value).rstrip("0").rstrip(".")
        else:
            text = str(value)
        if unit:
            return f"{text} {unit}"
        return text


class UnitPlot(QtWidgets.QFrame):
    """Wrapper um einen Plot je SI-Einheit."""

    def __init__(self, unit: str | None = None, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame {background: white; border-radius: 12px; border: 1px solid %s;}" % colors.PRIMARY_LIGHT
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        self._title_label = QtWidgets.QLabel()
        self._title_label.setStyleSheet(
            "QLabel {color: %s; font-weight: 600; font-size: 16px;}" % colors.PRIMARY_DARK
        )
        layout.addWidget(self._title_label)

        self.plot = pg.PlotWidget(background=colors.BACKGROUND)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.getPlotItem().getAxis("left").setPen(pg.mkPen(colors.MUTED_TEXT))
        self.plot.getPlotItem().getAxis("bottom").setPen(pg.mkPen(colors.MUTED_TEXT))
        self.plot.getPlotItem().getAxis("left").setTextPen(pg.mkPen(colors.MUTED_TEXT))
        self.plot.getPlotItem().getAxis("bottom").setTextPen(pg.mkPen(colors.MUTED_TEXT))
        self.plot.setLabel("bottom", "Zeit", "s")
        self.plot.addLegend()
        layout.addWidget(self.plot, 1)

        self._unit: str | None = None
        if unit:
            self.configure(unit)
        else:
            self.clear_unit()

    def configure(self, unit: str) -> None:
        self._unit = unit
        self._title_label.setText(f"Messwerte in {unit}")
        self.plot.setLabel("left", f"Wert [{unit}]")
        self.enable_auto_y()
        self.show()

    def clear_unit(self) -> None:
        self._unit = None
        self._title_label.setText("Messwerte")
        self.plot.clear()
        self.enable_auto_y()
        self.hide()

    def set_y_bounds(self, lower: float, upper: float) -> None:
        item = self.plot.getPlotItem()
        item.enableAutoRange(axis="y", enable=False)
        item.setYRange(lower, upper, padding=0)

    def enable_auto_y(self) -> None:
        item = self.plot.getPlotItem()
        item.enableAutoRange(axis="y", enable=True)




META_GROUP_DEFINITIONS: Dict[str, set[str]] = {
    "Ladegerät": {"P04", "P05", "P07", "P08"},
    "Batterie": {"P70", "P71", "P77", "P78", "P79", "P80", "P81"},
    "Temperaturfenster": {"P73", "P74", "P75", "P76"},
    "Grenzwerte": {"P72", "P90", "P91", "P92"},
}
META_GROUP_ORDER = ["Ladegerät", "Batterie", "Temperaturfenster", "Grenzwerte", "Weitere Angaben"]


class MetaDetailPanel(QtWidgets.QFrame):
    """Zeigt die einmaligen Meta-Informationen als Textfelder an."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame {background: white; border-radius: 12px; border: 1px solid %s;}" % colors.PRIMARY_LIGHT
        )

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)

        title = QtWidgets.QLabel("Geräteinformationen")
        title.setStyleSheet(
            "QLabel {color: %s; font-size: 18px; font-weight: 600;}" % colors.PRIMARY_DARK
        )
        outer.addWidget(title)

        subtitle = QtWidgets.QLabel(
            "Stammdaten aus dem ersten Datenblock. Die Werte ändern sich nur bei einem neuen Stream."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            "QLabel {color: %s; font-size: 13px;}" % colors.MUTED_TEXT
        )
        outer.addWidget(subtitle)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)

        self._scroll_content = QtWidgets.QWidget()
        self._groups_layout = QtWidgets.QVBoxLayout(self._scroll_content)
        self._groups_layout.setContentsMargins(0, 0, 0, 0)
        self._groups_layout.setSpacing(12)
        self._scroll.setWidget(self._scroll_content)

        outer.addWidget(self._scroll, 1)

        self._placeholder = QtWidgets.QLabel("Noch keine Geräteinformationen empfangen.")
        self._placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            "QLabel {color: %s; font-style: italic;}" % colors.MUTED_TEXT
        )
        outer.addWidget(self._placeholder)

        self._placeholder.show()
        self._scroll.hide()

    def update_meta(
        self,
        meta: Dict[str, str],
        status_value: Number | str | None,
        status_detail: StatusDetail | None,
    ) -> None:
        has_content = bool(meta) or status_value is not None
        if not has_content:
            self._placeholder.show()
            self._scroll.hide()
            return

        self._placeholder.hide()
        self._scroll.show()

        while self._groups_layout.count():
            item = self._groups_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        combined = dict(meta)
        if status_value is not None:
            combined["P05"] = str(status_value)

        grouped: Dict[str, List[str]] = {}
        for key in sorted(combined.keys()):
            group = self._group_name_for_key(key)
            grouped.setdefault(group, []).append(key)

        for group in META_GROUP_ORDER:
            keys = grouped.get(group)
            if not keys:
                continue
            box = QtWidgets.QGroupBox(group)
            box.setStyleSheet(
                "QGroupBox {border: 1px solid %s; border-radius: 10px; margin-top: 12px; padding: 10px 12px;}"
                "QGroupBox::title {subcontrol-origin: margin; left: 12px; padding: 0 4px; color: %s; font-weight: 600;}"
                % (colors.PRIMARY_LIGHT, colors.PRIMARY_DARK)
            )
            form = QtWidgets.QFormLayout()
            form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(8)

            for key in keys:
                info = PARAMETERS.get(key)
                caption = self._build_caption(key, info)
                value = combined[key]
                field = self._create_value_field(value, info)
                form.addRow(caption, field)
                if key == "P05":
                    detail_widget = self._build_status_details(status_detail)
                    form.addRow(self._status_caption(), detail_widget)

            box.setLayout(form)
            self._groups_layout.addWidget(box)

        self._groups_layout.addStretch(1)

    def _group_name_for_key(self, key: str) -> str:
        for group, keys in META_GROUP_DEFINITIONS.items():
            if key in keys:
                return group
        return "Weitere Angaben"

    def _build_caption(self, key: str, info) -> QtWidgets.QLabel:
        description = getattr(info, "description", "") if info else ""
        text = f"{key} – {description}" if description else key
        label = QtWidgets.QLabel(text)
        label.setStyleSheet(
            "QLabel {color: %s; font-weight: 500;}" % colors.TEXT
        )
        return label

    def _create_value_field(self, value: str, info) -> QtWidgets.QLineEdit:
        display_value = self._format_value(value, info)
        field = QtWidgets.QLineEdit()
        field.setReadOnly(True)
        field.setText(display_value)
        field.setStyleSheet(
            "QLineEdit {background: %s; border: 1px solid %s; border-radius: 6px; padding: 6px 8px;}"
            % (colors.BACKGROUND, colors.PRIMARY_LIGHT)
        )
        return field

    def _format_value(self, value: str, info) -> str:
        if not info:
            return str(value)
        casted = info.cast(str(value))
        if isinstance(casted, (int, float)):
            formatted = self._format_number(casted)
        else:
            formatted = str(casted)
        if info.unit:
            return f"{formatted} {info.unit}"
        return formatted

    def _format_number(self, number: Number) -> str:
        if isinstance(number, int):
            return str(number)
        return ("%.3f" % number).rstrip("0").rstrip(".")

    def _status_caption(self) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel("Statusdetails")
        label.setStyleSheet(
            "QLabel {color: %s; font-weight: 500;}" % colors.TEXT
        )
        return label

    def _build_status_details(self, status_detail: StatusDetail | None) -> QtWidgets.QWidget:
        text = "Keine Statusinformationen verfügbar."
        if status_detail and status_detail.details:
            text = "\n".join(status_detail.details)
        widget = QtWidgets.QLabel(text)
        widget.setWordWrap(True)
        widget.setStyleSheet(
            "QLabel {background: %s; border: 1px solid %s; border-radius: 6px; padding: 6px 8px; color: %s;}"
            % ("white", colors.PRIMARY_LIGHT, colors.TEXT)
        )
        widget.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        return widget


class StatusBadgeBar(QtWidgets.QWidget):
    """Zeigt Status-Badges im Wetech-Stil."""

    def __init__(self, config: AppConfig, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._strategy_label = QtWidgets.QLabel()
        self._strategy_label.setStyleSheet(
            "QLabel {background: %s; color: white; border-radius: 14px; padding: 6px 12px; font-weight: 600;}"
            % colors.PRIMARY
        )
        layout.addWidget(self._strategy_label)
        self._status_layout = QtWidgets.QHBoxLayout()
        self._status_layout.setContentsMargins(0, 0, 0, 0)
        self._status_layout.setSpacing(8)
        layout.addLayout(self._status_layout)
        layout.addStretch(1)
        self._badges: list[QtWidgets.QLabel] = []
        self.setLayout(layout)
        self.hide()

    def update_state(self, meta: Dict[str, str], status_detail: StatusDetail | None) -> None:
        strategy_code = meta.get("P04")
        friendly = label_strategy(strategy_code, self._config.strategy_labels)
        if friendly:
            self._strategy_label.setText(friendly)
            self._strategy_label.show()
        elif strategy_code:
            self._strategy_label.setText(str(strategy_code))
            self._strategy_label.show()
        else:
            self._strategy_label.hide()

        for badge in self._badges:
            self._status_layout.removeWidget(badge)
            badge.deleteLater()
        self._badges.clear()

        statuses: list[str] = []
        if status_detail:
            statuses = status_detail.badges

        for text in statuses:
            badge = QtWidgets.QLabel(text)
            badge.setStyleSheet(
                "QLabel {background: %s; color: white; border-radius: 12px; padding: 4px 10px; font-weight: 500;}"
                % colors.PRIMARY_DARK
            )
            self._status_layout.addWidget(badge)
            self._badges.append(badge)

        if friendly or strategy_code or statuses:
            self.show()
        else:
            self.hide()


class MainWindow(QtWidgets.QMainWindow):
    """Zentrales Fenster mit Plot, Tabelle und Metadaten."""

    def __init__(self, databus: DataBus, config: AppConfig, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.databus = databus
        self.config = config
        self.setWindowTitle("WeTech Telemetrie Monitor")
        self.resize(1360, 780)
        self._x_key = "P06"
        self._parameter_order: List[str] = list(PARAMETERS.keys())
        self._parameter_settings: Dict[str, ParameterSetting] = self._default_parameter_settings()
        self._curves: Dict[str, pg.PlotDataItem] = {}
        self._curve_units: Dict[str, str] = {}
        self._unit_plots: Dict[str, UnitPlot] = {}
        self._last_records: List[Dict[str, Number | str]] = []
        self._auto_initialized: set[str] = set()
        self._meta_keys: set[str] = set(META_PARAMETER_KEYS)
        self._seen_generation = self.databus.generation()
        self._temperature_limits: Tuple[float, float] | None = None

        self._init_palette()
        self._init_ui()

        self._timer = QtCore.QTimer(self)
        interval = max(15, int(1000 / max(1.0, config.ui_refresh_hz)))
        self._timer.timeout.connect(self.refresh)
        self._timer.start(interval)

    def _default_parameter_settings(self) -> Dict[str, ParameterSetting]:
        settings: Dict[str, ParameterSetting] = {}
        for key in self._parameter_order:
            if key in META_PARAMETER_KEYS:
                continue
            info = PARAMETERS[key]
            allow_graph = bool(info.unit) and key != self._x_key
            if not allow_graph:
                continue
            visible = key in SERIES_DEFAULT
            settings[key] = ParameterSetting(
                key=key,
                label=info.description,
                unit=info.unit,
                color=self._color_for_key(key),
                visible=visible,
                allow_graph=allow_graph,
            )
        return settings

    def _ordered_settings(self) -> List[ParameterSetting]:
        return sorted(
            self._parameter_settings.values(),
            key=lambda setting: (
                0 if setting.visible else 1,
                setting.unit or "",
                setting.label,
            ),
        )

    def _init_palette(self) -> None:
        palette = self.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("white"))
        palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(colors.TEXT))
        palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(colors.BACKGROUND))
        palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("white"))
        palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(colors.PRIMARY_LIGHT))
        palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("white"))
        self.setPalette(palette)

    def _init_ui(self) -> None:
        pg.setConfigOptions(antialias=True)

        central = QtWidgets.QWidget(self)
        central_layout = QtWidgets.QHBoxLayout(central)
        central_layout.setContentsMargins(16, 16, 16, 16)
        central_layout.setSpacing(16)

        self.sidebar = ParameterSidebar()
        self.sidebar.populate(self._ordered_settings())
        self.sidebar.changed.connect(self._on_parameter_setting_changed)
        central_layout.addWidget(self.sidebar)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        header = QtWidgets.QLabel("WTC3 Telemetrie")
        header.setStyleSheet(
            "font-size: 28px; font-weight: 600; color: %s; letter-spacing: 0.5px;" % colors.PRIMARY
        )
        content_layout.addWidget(header)

        self.status_badges = StatusBadgeBar(self.config)
        content_layout.addWidget(self.status_badges)

        self._plots_scroll = QtWidgets.QScrollArea()
        self._plots_scroll.setWidgetResizable(True)
        self._plots_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._plots_scroll.setStyleSheet("QScrollArea {border: none;}")

        self._plots_container = QtWidgets.QWidget()
        self._plots_layout = QtWidgets.QVBoxLayout(self._plots_container)
        self._plots_layout.setContentsMargins(0, 0, 0, 0)
        self._plots_layout.setSpacing(16)
        self._plots_layout.addStretch(1)

        self._plots_scroll.setWidget(self._plots_container)
        content_layout.addWidget(self._plots_scroll, 1)

        central_layout.addWidget(content, 2)

        self.meta_panel = MetaDetailPanel()
        self.meta_panel.setMinimumWidth(360)
        central_layout.addWidget(self.meta_panel, 1)

        central.setLayout(central_layout)
        self.setCentralWidget(central)

        toolbar = self.addToolBar("Aktionen")
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            "QToolBar {background: %s; spacing: 12px;} QToolButton {color: white; background: %s; border-radius: 6px; padding: 6px 12px;}"
            % (colors.PRIMARY_DARK, colors.PRIMARY)
        )
        export_action = QtGui.QAction("CSV öffnen", self)
        export_action.triggered.connect(self._open_csv)
        toolbar.addAction(export_action)

        pdf_action = QtGui.QAction("Messprotokoll PDF", self)
        pdf_action.triggered.connect(self._export_pdf)
        toolbar.addAction(pdf_action)

        self.status = self.statusBar()
        self.status.setStyleSheet("color: %s" % colors.MUTED_TEXT)
        self.status.showMessage("Bereit")

        self._update_plot_visibility()

    def _active_graph_keys(self) -> List[str]:
        return [
            key
            for key in self._parameter_order
            if (setting := self._parameter_settings.get(key))
            and setting.visible
            and setting.allow_graph
            and setting.unit
        ]

    def _collect_active_units(self) -> Dict[str, List[str]]:
        units: Dict[str, List[str]] = {}
        for key in self._active_graph_keys():
            unit = self._parameter_settings[key].unit
            assert unit is not None
            units.setdefault(unit, []).append(key)
        return units

    def _ensure_visible_units(self) -> Dict[str, List[str]]:
        units = self._collect_active_units()
        ordered_units = sorted(units.keys())

        for unit in ordered_units:
            if unit not in self._unit_plots:
                self._unit_plots[unit] = UnitPlot(parent=self._plots_container)

        self._rebuild_plot_layout(ordered_units)
        return {unit: units[unit] for unit in ordered_units}

    def _rebuild_plot_layout(self, ordered_units: List[str]) -> None:
        while self._plots_layout.count():
            item = self._plots_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(self._plots_container)

        if not ordered_units:
            self._plots_layout.addStretch(1)
            return

        for unit in ordered_units:
            plot = self._unit_plots[unit]
            plot.configure(unit)
            plot.show()
            self._plots_layout.addWidget(plot)

        self._plots_layout.addStretch(1)

        for unit, plot in self._unit_plots.items():
            if unit not in ordered_units:
                plot.clear_unit()
                plot.hide()

    def _update_plot_visibility(self) -> None:
        self._ensure_visible_units()

    def _on_parameter_setting_changed(self, key: str, setting: ParameterSetting) -> None:
        self._parameter_settings[key] = setting
        if not setting.visible or not setting.allow_graph:
            self._remove_curve(key)
        else:
            self._apply_curve_color(key)
        self._update_plot_visibility()
        state = "aktiv" if setting.visible else "inaktiv"
        self.status.showMessage(
            f"{setting.key} {state}",
            2500,
        )
        self.sidebar.populate(self._ordered_settings())

    def _handle_meta_parameters(self, meta: Dict[str, str]) -> None:
        self._update_temperature_limits(meta)

        new_meta = set(meta.keys()) - self._meta_keys
        if not new_meta:
            return

        self._meta_keys.update(new_meta)
        changed = False
        for key in new_meta:
            if key in self._parameter_settings:
                self._parameter_settings.pop(key)
                self._curves.pop(key, None)
                self._curve_units.pop(key, None)
                self._auto_initialized.discard(key)
                self.sidebar.forget_value(key)
                changed = True
        if changed:
            self.sidebar.populate(self._ordered_settings())
            self._update_plot_visibility()

    def _update_temperature_limits(self, meta: Dict[str, str]) -> None:
        values: List[float] = []
        for key in ("P73", "P74", "P75", "P76"):
            raw = meta.get(key)
            if raw is None:
                continue
            info = PARAMETERS.get(key)
            if not info:
                continue
            if isinstance(raw, str):
                casted = info.cast(raw)
            else:
                casted = info.cast(str(raw))
            if isinstance(casted, (int, float)):
                values.append(float(casted))
        if not values:
            return
        lower = min(values)
        upper = max(values)
        if lower == upper:
            upper = lower + 1.0
        self._temperature_limits = (lower, upper)

    def _auto_initialize_from_record(self, record: Dict[str, Number | str]) -> None:
        changed = False
        for key in record.keys():
            if key not in self._parameter_settings or key in self._auto_initialized:
                continue
            setting = self._parameter_settings[key]
            if not setting.allow_graph:
                self._auto_initialized.add(key)
                continue
            updated = replace(
                setting,
                visible=True,
            )
            if updated != setting:
                self._parameter_settings[key] = updated
                changed = True
            self._auto_initialized.add(key)
        if changed:
            self.sidebar.populate(self._ordered_settings())
            self._update_plot_visibility()

    def refresh(self) -> None:
        generation = self.databus.generation()
        if generation != self._seen_generation:
            self._seen_generation = generation
            self._on_data_reset()

        records = self.databus.snapshot()
        if not records:
            self._last_records = []
            return
        self._last_records = records
        meta = self.databus.meta()
        self._handle_meta_parameters(meta)
        last_record = records[-1]
        status_detail = decode_status(last_record.get("P05"))
        self.status_badges.update_state(meta, status_detail)
        self.meta_panel.update_meta(meta, last_record.get("P05"), status_detail)

        self._auto_initialize_from_record(last_record)
        self._update_active_parameter_values(last_record)

        x_data = self._extract_x(records)
        self._update_curves(x_data, records)

    def _on_data_reset(self) -> None:
        self._last_records = []
        self._auto_initialized.clear()
        for plot in self._unit_plots.values():
            plot.plot.clear()
        self._curves.clear()
        self._curve_units.clear()
        self.sidebar.clear_values()
        self._temperature_limits = None
        self._update_plot_visibility()

    def _update_active_parameter_values(self, record: Dict[str, Number | str]) -> None:
        for key, setting in self._parameter_settings.items():
            if not setting.allow_graph:
                continue
            value = record.get(key) if setting.visible else None
            self.sidebar.update_value(key, value, setting.unit)

    def _extract_x(self, records: List[Dict[str, Number | str]]) -> List[float]:
        x_vals: List[float] = []
        for record in records:
            value = record.get(self._x_key)
            if isinstance(value, (int, float)):
                x_vals.append(float(value))
            else:
                x_vals.append(float(len(x_vals)))
        return x_vals

    def _update_curves(self, x_data: List[float], records: List[Dict[str, Number | str]]) -> None:
        visible_units = self._ensure_visible_units()
        active_keys = {key for keys in visible_units.values() for key in keys}

        for key in list(self._curves.keys()):
            if key not in active_keys:
                self._remove_curve(key)

        unit_ranges: Dict[str, Tuple[float, float]] = {}
        for unit, keys in visible_units.items():
            plot_widget = self._unit_plots[unit]
            plot = plot_widget.plot
            unit_min: float | None = None
            unit_max: float | None = None
            for key in keys:
                xs: List[float] = []
                ys: List[float] = []
                for x_value, record in zip(x_data, records):
                    value = record.get(key)
                    if isinstance(value, (int, float)):
                        xs.append(x_value)
                        ys.append(float(value))
                color = QtGui.QColor(self._parameter_settings[key].color)
                pen = pg.mkPen(color=color, width=2)
                if key not in self._curves:
                    label = f"{key} – {self._parameter_settings[key].label}"
                    curve = plot.plot(name=label, pen=pen)
                    self._curves[key] = curve
                    self._curve_units[key] = unit
                else:
                    curve = self._curves[key]
                    curve.setPen(pen)
                self._curves[key].setData(xs, ys)
                if ys:
                    current_min = min(ys)
                    current_max = max(ys)
                    unit_min = current_min if unit_min is None else min(unit_min, current_min)
                    unit_max = current_max if unit_max is None else max(unit_max, current_max)
            if unit_min is not None and unit_max is not None:
                unit_ranges[unit] = (unit_min, unit_max)

        for unit, keys in visible_units.items():
            plot_widget = self._unit_plots[unit]
            bounds = unit_ranges.get(unit)
            if bounds is None:
                plot_widget.enable_auto_y()
                continue
            min_val, max_val = bounds
            if unit == "°C":
                if self._temperature_limits:
                    lower, upper = self._temperature_limits
                    lower = min(lower, min_val)
                    upper = max(upper, max_val)
                else:
                    lower, upper = min_val, max_val
            else:
                lower = 0.0
                upper = max(max_val * 1.05, 0.1)
            if upper <= lower:
                upper = lower + 1.0
            plot_widget.set_y_bounds(float(lower), float(upper))

        # Sichtbare Einheiten sind bereits in _ensure_visible_units gespeichert

    def _color_for_key(self, key: str) -> str:
        palette = [colors.PRIMARY, colors.PRIMARY_LIGHT, colors.ACCENT, "#3DC1D3", "#6A67CE", "#FFB347"]
        idx = hash(key) % len(palette)
        return palette[idx]

    def _remove_curve(self, key: str) -> None:
        item = self._curves.pop(key, None)
        unit = self._curve_units.pop(key, None)
        if item and unit and unit in self._unit_plots:
            self._unit_plots[unit].plot.removeItem(item)

    def _apply_curve_color(self, key: str) -> None:
        if key in self._curves:
            color = QtGui.QColor(self._parameter_settings[key].color)
            self._curves[key].setPen(pg.mkPen(color=color, width=2))

    def _open_csv(self) -> None:
        path = self.config.persist_path
        if not path.exists():
            self.status.showMessage("Keine CSV-Datei vorhanden", 3000)
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    def _export_pdf(self) -> None:
        if not self._last_records:
            QtWidgets.QMessageBox.information(
                self,
                "Kein Messprotokoll",
                "Es wurden noch keine Messdaten empfangen.",
            )
            return

        default_dir = self.config.persist_path.parent
        default_dir.mkdir(parents=True, exist_ok=True)
        suggested = default_dir / f"messprotokoll_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Messprotokoll speichern",
            str(suggested),
            "PDF-Dateien (*.pdf)",
        )
        if not selected:
            return

        target = Path(selected)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")

        last_record = self._last_records[-1]
        meta = self.databus.meta()
        status_value = last_record.get("P05")
        status_detail = decode_status(status_value)
        strategy_code = meta.get("P04")
        strategy_label = label_strategy(strategy_code, self.config.strategy_labels)

        x_data = self._extract_x(self._last_records)
        start_x = x_data[0] if x_data else None
        end_x = x_data[-1] if x_data else None
        duration = 0.0
        if start_x is not None and end_x is not None:
            duration = max(0.0, end_x - start_x)

        visible_stats: List[ParameterStatistic] = []
        hidden_stats: List[ParameterStatistic] = []
        for key in self._parameter_order:
            setting = self._parameter_settings.get(key)
            if not setting:
                continue
            values: List[float] = []
            for record in self._last_records:
                value = record.get(key)
                if isinstance(value, (int, float)):
                    values.append(float(value))
            if not values:
                continue
            stat = ParameterStatistic(
                key=key,
                label=setting.label,
                unit=setting.unit,
                min_value=min(values),
                max_value=max(values),
                last_value=values[-1],
                color=setting.color,
                visible=setting.visible,
            )
            if setting.visible:
                visible_stats.append(stat)
            else:
                hidden_stats.append(stat)

        x_info = PARAMETERS.get(self._x_key)
        x_caption = f"{self._x_key} – {x_info.description}" if x_info and x_info.description else self._x_key
        x_unit = x_info.unit if x_info else None

        try:
            render_measurement_report(
                target,
                meta,
                status_value,
                status_detail,
                strategy_code,
                strategy_label,
                visible_stats,
                hidden_stats,
                len(self._last_records),
                duration,
                x_caption,
                x_unit,
                start_x,
                end_x,
                datetime.now(),
            )
        except Exception as exc:  # pragma: no cover - Qt Fehler schwer reproduzierbar
            QtWidgets.QMessageBox.critical(
                self,
                "Export fehlgeschlagen",
                f"Das Messprotokoll konnte nicht erstellt werden:\n{exc}",
            )
            return

        self.status.showMessage(f"Messprotokoll gespeichert: {target}", 4000)


__all__ = ["MainWindow"]