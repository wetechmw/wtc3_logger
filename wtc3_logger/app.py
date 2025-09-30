"""Startpunkt für den Logger."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtWidgets

from .config import AppConfig, DEFAULT_CONFIG, SerialConfig
from .databus import DataBus
from .parser import Parser
from .serial_reader import FileTail, SerialReader
from .ui import MainWindow


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WTC3 Telemetrie Visualisierung")
    parser.add_argument("--config", type=Path, help="Pfad zu YAML-Konfiguration", default=None)
    parser.add_argument("--port", type=str, help="Serieller Port", default=None)
    parser.add_argument("--baud", type=int, help="Baudrate", default=None)
    parser.add_argument("--sample", action="store_true", help="Beispieldatei streamen")
    parser.add_argument("--sample-file", type=Path, help="Alternative Beispieldatei", default=None)
    parser.add_argument("--persist", action="store_true", help="Messwerte als CSV persistieren")
    return parser


def load_config(args: argparse.Namespace) -> AppConfig:
    config = DEFAULT_CONFIG
    if args.config:
        config = AppConfig.from_yaml(args.config)
    # CLI überschreibt Datei
    if args.port:
        config.serial = SerialConfig(port=args.port, baudrate=args.baud or config.serial.baudrate, enabled=True)
    if args.baud and not args.port:
        config.serial.baudrate = args.baud
    if args.sample:
        if args.sample_file:
            config.sample_file = args.sample_file
        else:
            config.sample_file = Path(__file__).with_name("sample.txt")
    elif args.sample_file:
        config.sample_file = args.sample_file
        config.serial.enabled = False
    if args.persist:
        config.persist_csv = True
    return config


def main(argv: Optional[list[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    arg_parser = build_arg_parser()
    args = arg_parser.parse_args(argv)
    config = load_config(args)

    persist_path = config.persist_path if config.persist_csv else None
    databus = DataBus(maxlen=config.max_points, persist_path=persist_path)

    parser = Parser()
    parser.on_record(databus.append)

    threads: list[FileTail | SerialReader] = []
    if config.sample_file and config.sample_file.exists():
        tail = FileTail(config.sample_file, parser.feed_line, loop=True)
        tail.start()
        threads.append(tail)
    elif config.serial.enabled and config.serial.port:
        try:
            reader = SerialReader(
                config.serial.port,
                config.serial.baudrate,
                config.serial.newline,
                parser.feed_line,
            )
        except Exception as exc:  # pragma: no cover - hardware spezifisch
            print(f"Serielle Verbindung fehlgeschlagen: {exc}", file=sys.stderr)
        else:
            reader.start()
            threads.append(reader)
    else:
        print("Keine Datenquelle konfiguriert. Verwende --sample oder --port.")

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(databus, config)
    window.show()
    exit_code = app.exec()

    for thread in threads:
        thread.stop()
        thread.join(timeout=1.0)
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
