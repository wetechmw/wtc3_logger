"""Qt UI für den Telemetrie-Viewer im Wetech-Stil."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import unicodedata
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence, Tuple

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..acquisition import AcquisitionController
from ..config import AppConfig
from ..preferences import load_preferences, save_preferences
from ..databus import DataBus
from ..parser import PARAMETERS, Number
from ..status import StatusDetail, decode_status, label_strategy
from . import colors
from .config_dialog import ConfigDialog
from .pdf_report import ParameterSeries, ParameterStatistic, StatusMarker, render_measurement_report


SERIES_DEFAULT: List[str] = ["P44", "P45", "P54", "P55", "P61"]
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

STATUS_FIELD_TRANSLATIONS = {
    "batteriespannung": "Battery Voltage",
    "batterietemperatur": "Battery Temperature",
    "innenwiderstand": "Internal Resistance",
    "versorgung": "Supply",
    "ladestrom": "Charge Current",
    "fehler": "Fault",
    "peripherie": "Peripheral",
    "nicd eoc": "NiCd End of Charge",
}

def _normalize_status_label(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("\u0394", "Delta ")
    cleaned = cleaned.replace("ΔV", "Delta V").replace("ΔT", "Delta T")
    cleaned = cleaned.replace("Δ", "Delta ")
    normalized = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
    normalized = " ".join(normalized.split()).lower()
    return normalized

STATUS_VALUE_TRANSLATIONS = {
    "tiefentladen": "Deep Discharged",
    "niedrig": "Low",
    "normal": "Normal",
    "voll": "Full",
    "uberspannung": "Over Voltage",
    "ladeende": "Charge Complete",
    "kalt": "Cold",
    "kuhl": "Cool",
    "warm": "Warm",
    "heiss": "Hot",
    "hoch": "High",
    "aus": "Off",
    "10%": "10%",
    "20%": "20%",
    "50%": "50%",
    "100%": "100%",
    "nicht verwendet": "Not Used",
    "keine fehler": "No Faults",
    "geringe kapazitat": "Low Capacity",
    "hohe kapazitat": "High Capacity",
    "temperaturdurchgang": "Temperature Fault",
    "hoher widerstand": "High Resistance",
    "eingang aktiviert": "Input Enabled",
    "ausgang aktiviert": "Output Enabled",
    "regler aktiv": "Regulator Active",
    "referenz aktiv": "Reference Active",
    "sleep aktiv": "Sleep Active",
    "delta v drop erreicht": "Delta V reached",
    "delta t anstieg": "Delta T rise",
    "max. spannungsabfall": "Max voltage drop",
    "hohe temperatur": "High temperature",
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
    """Editable color swatch that emits a signal when clicked."""

    clicked = QtCore.Signal()

    def __init__(self, color: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QtGui.QColor(color)
        self.setFixedSize(18, 18)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            "QFrame {border-radius: 9px; border: 2px solid %s; background-color: %s;}"
            % (colors.PRIMARY_LIGHT, self._color.name())
        )

    def set_color(self, color: QtGui.QColor) -> None:
        if not color.isValid():
            return
        self._color = color
        self._apply_style()

    def color(self) -> QtGui.QColor:
        return QtGui.QColor(self._color)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ParameterRow(QtWidgets.QWidget):
    """Eine Zeile in der Sidebar zur Steuerung eines Parameters."""

    changed = QtCore.Signal(ParameterSetting)

    def __init__(
        self,
        setting: ParameterSetting,
        on_color_change: Callable[[str, str], None] | None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._setting = setting
        if on_color_change is None:
            self._on_color_change: Callable[[str, str], None] = lambda _k, _c: None
        else:
            self._on_color_change = on_color_change

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

        self._value_label = QtWidgets.QLabel('---.---   ')
        self._value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        fixed_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self._value_label.setFont(fixed_font)
        metrics = QtGui.QFontMetrics(fixed_font)
        sample_width = metrics.horizontalAdvance('9999.999 XXX')
        self._value_label.setMinimumWidth(sample_width + 12)
        self._value_label.setStyleSheet(
            "QLabel {color: %s; font-weight: 600; background: %s; border-radius: 8px; padding: 4px 10px;}"
            % (colors.PRIMARY_DARK, colors.BACKGROUND)
        )
        self._value_label.setText(self._value_label.text().replace(' ', '\u00A0'))
        layout.addWidget(self._value_label)

        indicator = ColorIndicator(setting.color)
        indicator.setToolTip("Linienfarbe im Diagramm")
        indicator.clicked.connect(self._open_color_dialog)
        self._color_indicator = indicator
        layout.addWidget(indicator)

        wrapper = QtWidgets.QHBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(container)

        self._update_enabled_state()

    def set_color(self, color_hex: str) -> None:
        self._color_indicator.set_color(QtGui.QColor(color_hex))
        self._setting = replace(self._setting, color=color_hex)

    def _open_color_dialog(self) -> None:
        current = self._color_indicator.color()
        chosen = QtWidgets.QColorDialog.getColor(current, self, "Select color")
        if not chosen.isValid():
            return
        color_hex = chosen.name()
        self.set_color(color_hex)
        self._on_color_change(self._setting.key, color_hex)


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
        self._value_label.setText(display_value.replace(' ', '\u00A0'))




class ConfigurationWarningOverlay(QtWidgets.QFrame):
    """Centered warning shown when acquisition config is incomplete."""

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("configurationWarningOverlay")
        self.setStyleSheet(
            "QFrame#configurationWarningOverlay {background: rgba(255, 255, 255, 210);}"  # translucent backdrop
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        panel = QtWidgets.QFrame()
        panel.setStyleSheet(
            "QFrame {background: %s; border: 2px solid %s; border-radius: 14px; padding: 26px 36px;}"
            % (colors.BACKGROUND, colors.ACCENT)
        )
        inner = QtWidgets.QVBoxLayout(panel)
        inner.setSpacing(12)
        inner.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        title = QtWidgets.QLabel("Configuration incomplete")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "QLabel {color: %s; font-size: 20px; font-weight: 600;}" % colors.ACCENT
        )
        inner.addWidget(title)

        self._message = QtWidgets.QLabel()
        self._message.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet(
            "QLabel {color: %s; font-size: 13px;}" % colors.TEXT
        )
        inner.addWidget(self._message)

        hint = QtWidgets.QLabel("Open the data source settings to select a COM port or sample file.")
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("QLabel {color: %s;}" % colors.MUTED_TEXT)
        inner.addWidget(hint)

        layout.addWidget(panel)
        self.hide()

    def set_message(self, message: str) -> None:
        self._message.setText(message)

    def update_geometry(self) -> None:
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())

class ParameterSidebar(QtWidgets.QWidget):
    """Zusammenklappbare Sidebar zur Parameterauswahl."""

    changed = QtCore.Signal(str, ParameterSetting)
    preferred_width_changed = QtCore.Signal(int)

    def __init__(
        self,
        on_color_change: Callable[[str, str], None] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if on_color_change is None:
            self._on_color_change: Callable[[str, str], None] = lambda _k, _c: None
        else:
            self._on_color_change = on_color_change
        self._rows: Dict[str, ParameterRow] = {}
        self._values: Dict[str, str] = {}
        self._preferred_width: int = 360

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
                row = ParameterRow(setting, self._on_color_change)
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
            self.setMinimumWidth(220)
            self.setMaximumWidth(900)
            self._update_dynamic_width(force=True)
        else:
            collapsed = max(48, self._toggle.sizeHint().width() + 16)
            self.setMinimumWidth(collapsed)
            self.setMaximumWidth(collapsed)
            self.preferred_width_changed.emit(collapsed)

    def _update_dynamic_width(self, force: bool = False) -> None:
        self._scroll_content.adjustSize()
        content_width = self._scroll_content.sizeHint().width()
        scrollbar_width = self._scroll.verticalScrollBar().sizeHint().width()
        preferred = content_width + scrollbar_width + 24
        preferred = max(260, min(560, preferred))
        previous = self._preferred_width
        self._preferred_width = preferred
        if self._toggle.isChecked():
            self.setMinimumWidth(220)
            self.setMaximumWidth(900)
            if force or previous != preferred:
                self.preferred_width_changed.emit(preferred)
        elif force:
            collapsed = max(48, self._toggle.sizeHint().width() + 16)
            self.preferred_width_changed.emit(collapsed)

    def preferred_width(self) -> int:
        if self._toggle.isChecked():
            return self._preferred_width
        return max(48, self._toggle.sizeHint().width() + 16)

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    def update_value(self, key: str, value: Number | str | None, unit: str | None) -> None:
        formatted = self._format_value(value, unit)
        self._values[key] = formatted
        row = self._rows.get(key)
        if row:
            row.update_value(formatted)

    def clear_values(self) -> None:
        self._values.clear()
        for row in self._rows.values():
            placeholder = self._format_value(None, row.setting().unit)
            row.update_value(placeholder)


    def apply_color(self, key: str, color_hex: str) -> None:
        row = self._rows.get(key)
        if row:
            row.set_color(color_hex)

    def forget_value(self, key: str) -> None:
        self._values.pop(key, None)

    def _apply_value_to_row(self, key: str) -> None:
        row = self._rows.get(key)
        if not row:
            return
        value = self._values.get(key)
        if value is None:
            value = self._format_value(None, row.setting().unit)
        row.update_value(value)

    def _format_value(self, value: Number | str | None, unit: str | None) -> str:
        def _nb(text: str) -> str:
            return text.replace(' ', '\u00A0')

        if value is None:
            numeric = '---.---'
        elif isinstance(value, (int, float)):
            numeric = f"{float(value):7.3f}"
        else:
            text = str(value)
            numeric = text[:7].rjust(7)

        unit_text = (unit or '')[:3]
        unit_block = unit_text.rjust(3) if unit_text else '   '
        return _nb(f"{numeric} {unit_block}")



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
        legend = self.plot.addLegend()
        if legend is not None:
            legend.anchor((1, 1), (1, 1))
            legend.setOffset((-10, -10))
        layout.addWidget(self.plot, stretch=1)

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

    def set_config(self, config: AppConfig) -> None:
        self._config = config

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

    def __init__(self, databus: DataBus, config: AppConfig, controller: AcquisitionController | None = None, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.databus = databus
        self._controller = controller
        self.config = controller.config if controller else config
        self._open_raw_action: QtGui.QAction | None = None
        self._pdf_action: QtGui.QAction | None = None
        self._config_action: QtGui.QAction | None = None
        self._config_warning: ConfigurationWarningOverlay | None = None
        self._auto_stop_checkbox: QtWidgets.QCheckBox | None = None
        self.setWindowTitle("WeTech Telemetrie Monitor")
        self.resize(1360, 780)
        self._x_key = "P06"
        self._preferences = load_preferences()
        self._auto_stop_enabled = bool(self._preferences.get('auto_stop_full_battery', False))
        self._auto_stop_since: datetime | None = None
        self._auto_stop_triggered = False
        self._color_overrides: Dict[str, str] = self._preferences.get('parameter_colors', {})
        self._parameter_order: List[str] = list(PARAMETERS.keys())
        self._parameter_settings: Dict[str, ParameterSetting] = self._default_parameter_settings()
        self._curves: Dict[str, pg.PlotDataItem] = {}
        self._curve_units: Dict[str, str] = {}
        self._unit_plots: Dict[str, UnitPlot] = {}
        self._last_records: List[Dict[str, Number | str]] = []
        self._auto_initialized: set[str] = set()
        self._meta_keys: set[str] = set(META_PARAMETER_KEYS)
        self._main_splitter: QtWidgets.QSplitter | None = None
        self._seen_generation = self.databus.generation()
        self._temperature_limits: Tuple[float, float] | None = None

        self._init_palette()
        self._init_ui()

        if self._controller:
            self._controller.status_message.connect(self._handle_status_message)
            self._controller.error_occurred.connect(self._handle_acquisition_error)
            self._controller.config_changed.connect(self._on_config_changed)

        self._refresh_action_state()

        self._timer = QtCore.QTimer(self)
        interval = max(15, int(1000 / max(1.0, self.config.ui_refresh_hz)))
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

        self.sidebar = ParameterSidebar(self._on_row_color_change)
        self.sidebar.populate(self._ordered_settings())
        self.sidebar.changed.connect(self._on_parameter_setting_changed)

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

        self._main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.setHandleWidth(10)
        self._main_splitter.addWidget(self.sidebar)
        self._main_splitter.addWidget(content)
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)
        central_layout.addWidget(self._main_splitter, 3)

        self.sidebar.preferred_width_changed.connect(self._apply_sidebar_width)

        self.meta_panel = MetaDetailPanel()
        self.meta_panel.setMinimumWidth(360)
        central_layout.addWidget(self.meta_panel, 1)

        central.setLayout(central_layout)
        self.setCentralWidget(central)
        central.installEventFilter(self)
        self._config_warning = ConfigurationWarningOverlay(central)
        self._config_warning.update_geometry()

        toolbar = self.addToolBar("Actions")
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            "QToolBar {background: %s; spacing: 12px;} QToolButton {color: white; background: %s; border-radius: 6px; padding: 6px 12px;}"
            % (colors.PRIMARY_DARK, colors.PRIMARY)
        )
        if self._controller:
            config_action = QtGui.QAction("Data Source...", self)
            config_action.triggered.connect(self._open_config_dialog)
            toolbar.addAction(config_action)
            self._config_action = config_action

        export_action = QtGui.QAction("Open Raw Data", self)
        export_action.triggered.connect(self._open_raw_data)
        toolbar.addAction(export_action)
        self._open_raw_action = export_action

        pdf_action = QtGui.QAction("Export Report PDF", self)
        pdf_action.triggered.connect(self._export_pdf)
        toolbar.addAction(pdf_action)
        self._pdf_action = pdf_action

        toolbar.addSeparator()
        auto_stop_box = QtWidgets.QCheckBox('Auto-stop (Full >=1 min)')
        auto_stop_box.setChecked(self._auto_stop_enabled)
        auto_stop_box.setToolTip('Stop acquisition when the battery reports a full state for 60 seconds.')
        auto_stop_box.setStyleSheet('QCheckBox { color: white; font-weight: 500; }')
        auto_stop_box.toggled.connect(self._toggle_auto_stop)
        toolbar.addWidget(auto_stop_box)
        self._auto_stop_checkbox = auto_stop_box

        self.status = self.statusBar()
        self.status.setStyleSheet("color: %s" % colors.MUTED_TEXT)
        self.status.showMessage("Ready")

        QtCore.QTimer.singleShot(0, self._init_splitter_sizes)
        self._update_plot_visibility()

    def _refresh_action_state(self) -> None:
        if self._open_raw_action:
            path: Path | None = None
            if self._controller:
                path = self._controller.raw_log_path()
            if path is None and self.config.persist_csv:
                path = self.config.persist_path
            enabled = self.config.persist_csv and path is not None and Path(path).exists()
            self._open_raw_action.setEnabled(enabled)
        self._update_configuration_warning()

    def _is_configuration_valid(self) -> bool:
        serial = self.config.serial
        if self.config.sample_file:
            return True
        if serial.enabled and serial.port:
            return True
        return False

    def _configuration_issue_text(self) -> str:
        serial = self.config.serial
        if serial.enabled and not serial.port:
            return "Serial data source is enabled but no COM port is configured."
        return "No data source configured. Select a COM port or choose a sample file."

    def _update_configuration_warning(self) -> None:
        if not self._config_warning:
            return
        if self._is_configuration_valid():
            self._config_warning.hide()
            return
        self._config_warning.set_message(self._configuration_issue_text())
        self._config_warning.update_geometry()
        self._config_warning.show()
        self._config_warning.raise_()

    def _apply_sidebar_width(self, width: int) -> None:
        if not self._main_splitter:
            return
        sizes = self._main_splitter.sizes()
        total = sum(sizes) if sizes and sum(sizes) > 0 else width + 600
        width = max(width, self.sidebar.minimumWidth())
        remaining = max(total - width, 1)
        self._main_splitter.setSizes([width, remaining])

    def _init_splitter_sizes(self) -> None:
        if not self._main_splitter:
            return
        width = self.sidebar.preferred_width()
        remaining = max(width * 2, 600)
        self._main_splitter.setSizes([width, remaining])

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.centralWidget() and event.type() in {QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show}:
            if self._config_warning:
                self._config_warning.update_geometry()
        return super().eventFilter(obj, event)


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

    def _on_row_color_change(self, key: str, color_hex: str) -> None:
        self._color_overrides[key] = color_hex
        self._preferences['parameter_colors'] = dict(self._color_overrides)
        save_preferences(self._preferences)
        if key in self._parameter_settings:
            self._parameter_settings[key] = replace(self._parameter_settings[key], color=color_hex)
        self.sidebar.apply_color(key, color_hex)
        self._apply_curve_color(key)


    def _toggle_auto_stop(self, enabled: bool) -> None:
        self._auto_stop_enabled = bool(enabled)
        self._preferences['auto_stop_full_battery'] = self._auto_stop_enabled
        save_preferences(self._preferences)
        self._auto_stop_since = None
        self._auto_stop_triggered = False
        status_text = "Auto-stop when battery is full for 1 minute"
        status_state = "enabled" if self._auto_stop_enabled else "disabled"
        self.status.showMessage(f"{status_text} {status_state}", 3000)


    def _update_auto_stop(self, status_detail: StatusDetail | None) -> None:
        if not self._auto_stop_enabled or self._controller is None:
            self._auto_stop_since = None
            return
        if self._auto_stop_triggered:
            return

        raw_value = status_detail.raw_value if status_detail else None
        is_full = False
        if isinstance(raw_value, int):
            battery_state = raw_value & 0b111
            if battery_state in {3, 5}:
                is_full = True

        if is_full:
            now = datetime.now()
            if self._auto_stop_since is None:
                self._auto_stop_since = now
                return
            if now - self._auto_stop_since >= timedelta(minutes=1):
                self._auto_stop_triggered = True
                self._auto_stop_since = None
                try:
                    self._controller.stop()
                except Exception as exc:  # pragma: no cover - controller stop rarely fails
                    self.status.showMessage(f"Stopping acquisition failed: {exc}", 6000)
                else:
                    self.status.showMessage("Acquisition stopped after battery was full for 60 seconds.", 5000)
                self._refresh_action_state()
        else:
            self._auto_stop_since = None


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
        for key in record.keys():
            if key not in self._parameter_settings:
                continue
            self._auto_initialized.add(key)

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
        if self._controller:
            self._controller.update_export_meta(meta)
        self._handle_meta_parameters(meta)
        last_record = records[-1]
        status_detail = decode_status(last_record.get("P05"), self.config.status_bits)
        self.status_badges.update_state(meta, status_detail)
        self.meta_panel.update_meta(meta, last_record.get("P05"), status_detail)
        self._update_auto_stop(status_detail)

        self._auto_initialize_from_record(last_record)
        self._update_active_parameter_values(last_record)

        x_data = self._extract_x(records)
        self._update_curves(x_data, records)

    def _on_data_reset(self) -> None:
        self._last_records = []
        self._auto_initialized.clear()
        self._auto_stop_since = None
        self._auto_stop_triggered = False
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
        override = getattr(self, '_color_overrides', {}).get(key)
        if override:
            return override
        setting = getattr(self, '_parameter_settings', {}).get(key) if hasattr(self, '_parameter_settings') else None
        info = PARAMETERS.get(key)
        label = ''
        if setting and setting.label:
            label = setting.label.lower()
        elif info and info.description:
            label = info.description.lower()
        unit = ''
        if setting and setting.unit:
            unit = setting.unit.lower()
        elif info and info.unit:
            unit = info.unit.lower()

        battery_keys = {'P40','P41','P42','P45','P46','P72','P90','P91','P92','P50','P51','P52','P55','P56'}
        control_keys = {'P43','P44','P53','P54','P57'}
        temperature_keys = {'P60','P61','P62','P73','P74','P75','P76'}
        resistance_keys = {'P80','P81'}

        key_upper = key.upper()
        if key_upper in battery_keys or 'batterie' in label or 'battery' in label:
            return colors.PRIMARY
        if key_upper in control_keys or 'stell' in label or 'control' in label:
            return colors.SECONDARY
        if key_upper in temperature_keys or 'temp' in label:
            return colors.ACCENT
        if key_upper in resistance_keys or 'widerstand' in label or 'resistance' in label:
            return colors.SECONDARY_LIGHT
        if 'leistung' in label or 'power' in label:
            return colors.PRIMARY_LIGHT

        palette = [colors.PRIMARY, colors.SECONDARY, colors.ACCENT, colors.SECONDARY_LIGHT, colors.PRIMARY_LIGHT, colors.TEXT]
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

    def _collect_series_for_pdf(
        self, x_data: Sequence[float], stats: Sequence[ParameterStatistic]
    ) -> List[ParameterSeries]:
        def fmt(value: float) -> str:
            text = ("%.3f" % value).rstrip("0").rstrip(".")
            return text if text else "0"

        series_list: List[ParameterSeries] = []
        for stat in stats:
            setting = self._parameter_settings.get(stat.key)
            color = setting.color if setting else stat.color
            xs: List[float] = []
            ys: List[float] = []
            for x_value, record in zip(x_data, self._last_records):
                value = record.get(stat.key)
                if isinstance(value, (int, float)):
                    xs.append(float(x_value))
                    ys.append(float(value))
            if len(xs) < 2:
                continue
            info = PARAMETERS.get(stat.key)
            descriptor = info.description if info and info.description else stat.label
            unit_suffix = f" {stat.unit}" if stat.unit else ""
            explanation = (
                f"{descriptor}. Range {fmt(stat.min_value)} - {fmt(stat.max_value)}{unit_suffix}. "
                f"Latest value {fmt(stat.last_value)}{unit_suffix}."
            )
            series_list.append(
                ParameterSeries(
                    key=stat.key,
                    label=stat.label,
                    unit=stat.unit,
                    color=color,
                    x_values=tuple(xs),
                    y_values=tuple(ys),
                    explanation=explanation,
                )
            )
        return series_list

    @staticmethod
    def _status_badge_snapshot(detail: StatusDetail | None) -> Dict[str, str]:
        snapshot: Dict[str, str] = {}
        if not detail:
            return snapshot
        entries = list(detail.badges)
        for entry in detail.details:
            if entry not in entries:
                entries.append(entry)
        for entry in entries:
            if ": " not in entry:
                continue
            raw_key, raw_value = entry.split(": ", 1)
            key = STATUS_FIELD_TRANSLATIONS.get(_normalize_status_label(raw_key), raw_key.strip())
            clean_value = raw_value.strip()
            value = STATUS_VALUE_TRANSLATIONS.get(_normalize_status_label(clean_value), clean_value)
            snapshot[key] = value
        return snapshot



    def _collect_status_markers(
        self,
        x_data: Sequence[float],
        records: Sequence[Dict[str, Number | str]],
    ) -> List[StatusMarker]:
        markers: List[StatusMarker] = []
        if not x_data or not records:
            return markers
        limit = max(0, len(records) - 1)
        prev_snapshot: Dict[str, str] | None = None
        for idx, (x_value, record) in enumerate(zip(x_data, records)):
            if idx >= limit:
                break
            detail = decode_status(record.get("P05"), self.config.status_bits)
            snapshot = self._status_badge_snapshot(detail)
            if prev_snapshot is None:
                prev_snapshot = snapshot
                continue
            if snapshot != prev_snapshot:
                changes: List[str] = []
                keys = sorted(set(prev_snapshot.keys()) | set(snapshot.keys()))
                for key in keys:
                    before = prev_snapshot.get(key)
                    after = snapshot.get(key)
                    if before == after:
                        continue
                    if before and after:
                        changes.append(f"{key}: {before} -> {after}")
                    elif after:
                        changes.append(f"{key}: {after}")
                    elif before:
                        changes.append(f"{key}: {before} -> -")
                if not changes:
                    changes.append("Status changed")
                markers.append(StatusMarker(position=float(x_value), label=" | ".join(changes[:3])))
            prev_snapshot = snapshot
        return markers

    def _open_raw_data(self) -> None:
        if not self.config.persist_csv:
            self.status.showMessage("Raw data logging is disabled", 3000)
            return
        path = None
        if self._controller:
            path = self._controller.raw_log_path()
        if path is None:
            path = self.config.persist_path
        if path is None:
            self.status.showMessage("No raw data file available", 3000)
            return
        path = Path(path)
        if not path.exists():
            self.status.showMessage("No raw data file available", 3000)
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    def _export_pdf(self) -> None:
        if not self._last_records:
            QtWidgets.QMessageBox.information(
                self,
                "No measurement report",
                "No telemetry data received yet.",
            )
            return

        meta = self.databus.meta()
        if self._controller:
            export_stem = self._controller.export_stem(meta)
            log_path = self._controller.raw_log_path()
        else:
            export_stem = datetime.now().strftime('%Y%m%d_%H%M%S_raw')
            log_path = None

        if log_path is not None:
            default_dir = Path(log_path).parent
        elif self.config.persist_path:
            default_dir = self.config.persist_path.parent
        else:
            default_dir = Path.cwd() / 'logs'
        default_dir.mkdir(parents=True, exist_ok=True)
        suggested = default_dir / export_stem
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save measurement report",
            str(suggested),
            "PDF files (*.pdf)",
        )
        if not selected:
            return

        target = Path(selected)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")

        last_record = self._last_records[-1]
        status_value = last_record.get("P05")
        status_detail = decode_status(status_value, self.config.status_bits)
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

        series_list = self._collect_series_for_pdf(x_data, visible_stats)
        status_markers = self._collect_status_markers(x_data, self._last_records)

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
                series_list,
                status_markers,
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
                f"The report could not be generated:\n{exc}",
            )
            return

        self.status.showMessage(f"Report saved to {target}", 4000)

    def _open_config_dialog(self) -> None:
        if not self._controller:
            return
        dialog = ConfigDialog(self.config, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        new_config = dialog.result_config()
        if new_config is None:
            return
        if self._controller.apply_config(new_config):
            self.status.showMessage("Configuration updated", 3000)

    def _handle_status_message(self, message: str, timeout: int) -> None:
        self.status.showMessage(message, timeout)

    def _handle_acquisition_error(self, message: str) -> None:
        QtWidgets.QMessageBox.warning(self, "Data source", message)
        self.status.showMessage(message, 5000)

    def _on_config_changed(self, config: AppConfig) -> None:
        self.config = config
        self.status_badges.set_config(config)
        self._refresh_action_state()
        interval = max(15, int(1000 / max(1.0, self.config.ui_refresh_hz)))
        self._timer.setInterval(interval)


__all__ = ["MainWindow"]
