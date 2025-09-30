"""Hilfsfunktionen zur Auswertung von Status- und Strategiecodes."""
from __future__ import annotations

from typing import Dict, List

from .parser import Number


def decode_status(value: Number | str | None, bit_labels: Dict[int, str]) -> List[str]:
    """Dekodiere ein Statuswort in menschlich lesbare Labels.

    Wird kein Mapping angegeben oder das Statuswort ist nicht numerisch, wird eine
    leere Liste zurückgegeben. Bits werden als *aktiv* interpretiert, wenn sie im
    Integer-Wert gesetzt sind (``value & (1 << bit)``).
    """

    if not bit_labels:
        return []
    try:
        int_value = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return []
    active: List[str] = []
    for bit, label in sorted(bit_labels.items()):
        if int_value & (1 << bit):
            active.append(label)
    return active


def label_strategy(code: str | None, labels: Dict[str, str]) -> str | None:
    """Ermittle eine verbale Bezeichnung für eine Ladestrategie."""

    if not code:
        return None
    if not labels:
        return None
    return labels.get(str(code))


__all__ = ["decode_status", "label_strategy"]
