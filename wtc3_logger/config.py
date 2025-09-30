"""Konfigurationsmodelle für den WTC3 Logger."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:  # pragma: no cover - optional dependency für reine Tests
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


def _expand(path: Optional[str]) -> Optional[Path]:
    if path is None:
        return None
    return Path(path).expanduser().resolve()


@dataclass(slots=True)
class SerialConfig:
    """Konfiguration der seriellen Schnittstelle."""

    port: str = ""
    baudrate: int = 115200
    newline: str = "\n"
    enabled: bool = False


@dataclass(slots=True)
class AppConfig:
    """Hauptkonfiguration der Anwendung."""

    serial: SerialConfig = field(default_factory=SerialConfig)
    sample_file: Optional[Path] = None
    persist_csv: bool = False
    persist_path: Path = field(default_factory=lambda: Path.cwd() / "logs" / "wtc3_log.csv")
    ui_refresh_hz: float = 15.0
    max_points: int = 10_000
    status_bits: dict[int, str] = field(default_factory=dict)
    strategy_labels: dict[str, str] = field(default_factory=dict)

    def resolved_sample(self) -> Optional[Path]:
        return self.sample_file

    @classmethod
    def from_yaml(cls, file: Path) -> "AppConfig":
        if yaml is None:
            raise RuntimeError("PyYAML ist nicht installiert")
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        serial_data = data.get("serial", {})
        serial = SerialConfig(
            port=serial_data.get("port", ""),
            baudrate=int(serial_data.get("baudrate", 115200)),
            newline=str(serial_data.get("newline", "\n")),
            enabled=bool(serial_data.get("enabled", False)),
        )
        sample = data.get("sample_file")
        persist = data.get("persist_csv", False)
        persist_path = data.get("persist_path")
        status_bits_raw = data.get("status_bits", {})
        status_bits: dict[int, str] = {}
        if isinstance(status_bits_raw, dict):
            for key, value in status_bits_raw.items():
                try:
                    bit = int(key)
                except (TypeError, ValueError):
                    continue
                status_bits[bit] = str(value)
        strategy_labels_raw = data.get("strategy_labels", {})
        strategy_labels: dict[str, str] = {}
        if isinstance(strategy_labels_raw, dict):
            for key, value in strategy_labels_raw.items():
                strategy_labels[str(key)] = str(value)
        return cls(
            serial=serial,
            sample_file=_expand(sample),
            persist_csv=bool(persist),
            persist_path=_expand(persist_path) if persist_path else Path.cwd() / "logs" / "wtc3_log.csv",
            ui_refresh_hz=float(data.get("ui_refresh_hz", 15.0)),
            max_points=int(data.get("max_points", 10_000)),
            status_bits=status_bits,
            strategy_labels=strategy_labels,
        )


DEFAULT_CONFIG = AppConfig()
