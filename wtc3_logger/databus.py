"""Simple in-memory data distribution."""
from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Callable, Deque, Dict, List

from .parser import Number


class DataBus:
    """Thread-safe collection of telemetry records."""

    def __init__(self, maxlen: int = 10_000) -> None:
        self._maxlen = maxlen
        self._records: Deque[Dict[str, Number | str]] = deque(maxlen=maxlen)
        self._meta: Dict[str, str] = {}
        self._listeners: List[Callable[[Dict[str, str], Dict[str, Number | str]], None]] = []
        self._lock = Lock()
        self._generation = 0

    def append(self, meta: Dict[str, str], record: Dict[str, Number | str]) -> None:
        with self._lock:
            self._meta = dict(meta)
            self._records.append(dict(record))
        for listener in list(self._listeners):
            listener(meta, record)

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._generation += 1

    def snapshot(self) -> List[Dict[str, Number | str]]:
        with self._lock:
            return list(self._records)

    def meta(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._meta)

    def generation(self) -> int:
        with self._lock:
            return self._generation

    def subscribe(self, fn: Callable[[Dict[str, str], Dict[str, Number | str]], None]) -> None:
        self._listeners.append(fn)

    def unsubscribe(self, fn: Callable[[Dict[str, str], Dict[str, Number | str]], None]) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)


__all__ = ["DataBus"]
