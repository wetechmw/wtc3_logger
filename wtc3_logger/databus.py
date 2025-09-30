"""Einfache Datenablage und Distribution."""
from __future__ import annotations

import csv
import datetime as dt
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Callable, Deque, Dict, List, Optional

from .parser import Number, PARAMETERS


class DataBus:
    """Thread-sichere Sammlung von Datensätzen."""

    def __init__(self, maxlen: int = 10_000, persist_path: Optional[Path] = None) -> None:
        self._maxlen = maxlen
        self._records: Deque[Dict[str, Number | str]] = deque(maxlen=maxlen)
        self._meta: Dict[str, str] = {}
        self._listeners: List[Callable[[Dict[str, str], Dict[str, Number | str]], None]] = []
        self._lock = Lock()
        self._persist_path = persist_path
        if persist_path:
            persist_path.parent.mkdir(parents=True, exist_ok=True)
            if not persist_path.exists():
                self._write_csv_header(persist_path)

    def _write_csv_header(self, path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["timestamp"] + list(PARAMETERS.keys()))

    def append(self, meta: Dict[str, str], record: Dict[str, Number | str]) -> None:
        with self._lock:
            self._meta = dict(meta)
            self._records.append(dict(record))
        for listener in list(self._listeners):
            listener(meta, record)
        if self._persist_path:
            self._append_csv(record)

    def _append_csv(self, record: Dict[str, Number | str]) -> None:
        assert self._persist_path is not None
        with self._persist_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            row = [dt.datetime.utcnow().isoformat(timespec="seconds")]
            for key in PARAMETERS.keys():
                row.append(record.get(key, ""))
            writer.writerow(row)

    def snapshot(self) -> List[Dict[str, Number | str]]:
        with self._lock:
            return list(self._records)

    def meta(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._meta)

    def subscribe(self, fn: Callable[[Dict[str, str], Dict[str, Number | str]], None]) -> None:
        self._listeners.append(fn)

    def unsubscribe(self, fn: Callable[[Dict[str, str], Dict[str, Number | str]], None]) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)


__all__ = ["DataBus"]

