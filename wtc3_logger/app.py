"""Startpunkt für den Logger."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtWidgets, QtGui

from .acquisition import AcquisitionController
from .config import AppConfig, DEFAULT_CONFIG, SerialConfig
from .databus import DataBus
from .ui import MainWindow



def _resource_path(*parts: str) -> Path:
    base = getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])
    return Path(base, *parts)

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WTC3 Telemetrie Visualisierung")
    parser.add_argument("--config", type=Path, help="Pfad zu YAML-Konfiguration", default=None)
    parser.add_argument("--port", type=str, help="Serieller Port", default=None)
    parser.add_argument("--baud", type=int, help="Baudrate", default=None)
    parser.add_argument("--sample", action="store_true", help="Beispieldatei streamen")
    parser.add_argument("--sample-file", type=Path, help="Alternative Beispieldatei", default=None)
    parser.add_argument("--persist", action="store_true", help="Enable raw data logging")
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

    databus = DataBus(maxlen=config.max_points)
    controller = AcquisitionController(config, databus)

    app = QtWidgets.QApplication(sys.argv)
    icon_path = _resource_path("assets", "Icon.png")
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))
    window = MainWindow(databus, config, controller)
    window.showMaximized()
    controller.start()
    exit_code = app.exec()

    controller.stop()
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
