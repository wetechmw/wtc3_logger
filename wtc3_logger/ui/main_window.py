"""Qt UI für den Telemetrie-Viewer im Wetech-Stil."""
from __future__ import annotations

from typing import Dict, Iterable, List

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..config import AppConfig
from ..databus import DataBus
from ..parser import PARAMETERS, Number
from ..status import decode_status, label_strategy
from . import colors


SERIES_DEFAULT = ["P40", "P45", "P50", "P52", "P60", "P61"]


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


class SeriesSelector(QtWidgets.QWidget):
    """Checkboxen zur Auswahl der Kurven."""

    toggled = QtCore.Signal(str, bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._boxes: Dict[str, QtWidgets.QCheckBox] = {}
        self.setLayout(layout)

    def set_series(self, keys: Iterable[str], active: Iterable[str]) -> None:
        layout = self.layout()
        assert isinstance(layout, QtWidgets.QHBoxLayout)
        active_set = set(active)
        for key in keys:
            if key in self._boxes:
                box = self._boxes[key]
            else:
                info = PARAMETERS.get(key)
                label = f"{key} – {info.description}" if info else key
                box = QtWidgets.QCheckBox(label)
                box.setStyleSheet(
                    "QCheckBox {color: %s;} QCheckBox::indicator { width: 18px; height: 18px;}"
                    % colors.TEXT
                )
                box.toggled.connect(lambda state, k=key: self.toggled.emit(k, state))
                layout.addWidget(box)
                self._boxes[key] = box
            box.setChecked(key in active_set)


class MainWindow(QtWidgets.QMainWindow):
    """Zentrales Fenster mit Plot, Tabelle und Metadaten."""

    def __init__(self, databus: DataBus, config: AppConfig, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.databus = databus
        self.config = config
        self.setWindowTitle("WeTech Telemetrie Monitor")
        self.resize(1280, 720)
        self._curves: Dict[str, pg.PlotDataItem] = {}
        self._plot_candidates: List[str] = [
            key for key, info in PARAMETERS.items() if info.unit or key in SERIES_DEFAULT
        ]
        self._series_active: List[str] = [k for k in SERIES_DEFAULT if k in self._plot_candidates]
        self._x_key = "P06"

        self._init_palette()
        self._init_ui()

        self._timer = QtCore.QTimer(self)
        interval = max(15, int(1000 / max(1.0, config.ui_refresh_hz)))
        self._timer.timeout.connect(self.refresh)
        self._timer.start(interval)

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
        central = QtWidgets.QWidget(self)
        central_layout = QtWidgets.QVBoxLayout(central)
        central_layout.setContentsMargins(12, 12, 12, 12)
        central_layout.setSpacing(10)

        header = QtWidgets.QLabel("WTC3 Telemetrie")
        header.setStyleSheet(
            "font-size: 24px; font-weight: 600; color: %s; letter-spacing: 0.5px;" % colors.PRIMARY
        )
        central_layout.addWidget(header)

        self.status_badges = StatusBadgeBar(self.config)
        central_layout.addWidget(self.status_badges)

        self.meta_widget = MetaWidget()
        central_layout.addWidget(self.meta_widget)

        self.selector = SeriesSelector()
        self.selector.set_series(self._plot_candidates, self._series_active)
        self.selector.toggled.connect(self._on_toggle_series)
        central_layout.addWidget(self.selector)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        central_layout.addWidget(splitter, 1)

        self.plot = self._create_plot()
        splitter.addWidget(self.plot)

        self.table = self._create_table()
        splitter.addWidget(self.table)

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

    def _create_plot(self) -> pg.PlotWidget:
        pg.setConfigOptions(antialias=True)
        plot = pg.PlotWidget(background=colors.BACKGROUND)
        plot.getPlotItem().getAxis("left").setPen(pg.mkPen(colors.MUTED_TEXT))
        plot.getPlotItem().getAxis("bottom").setPen(pg.mkPen(colors.MUTED_TEXT))
        plot.getPlotItem().getAxis("left").setTextPen(pg.mkPen(colors.MUTED_TEXT))
        plot.getPlotItem().getAxis("bottom").setTextPen(pg.mkPen(colors.MUTED_TEXT))
        plot.showGrid(x=True, y=True, alpha=0.2)
        return plot

    def _create_table(self) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget()
        table.setColumnCount(len(self._series_active) + 1)
        headers = ["Zeit (P06)"] + [
            PARAMETERS[key].description if key in PARAMETERS else key for key in self._series_active
        ]
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setStyleSheet(
            "QTableWidget {background: white; alternate-background-color: %s; color: %s;}" % (colors.BACKGROUND, colors.TEXT)
        )
        return table

    def _on_toggle_series(self, key: str, state: bool) -> None:
        if state:
            if key not in self._series_active:
                self._series_active.append(key)
        else:
            if key in self._series_active:
                self._series_active.remove(key)
        self._series_active = [k for k in self._plot_candidates if k in self._series_active]
        self.table.setColumnCount(len(self._series_active) + 1)
        headers = ["Zeit (P06)"] + [
            PARAMETERS[key].description if key in PARAMETERS else key for key in self._series_active
        ]
        self.table.setHorizontalHeaderLabels(headers)
        self.status.showMessage(f"Aktive Serien: {', '.join(self._series_active)}", 3000)

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
        for key in self._series_active:
            y_vals: List[float] = []
            for record in records:
                value = record.get(key)
                if isinstance(value, (int, float)):
                    y_vals.append(float(value))
            if key not in self._curves:
                color = self._color_for_key(key)
                pen = pg.mkPen(color=color, width=2)
                self._curves[key] = self.plot.plot(name=key, pen=pen)
            self._curves[key].setData(x_data[: len(y_vals)], y_vals)
        # Ausblenden nicht aktiver Kurven
        for key in list(self._curves.keys()):
            if key not in self._series_active:
                self.plot.removeItem(self._curves.pop(key))

    def _color_for_key(self, key: str) -> str:
        palette = [colors.PRIMARY, colors.PRIMARY_LIGHT, colors.ACCENT, "#3DC1D3", "#6A67CE", "#FFB347"]
        idx = hash(key) % len(palette)
        return palette[idx]

    def _update_table(self, records: List[Dict[str, Number | str]]) -> None:
        rows = min(100, len(records))
        self.table.setRowCount(rows)
        recent = records[-rows:]
        active_keys = list(self._series_active)
        for r, record in enumerate(recent):
            time_value = record.get("P06", "-")
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(time_value)))
            for c, key in enumerate(active_keys, start=1):
                value = record.get(key, "-")
                if isinstance(value, float):
                    display = f"{value:.2f}"
                else:
                    display = str(value)
                self.table.setItem(r, c, QtWidgets.QTableWidgetItem(display))
        self.table.scrollToBottom()

    def _open_csv(self) -> None:
        path = self.config.persist_path
        if not path.exists():
            self.status.showMessage("Keine CSV-Datei vorhanden", 3000)
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))


__all__ = ["MainWindow"]
