"""Runtime helpers to manage data acquisition threads."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, TextIO

import datetime as dt

from PySide6 import QtCore

from .config import AppConfig
from .databus import DataBus
from .parser import Parser
from .export_utils import build_export_stem
from .serial_reader import FileTail, SerialReader


class AcquisitionError(RuntimeError):
    """Raised when a data source cannot be started."""


class AcquisitionController(QtCore.QObject):
    """Controls the active data source and keeps the DataBus in sync."""

    status_message = QtCore.Signal(str, int)
    error_occurred = QtCore.Signal(str)
    config_changed = QtCore.Signal(AppConfig)

    def __init__(self, config: AppConfig, databus: DataBus, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._databus = databus
        self._parser = Parser()
        self._parser.on_record(self._handle_record)
        self._parser.on_data_header(lambda _: self._databus.reset())
        self._thread: FileTail | SerialReader | None = None
        self._session_started = dt.datetime.now()
        self._session_stem = self._session_started.strftime("%Y%m%d_%H%M%S")
        self._raw_log: TextIO | None = None
        self._raw_log_path: Path | None = None
        self._raw_log_dir: Path | None = None
        self._raw_log_suffix = ".tsv"
        self._export_stem: str | None = None

    @property
    def config(self) -> AppConfig:
        return self._config

    def start(self) -> None:
        """Start the currently configured data source."""

        self.stop()
        try:
            self._start_with_config(self._config)
        except AcquisitionError as exc:
            self.error_occurred.emit(str(exc))

    def stop(self) -> None:
        """Stop the active data source thread if any."""

        if self._thread is None:
            return
        try:
            self._thread.stop()
            self._thread.join(timeout=1.0)
        finally:
            self._thread = None
            self._close_raw_log()

    def apply_config(self, new_config: AppConfig) -> bool:
        """Apply a new configuration and restart the data source."""

        previous_config = self._config
        self.stop()
        try:
            self._start_with_config(new_config)
        except AcquisitionError as exc:
            try:
                self._start_with_config(previous_config)
            except AcquisitionError:
                self._config = previous_config
            self.error_occurred.emit(str(exc))
            return False
        return True

    def _start_with_config(self, config: AppConfig) -> None:
        self._config = config
        self._databus.reset()
        self._configure_raw_log(config.persist_path if config.persist_csv else None)
        try:
            thread = self._build_thread(config)
        except Exception:
            self._close_raw_log()
            raise
        self._thread = thread
        if thread is not None:
            thread.start()
            self.status_message.emit(self._describe_source(config), 4000)
        else:
            self.status_message.emit("No data source configured.", 4000)
        self.config_changed.emit(self._config)

    def _build_thread(self, config: AppConfig) -> FileTail | SerialReader | None:
        if config.sample_file:
            sample_path = Path(config.sample_file)
            if not sample_path.exists():
                raise AcquisitionError(f"Sample file not found: {sample_path}")
            return FileTail(sample_path, self._handle_raw_line, loop=True)
        if config.serial.enabled and config.serial.port:
            try:
                return SerialReader(
                    config.serial.port,
                    config.serial.baudrate,
                    config.serial.newline,
                    self._handle_raw_line,
                )
            except Exception as exc:
                raise AcquisitionError(f"Serial connection failed: {exc}") from exc
        return None

    def _handle_record(self, meta: dict[str, str], record: dict[str, object]) -> None:
        self._databus.append(meta, record)
        if meta and self._config.persist_csv:
            self.update_export_meta(meta)

    def _handle_raw_line(self, raw: str) -> None:
        if self._raw_log:
            try:
                self._raw_log.write(raw)
                self._raw_log.write("\n")
                self._raw_log.flush()
            except Exception as exc:  # pragma: no cover - disk issues are rare
                self.error_occurred.emit(f"Raw data logging failed: {exc}")
                self._close_raw_log()
        self._parser.feed_line(raw)

    def _configure_raw_log(self, path: Path | None) -> None:
        self._close_raw_log()
        self._raw_log_path = None
        self._raw_log_dir = None
        self._raw_log_suffix = '.tsv'
        self._export_stem = None
        if path is None:
            return
        resolved = path
        if resolved.suffix:
            self._raw_log_dir = resolved.parent
            self._raw_log_suffix = resolved.suffix
            initial_stem = resolved.stem or f"{self._session_stem}_raw"
        else:
            self._raw_log_dir = resolved
            initial_stem = f"{self._session_stem}_raw"
        assert self._raw_log_dir is not None
        self._raw_log_dir.mkdir(parents=True, exist_ok=True)
        initial_path = self._raw_log_dir / f"{initial_stem}{self._raw_log_suffix}"
        try:
            self._raw_log = initial_path.open('a', encoding='utf-8', newline='')
        except Exception as exc:
            self.error_occurred.emit(f"Raw data logging unavailable: {exc}")
            self._raw_log = None
            self._raw_log_path = None
            return
        self._raw_log_path = initial_path
        self._config.persist_path = initial_path
        if resolved.suffix:
            self._export_stem = initial_stem

    def _close_raw_log(self) -> None:
        current_path = self._raw_log_path
        if self._raw_log:
            try:
                self._raw_log.flush()
            finally:
                self._raw_log.close()
        self._raw_log = None
        if current_path and self._raw_log_dir and self._export_stem:
            target = self._raw_log_dir / f"{self._export_stem}{self._raw_log_suffix}"
            if target != current_path and current_path.exists():
                try:
                    current_path.replace(target)
                except Exception:  # pragma: no cover - depends on filesystem state
                    pass
                else:
                    current_path = target
                    self._config.persist_path = target
        self._raw_log_path = current_path


    def update_export_meta(self, meta: dict[str, str]) -> None:
        if not self._raw_log_dir:
            return
        new_stem = build_export_stem(self._session_started, meta)
        if not new_stem or new_stem == self._export_stem:
            return
        target = self._raw_log_dir / f"{new_stem}{self._raw_log_suffix}"
        self._export_stem = new_stem
        if self._raw_log is None:
            self._raw_log_path = target
            self._config.persist_path = target
            return

        current_path = self._raw_log_path
        if current_path == target:
            self._raw_log_path = target
            self._config.persist_path = target
            return

        try:
            self._raw_log.flush()
        except Exception:
            pass
        try:
            self._raw_log.close()
        finally:
            self._raw_log = None

        reopened_path = target
        rename_exc: Exception | None = None
        if current_path and current_path.exists():
            try:
                current_path.replace(target)
            except Exception as exc:  # pragma: no cover - depends on filesystem state
                rename_exc = exc
                reopened_path = current_path

        try:
            self._raw_log = reopened_path.open('a', encoding='utf-8', newline='')
        except Exception as exc:  # pragma: no cover - disk issues are rare
            self.error_occurred.emit(f"Raw data logging unavailable: {exc}")
            self._raw_log = None
            self._raw_log_path = None
            self._config.persist_path = None
            return

        self._raw_log_path = reopened_path
        self._config.persist_path = reopened_path
        if rename_exc:
            self.error_occurred.emit(f"Raw data log rename failed: {rename_exc}")


    def export_stem(self, meta: dict[str, str] | None = None) -> str:
        if meta is not None:
            self.update_export_meta(meta)
        if self._export_stem:
            return self._export_stem
        return f"{self._session_stem}_raw"

    def raw_log_path(self) -> Path | None:
        return self._raw_log_path

    def _describe_source(self, config: AppConfig) -> str:
        if config.sample_file:
            sample_path = Path(config.sample_file)
            return f"Streaming from sample file: {sample_path.name}"
        if config.serial.enabled and config.serial.port:
            return f"Serial connection active ({config.serial.port} @ {config.serial.baudrate})"
        return "No input configured."


__all__ = ["AcquisitionController", "AcquisitionError"]
