"""Qt UI für den Telemetrie-Viewer im Wetech-Stil."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Iterable, List

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..config import AppConfig
from ..databus import DataBus
from ..parser import PARAMETERS, Number
from ..status import decode_status, label_strategy
from . import colors


SERIES_DEFAULT = ["P40", "P45", "P50", "P52", "P60", "P61"]


@dataclass(slots=True)
class ParameterSetting:
    """Konfiguration für einen Telemetrie-Parameter."""

    key: str
    label: str
    unit: str | None
    color: str
    visible: bool
    show_in_graph: bool
    show_in_table: bool
    allow_graph: bool = True


class ColorButton(QtWidgets.QPushButton):
    """Kleiner Button, der die Linienfarbe repräsentiert."""

    color_changed = QtCore.Signal(str)

    def __init__(self, color: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QtGui.QColor(color)
        self.setFixedSize(28, 28)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._apply_style()
        self.clicked.connect(self._choose_color)

    def _choose_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(self._color, self, "Farbe wählen")
        if color.isValid():
            self._color = color
            self._apply_style()
            self.color_changed.emit(color.name())

    def _apply_style(self) -> None:
        border = colors.PRIMARY_DARK
        self.setStyleSheet(
            "QPushButton {border: 2px solid %s; border-radius: 6px; background-color: %s;}\n"
            "QPushButton::hover {border-color: %s;}" % (border, self._color.name(), colors.PRIMARY)
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
        self._visible_box.setToolTip("Parameter aktivieren")
        self._visible_box.toggled.connect(self._emit_change)
        layout.addWidget(self._visible_box)

        info_label = QtWidgets.QLabel(f"{setting.key} – {setting.label}")
        info_label.setStyleSheet(
            "QLabel {color: %s; font-weight: 500;}" % colors.TEXT
        )
        layout.addWidget(info_label, 1)

        self._color_button = ColorButton(setting.color)
        self._color_button.setToolTip("Linienfarbe festlegen")
        self._color_button.color_changed.connect(self._on_color_changed)
        layout.addWidget(self._color_button)

        self._graph_box = QtWidgets.QCheckBox("Graph")
        self._graph_box.setChecked(setting.show_in_graph and setting.allow_graph)
        self._graph_box.setEnabled(setting.allow_graph)
        self._graph_box.toggled.connect(self._emit_change)
        layout.addWidget(self._graph_box)

        self._table_box = QtWidgets.QCheckBox("Liste")
        self._table_box.setChecked(setting.show_in_table)
        self._table_box.toggled.connect(self._emit_change)
        layout.addWidget(self._table_box)

        wrapper = QtWidgets.QHBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(container)

        self._update_enabled_state()

    def setting(self) -> ParameterSetting:
        return self._setting

    def _on_color_changed(self, color: str) -> None:
        self._setting = replace(self._setting, color=color)
        self.changed.emit(self._setting)

    def _emit_change(self) -> None:
        visible = self._visible_box.isChecked()
        show_graph = self._graph_box.isChecked() and self._graph_box.isEnabled()
        show_table = self._table_box.isChecked() and visible
        self._setting = replace(
            self._setting,
            visible=visible,
            show_in_graph=show_graph,
            show_in_table=show_table,
        )
        self._update_enabled_state()
        self.changed.emit(self._setting)

    def _update_enabled_state(self) -> None:
        visible = self._visible_box.isChecked()
        self._graph_box.setEnabled(self._setting.allow_graph and visible)
        self._color_button.setEnabled(self._setting.allow_graph and visible)
        self._table_box.setEnabled(visible)


class ParameterSidebar(QtWidgets.QWidget):
    """Zusammenklappbare Sidebar zur Parameterauswahl."""

    changed = QtCore.Signal(str, ParameterSetting)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: Dict[str, ParameterRow] = {}

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

        self.setMinimumWidth(260)
        self.setMaximumWidth(360)

    def populate(self, settings: Iterable[ParameterSetting]) -> None:
        # Entferne Platzhalter-Stretch, damit neue Elemente korrekt eingefügt werden.
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()

        grouped: Dict[str, list[ParameterSetting]] = {}
        for setting in settings:
            grouped.setdefault(setting.unit or "Allgemein", []).append(setting)

        for unit, entries in sorted(grouped.items(), key=lambda kv: kv[0]):
            header = QtWidgets.QLabel(unit)
            header.setStyleSheet(
                "QLabel {color: %s; font-size: 14px; font-weight: 600;}" % colors.MUTED_TEXT
            )
            self._scroll_layout.addWidget(header)
            for setting in sorted(entries, key=lambda s: s.label):
                row = ParameterRow(setting)
                row.changed.connect(self._on_row_changed)
                self._scroll_layout.addWidget(row)
                self._rows[setting.key] = row

        self._scroll_layout.addStretch(1)

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
            self.setMinimumWidth(260)
            self.setMaximumWidth(360)
        else:
            collapsed = max(48, self._toggle.sizeHint().width() + 16)
            self.setMinimumWidth(collapsed)
            self.setMaximumWidth(collapsed)


class UnitPlot(QtWidgets.QWidget):
    """Wrapper um einen Plot je SI-Einheit."""

    def __init__(self, unit: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QtWidgets.QLabel(f"Messwerte in {unit}")
        title.setStyleSheet(
            "QLabel {color: %s; font-weight: 600; font-size: 16px;}" % colors.PRIMARY_DARK
        )
        layout.addWidget(title)

        self.plot = pg.PlotWidget(background=colors.BACKGROUND)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.getPlotItem().getAxis("left").setPen(pg.mkPen(colors.MUTED_TEXT))
        self.plot.getPlotItem().getAxis("bottom").setPen(pg.mkPen(colors.MUTED_TEXT))
        self.plot.getPlotItem().getAxis("left").setTextPen(pg.mkPen(colors.MUTED_TEXT))
        self.plot.getPlotItem().getAxis("bottom").setTextPen(pg.mkPen(colors.MUTED_TEXT))
        self.plot.setLabel("left", f"Wert [{unit}]")
        self.plot.setLabel("bottom", "Zeit", "s")
        self.plot.addLegend()
        layout.addWidget(self.plot, 1)

        self.hide()

class MetaWidget(QtWidgets.QWidget):
    """Zeigt Meta-Informationen des aktuellen Blocks."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: Dict[str, QtWidgets.QLabel] = {}
        layout = QtWidgets.QFormLayout(self)
        layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(6)
        self.setLayout(layout)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(colors.BACKGROUND))
        self.setPalette(palette)

    def update_meta(self, meta: Dict[str, str]) -> None:
        layout = self.layout()
        assert isinstance(layout, QtWidgets.QFormLayout)
        for key, value in meta.items():
            if key not in self._labels:
                label = QtWidgets.QLabel(value)
                label.setStyleSheet(f"color: {colors.TEXT}; font-weight: 500;")
                caption = QtWidgets.QLabel(key)
                caption.setStyleSheet(f"color: {colors.MUTED_TEXT};")
                layout.addRow(caption, label)
                self._labels[key] = label
            else:
                self._labels[key].setText(value)


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

    def update_state(self, meta: Dict[str, str], record: Dict[str, Number | str] | None) -> None:
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
        if record and "P05" in record:
            statuses = decode_status(record.get("P05"), self._config.status_bits)

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

        self._init_palette()
        self._init_ui()

        self._timer = QtCore.QTimer(self)
        interval = max(15, int(1000 / max(1.0, config.ui_refresh_hz)))
        self._timer.timeout.connect(self.refresh)
        self._timer.start(interval)

    def _default_parameter_settings(self) -> Dict[str, ParameterSetting]:
        settings: Dict[str, ParameterSetting] = {}
        for key in self._parameter_order:
            info = PARAMETERS[key]
            allow_graph = bool(info.unit) and key != self._x_key
            visible = key in SERIES_DEFAULT
            show_in_graph = visible and allow_graph
            show_in_table = visible
            settings[key] = ParameterSetting(
                key=key,
                label=info.description,
                unit=info.unit,
                color=self._color_for_key(key),
                visible=visible,
                show_in_graph=show_in_graph,
                show_in_table=show_in_table,
                allow_graph=allow_graph,
            )
        return settings

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
        central_layout.setContentsMargins(12, 12, 12, 12)
        central_layout.setSpacing(12)

        self.sidebar = ParameterSidebar()
        self.sidebar.populate(self._parameter_settings.values())
        self.sidebar.changed.connect(self._on_parameter_setting_changed)
        central_layout.addWidget(self.sidebar)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        header = QtWidgets.QLabel("WTC3 Telemetrie")
        header.setStyleSheet(
            "font-size: 26px; font-weight: 600; color: %s; letter-spacing: 0.5px;" % colors.PRIMARY
        )
        content_layout.addWidget(header)

        self.status_badges = StatusBadgeBar(self.config)
        content_layout.addWidget(self.status_badges)

        self.meta_widget = MetaWidget()
        content_layout.addWidget(self.meta_widget)

        self._plots_scroll = QtWidgets.QScrollArea()
        self._plots_scroll.setWidgetResizable(True)
        self._plots_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._plots_scroll.setStyleSheet("QScrollArea {border: none;}")

        plots_container = QtWidgets.QWidget()
        self._plots_layout = QtWidgets.QVBoxLayout(plots_container)
        self._plots_layout.setContentsMargins(0, 0, 0, 0)
        self._plots_layout.setSpacing(16)

        for unit in self._available_units():
            unit_plot = UnitPlot(unit)
            self._unit_plots[unit] = unit_plot
            self._plots_layout.addWidget(unit_plot)

        self._plots_layout.addStretch(1)
        self._plots_scroll.setWidget(plots_container)
        content_layout.addWidget(self._plots_scroll, 1)

        self.table = self._create_table()
        content_layout.addWidget(self.table)

        central_layout.addWidget(content, 1)

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

        self.status = self.statusBar()
        self.status.setStyleSheet("color: %s" % colors.MUTED_TEXT)
        self.status.showMessage("Bereit")

        self._configure_table_headers()
        self._update_plot_visibility()

    def _available_units(self) -> List[str]:
        units = {info.unit for info in PARAMETERS.values() if info.unit}
        return sorted(units)

    def _create_table(self) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget()
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setStyleSheet(
            "QTableWidget {background: white; alternate-background-color: %s; color: %s;}" % (colors.BACKGROUND, colors.TEXT)
        )
        return table

    def _configure_table_headers(self) -> List[str]:
        keys = self._active_table_keys()
        headers = [f"Zeit ({self._x_key})"]
        for key in keys:
            setting = self._parameter_settings[key]
            headers.append(f"{key} – {setting.label}")
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        return keys

    def _active_table_keys(self) -> List[str]:
        return [
            key
            for key in self._parameter_order
            if (setting := self._parameter_settings.get(key))
            and setting.visible
            and setting.show_in_table
        ]

    def _active_graph_keys(self) -> List[str]:
        return [
            key
            for key in self._parameter_order
            if (setting := self._parameter_settings.get(key))
            and setting.visible
            and setting.show_in_graph
            and setting.unit
        ]

    def _active_units(self) -> Dict[str, List[str]]:
        units: Dict[str, List[str]] = {}
        for key in self._active_graph_keys():
            unit = self._parameter_settings[key].unit
            assert unit is not None
            units.setdefault(unit, []).append(key)
        return units

    def _update_plot_visibility(self) -> None:
        active_units = self._active_units()
        for unit, widget in self._unit_plots.items():
            widget.setVisible(unit in active_units)

    def _on_parameter_setting_changed(self, key: str, setting: ParameterSetting) -> None:
        self._parameter_settings[key] = setting
        if not setting.visible or not setting.show_in_graph:
            self._remove_curve(key)
        else:
            self._apply_curve_color(key)
        table_keys = self._configure_table_headers()
        self._update_plot_visibility()
        state = "aktiv" if setting.visible else "inaktiv"
        graph_flag = "ja" if setting.show_in_graph else "nein"
        table_flag = "ja" if setting.show_in_table else "nein"
        self.status.showMessage(
            f"{setting.key} {state} – Liste: {table_flag}, Graph: {graph_flag}",
            2500,
        )
        # Falls Spaltenanzahl sich verringert hat, vorhandene Items zurücksetzen
        if not table_keys:
            self.table.clearContents()

    def refresh(self) -> None:
        records = self.databus.snapshot()
        if not records:
            return
        meta = self.databus.meta()
        self.status_badges.update_state(meta, records[-1])
        self.meta_widget.update_meta(meta)

        x_data = self._extract_x(records)
        self._update_curves(x_data, records)
        self._update_table(records)

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
        active_units = self._active_units()
        active_keys = {key for keys in active_units.values() for key in keys}

        for key in list(self._curves.keys()):
            if key not in active_keys:
                self._remove_curve(key)

        for unit, keys in active_units.items():
            plot_widget = self._unit_plots[unit]
            plot_widget.setVisible(True)
            plot = plot_widget.plot
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

        for unit, widget in self._unit_plots.items():
            if unit not in active_units:
                widget.hide()

    def _color_for_key(self, key: str) -> str:
        palette = [colors.PRIMARY, colors.PRIMARY_LIGHT, colors.ACCENT, "#3DC1D3", "#6A67CE", "#FFB347"]
        idx = hash(key) % len(palette)
        return palette[idx]

    def _update_table(self, records: List[Dict[str, Number | str]]) -> None:
        table_keys = self._configure_table_headers()
        rows = min(100, len(records))
        self.table.setRowCount(rows)
        recent = records[-rows:]
        for r, record in enumerate(recent):
            time_value = record.get(self._x_key, "-")
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(time_value)))
            for c, key in enumerate(table_keys, start=1):
                value = record.get(key, "-")
                if isinstance(value, float):
                    display = f"{value:.2f}"
                else:
                    display = str(value)
                self.table.setItem(r, c, QtWidgets.QTableWidgetItem(display))
        if rows:
            self.table.scrollToBottom()

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


__all__ = ["MainWindow"]