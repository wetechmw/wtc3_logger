"""Qt configuration dialog for data source and raw data logging."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

from PySide6 import QtWidgets

from ..config import AppConfig


class ConfigDialog(QtWidgets.QDialog):
    """Allow switching between serial input and sample playback."""

    def __init__(self, config: AppConfig, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.setModal(True)
        self._config = config
        self._result: Optional[AppConfig] = None

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self._build_source_group(main_layout)
        self._build_raw_group(main_layout)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel |
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        self.resize(480, 0)

    def result_config(self) -> Optional[AppConfig]:
        return self._result

    def accept(self) -> None:
        try:
            self._result = self._build_config()
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid input", str(exc))
            return
        super().accept()

    def _build_source_group(self, layout: QtWidgets.QVBoxLayout) -> None:
        group = QtWidgets.QGroupBox("Data source")
        group_layout = QtWidgets.QVBoxLayout(group)
        group_layout.setSpacing(6)

        self._serial_radio = QtWidgets.QRadioButton("Use serial interface")
        self._sample_radio = QtWidgets.QRadioButton("Replay sample file")

        self._serial_radio.toggled.connect(self._update_source_widgets)
        self._sample_radio.toggled.connect(self._update_source_widgets)

        radio_group = QtWidgets.QButtonGroup(self)
        radio_group.setExclusive(True)
        radio_group.addButton(self._serial_radio)
        radio_group.addButton(self._sample_radio)

        group_layout.addWidget(self._serial_radio)
        serial_widget = QtWidgets.QWidget()
        serial_form = QtWidgets.QFormLayout(serial_widget)
        serial_form.setContentsMargins(24, 0, 0, 0)
        serial_form.setSpacing(6)

        self._serial_port = QtWidgets.QLineEdit()
        self._serial_port.setPlaceholderText("COM3 or /dev/ttyUSB0")
        self._serial_baud = QtWidgets.QSpinBox()
        self._serial_baud.setRange(1200, 1_000_000)
        self._serial_baud.setSingleStep(1200)
        serial_form.addRow("Port", self._serial_port)
        serial_form.addRow("Baud rate", self._serial_baud)
        group_layout.addWidget(serial_widget)

        group_layout.addWidget(self._sample_radio)
        sample_widget = QtWidgets.QWidget()
        sample_layout = QtWidgets.QHBoxLayout(sample_widget)
        sample_layout.setContentsMargins(24, 0, 0, 0)
        sample_layout.setSpacing(6)
        self._sample_path = QtWidgets.QLineEdit()
        self._sample_browse = QtWidgets.QPushButton("Browse")
        self._sample_browse.clicked.connect(self._browse_sample)
        sample_layout.addWidget(self._sample_path, 1)
        sample_layout.addWidget(self._sample_browse)
        group_layout.addWidget(sample_widget)

        layout.addWidget(group)

        if self._config.sample_file:
            self._sample_radio.setChecked(True)
            self._sample_path.setText(str(self._config.sample_file))
        elif self._config.serial.enabled and self._config.serial.port:
            self._serial_radio.setChecked(True)
        else:
            self._serial_radio.setChecked(True)
        self._serial_port.setText(self._config.serial.port)
        self._serial_baud.setValue(int(self._config.serial.baudrate))

        self._update_source_widgets(False)

    def _build_raw_group(self, layout: QtWidgets.QVBoxLayout) -> None:
        group = QtWidgets.QGroupBox("Raw data logging")
        group_layout = QtWidgets.QVBoxLayout(group)
        group_layout.setSpacing(6)

        self._persist_checkbox = QtWidgets.QCheckBox("Record raw telemetry stream")
        self._persist_checkbox.setChecked(self._config.persist_csv)
        self._persist_checkbox.toggled.connect(self._update_persist_widgets)
        group_layout.addWidget(self._persist_checkbox)

        raw_widget = QtWidgets.QWidget()
        raw_layout = QtWidgets.QHBoxLayout(raw_widget)
        raw_layout.setContentsMargins(24, 0, 0, 0)
        raw_layout.setSpacing(6)
        self._raw_path = QtWidgets.QLineEdit(str(self._config.persist_path))
        self._raw_browse = QtWidgets.QPushButton("Choose location")
        self._raw_browse.clicked.connect(self._browse_raw)
        raw_layout.addWidget(self._raw_path, 1)
        raw_layout.addWidget(self._raw_browse)
        group_layout.addWidget(raw_widget)

        layout.addWidget(group)

        self._update_persist_widgets(self._config.persist_csv)

    def _update_source_widgets(self, _: bool) -> None:
        serial_active = self._serial_radio.isChecked()
        sample_active = self._sample_radio.isChecked()
        self._serial_port.setEnabled(serial_active)
        self._serial_baud.setEnabled(serial_active)
        self._sample_path.setEnabled(sample_active)
        self._sample_browse.setEnabled(sample_active)

    def _update_persist_widgets(self, checked: bool) -> None:
        self._raw_path.setEnabled(checked)
        self._raw_browse.setEnabled(checked)

    def _browse_sample(self) -> None:
        current_dir = self._sample_path.text().strip()
        if not current_dir:
            current_dir = str((self._config.sample_file or Path.cwd()).parent)
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select sample file",
            current_dir,
            "Text files (*.txt);;All files (*)",
        )
        if selected:
            self._sample_path.setText(selected)
            self._sample_radio.setChecked(True)
            self._update_source_widgets(True)

    def _browse_raw(self) -> None:
        current = self._raw_path.text().strip() or str(self._config.persist_path)
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save raw data to",
            current,
            "Raw data (*.tsv);;All files (*)",
        )
        if selected:
            self._raw_path.setText(selected)
            self._persist_checkbox.setChecked(True)
            self._update_persist_widgets(True)

    def _build_config(self) -> AppConfig:
        serial_enabled = self._serial_radio.isChecked()
        port = self._serial_port.text().strip()
        if serial_enabled and not port:
            raise ValueError("Please provide a serial port.")
        baudrate = int(self._serial_baud.value())
        serial_config = replace(
            self._config.serial,
            port=port if serial_enabled else "",
            baudrate=baudrate,
            enabled=serial_enabled,
        )

        sample_path: Optional[Path] = None
        if self._sample_radio.isChecked():
            sample_text = self._sample_path.text().strip()
            if not sample_text:
                raise ValueError("Please choose a sample file.")
            sample_path = Path(sample_text).expanduser()
            if sample_path.exists():
                sample_path = sample_path.resolve()

        persist_enabled = self._persist_checkbox.isChecked()
        raw_text = self._raw_path.text().strip()
        if persist_enabled and not raw_text:
            raise ValueError("Please choose a raw data location.")
        persist_path = self._config.persist_path
        if raw_text:
            candidate = Path(raw_text).expanduser()
            try:
                persist_path = candidate.resolve(strict=False)
            except Exception:
                persist_path = candidate

        return replace(
            self._config,
            serial=serial_config,
            sample_file=sample_path,
            persist_csv=persist_enabled,
            persist_path=persist_path,
        )


__all__ = ["ConfigDialog"]
