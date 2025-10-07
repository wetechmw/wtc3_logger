"""Utility helpers to construct export file names."""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Dict


def _sanitize_token(raw: str | None) -> str:
    if not raw:
        return ""
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-_")
    return cleaned


def build_export_stem(started: dt.datetime, meta: Dict[str, str]) -> str:
    """Return a descriptive filename stem based on timestamp, battery and cradle."""

    timestamp = started.strftime("%Y%m%d_%H%M%S")
    battery = _sanitize_token(meta.get("P70"))
    cradle = _sanitize_token(meta.get("P07"))

    parts = [timestamp]
    if battery:
        parts.append(battery)
    if cradle:
        parts.append(cradle)
    if len(parts) == 1:
        parts.append("raw")
    return "_".join(parts)


__all__ = ["build_export_stem"]
