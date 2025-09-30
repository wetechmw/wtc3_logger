"""Serial Reader mit Fallback auf Dateien."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

try:
    import serial
except ImportError:  # pragma: no cover - optional dependency während Tests
    serial = None  # type: ignore


class SerialReader(threading.Thread):
    """Liests Zeilen aus einer seriellen Schnittstelle."""

    def __init__(
        self,
        port: str,
        baudrate: int,
        newline: str,
        callback: Callable[[str], None],
    ) -> None:
        super().__init__(daemon=True)
        self._callback = callback
        self._newline = newline.encode()
        self._running = threading.Event()
        self._running.set()
        self._serial = None
        if serial is None:
            raise RuntimeError("pyserial ist nicht installiert")
        self._serial = serial.Serial(port, baudrate=baudrate, timeout=0.2)

    def run(self) -> None:  # pragma: no cover - benötigt echte Hardware
        assert self._serial is not None
        buffer = b""
        while self._running.is_set():
            chunk = self._serial.read(1024)
            if not chunk:
                continue
            buffer += chunk
            while self._newline in buffer:
                line, buffer = buffer.split(self._newline, 1)
                self._callback(line.decode(errors="ignore"))

    def stop(self) -> None:  # pragma: no cover - benötigt echte Hardware
        self._running.clear()
        if self._serial:
            self._serial.close()


class FileTail(threading.Thread):
    """Simuliert Streaming, indem eine Datei Zeile für Zeile gelesen wird."""

    def __init__(self, path: Path, callback: Callable[[str], None], loop: bool = False, delay: float = 0.05) -> None:
        super().__init__(daemon=True)
        self._path = path
        self._callback = callback
        self._loop = loop
        self._delay = delay
        self._running = threading.Event()
        self._running.set()

    def run(self) -> None:  # pragma: no cover - UI Integration
        while self._running.is_set():
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not self._running.is_set():
                        break
                    self._callback(line.rstrip("\n"))
                    time.sleep(self._delay)
            if not self._loop:
                break

    def stop(self) -> None:  # pragma: no cover
        self._running.clear()


__all__ = ["SerialReader", "FileTail"]
