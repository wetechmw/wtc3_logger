"""Hilfsfunktionen zur Auswertung von Status- und Strategiecodes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .parser import Number


@dataclass(slots=True)
class StatusDetail:
    """Beschreibt die einzelnen Felder des Statuswortes."""

    raw_value: int | None
    badges: List[str]
    details: List[str]


BATTERY_VOLTAGE = {
    0: "Tiefentladen",
    1: "Niedrig",
    2: "Normal",
    3: "Voll",
    4: "Überspannung",
    5: "Ladeende",
}
BATTERY_TEMPERATURE = {
    0: "Kalt",
    1: "Kühl",
    2: "Normal",
    3: "Warm",
    4: "Heiß",
}
BATTERY_RESISTANCE = {
    0: "Niedrig",
    1: "Normal",
    2: "Hoch",
    3: "Nicht verwendet",
}
CHARGER_SUPPLY = {
    0: "Tief",
    1: "Niedrig",
    2: "Normal",
    3: "Hoch",
}
CHARGER_CURRENT = {
    0: "Aus",
    1: "10%",
    2: "20%",
    3: "50%",
    4: "100%",
    7: "Nicht verwendet",
}
FAULT_CODES = {
    0: "Keine Fehler",
    1: "Geringe Kapazität",
    2: "Hohe Kapazität",
    3: "Temperaturdurchgang",
    4: "Hoher Widerstand",
}
PERIPHERAL_BITS = {
    14: "Eingang aktiviert",
    15: "Ausgang aktiviert",
    16: "Regler aktiv",
    17: "Referenz aktiv",
    18: "Sleep aktiv",
}
NICKEL_EOC_BITS = {
    22: "ΔV Drop erreicht",
    23: "ΔT Anstieg",
    24: "Max. Spannungsabfall",
    25: "Hohe Temperatur",
}


def decode_status(value: Number | str | None, bit_labels: Dict[int, str] | None = None) -> StatusDetail:
    """Dekodiere das Statuswort in strukturierte Informationen."""

    try:
        raw_value = int(value) if value is not None else None
    except (TypeError, ValueError):
        raw_value = None

    if raw_value is None:
        return StatusDetail(None, [], [])

    badges: List[str] = []
    details: List[str] = []

    def field(offset: int, size: int) -> int:
        mask = (1 << size) - 1
        return (raw_value >> offset) & mask

    def add_enum(label: str, mapping: Dict[int, str], code: int, include_badge: bool = True) -> None:
        text = mapping.get(code)
        if text is None:
            text = f"Unbekannt ({code})"
        entry = f"{label}: {text}"
        details.append(entry)
        if include_badge:
            badges.append(entry)

    add_enum("Batteriespannung", BATTERY_VOLTAGE, field(0, 3))
    add_enum("Batterietemperatur", BATTERY_TEMPERATURE, field(3, 3))
    add_enum("Innenwiderstand", BATTERY_RESISTANCE, field(6, 2), include_badge=False)
    add_enum("Versorgung", CHARGER_SUPPLY, field(8, 2))
    add_enum("Ladestrom", CHARGER_CURRENT, field(11, 3))

    fault_code = field(19, 3)
    fault_text = FAULT_CODES.get(fault_code, f"Unbekannt ({fault_code})")
    fault_entry = f"Fehler: {fault_text}"
    details.append(fault_entry)
    badges.append(fault_entry)

    handled_bits = set(range(0, 3)) | set(range(3, 6)) | set(range(6, 8)) | set(range(8, 10)) | set(range(11, 14))
    handled_bits |= set(range(19, 22)) | set(PERIPHERAL_BITS) | set(NICKEL_EOC_BITS)

    for bit, text in PERIPHERAL_BITS.items():
        if raw_value & (1 << bit):
            details.append(f"Peripherie: {text}")

    for bit, text in NICKEL_EOC_BITS.items():
        if raw_value & (1 << bit):
            details.append(f"NiCd EoC: {text}")

    if bit_labels:
        for bit, label in sorted(bit_labels.items()):
            if bit in handled_bits:
                continue
            if raw_value & (1 << bit):
                details.append(label)

    return StatusDetail(raw_value, badges, details)


def label_strategy(code: str | None, labels: Dict[str, str]) -> str | None:
    """Ermittle eine verbale Bezeichnung für eine Ladestrategie."""

    if not code:
        return None
    if not labels:
        return None
    return labels.get(str(code))


__all__ = ["StatusDetail", "decode_status", "label_strategy"]