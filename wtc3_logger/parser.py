"""Parser für das WTC3-Protokoll."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List

Number = float | int


def split_ws(line: str) -> List[str]:
    return [tok for tok in line.strip().split() if tok]


@dataclass(frozen=True, slots=True)
class ParameterInfo:
    key: str
    description: str
    unit: str | None
    scale: float | None = None

    def cast(self, raw: str) -> Number | str:
        if raw == "":
            return raw
        try:
            if "." in raw or "e" in raw.lower():
                value: Number = float(raw)
            else:
                value = int(raw)
        except ValueError:
            return raw
        if self.scale is not None:
            return value * self.scale
        return value


PARAMETERS: Dict[str, ParameterInfo] = {
    "P04": ParameterInfo("P04", "Ladestrategie", None),
    "P05": ParameterInfo("P05", "Status", None),
    "P06": ParameterInfo("P06", "Laufzeit", "s"),
    "P07": ParameterInfo("P07", "Halterung", None),
    "P08": ParameterInfo("P08", "Lademodul", None),
    "P40": ParameterInfo("P40", "Eingangsspannung", "V", 0.001),
    "P41": ParameterInfo("P41", "Controllerspannung", "V", 0.001),
    "P42": ParameterInfo("P42", "Ausgangsspannung", "V", 0.001),
    "P43": ParameterInfo("P43", "Stellspannung", "V", 0.001),
    "P44": ParameterInfo("P44", "Sollspannung", "V", 0.001),
    "P45": ParameterInfo("P45", "Batteriespannung", "V", 0.001),
    "P46": ParameterInfo("P46", "Fuelgauge Batteriespannung", "V", 0.001),
    "P50": ParameterInfo("P50", "Eingangsstrom", "A", 0.001),
    "P51": ParameterInfo("P51", "Controllerstrom", "A", 0.001),
    "P52": ParameterInfo("P52", "Ausgangsstrom", "A", 0.001),
    "P53": ParameterInfo("P53", "Stellstrom", "A", 0.001),
    "P54": ParameterInfo("P54", "Sollstrom", "A", 0.001),
    "P55": ParameterInfo("P55", "Batteriestrom", "A", 0.001),
    "P56": ParameterInfo("P56", "Fuelgauge Ladestrom", "A", 0.001),
    "P57": ParameterInfo("P57", "Stellstrom DAC", "count"),
    "P60": ParameterInfo("P60", "Systemtemperatur", "°C", 0.1),
    "P61": ParameterInfo("P61", "Batterietemperatur", "°C", 0.1),
    "P62": ParameterInfo("P62", "Fuelgauge Temperatur", "°C", 0.1),
    "P70": ParameterInfo("P70", "Batteriename", None),
    "P71": ParameterInfo("P71", "Chemie", None),
    "P72": ParameterInfo("P72", "Schlussspannung", "V", 0.001),
    "P73": ParameterInfo("P73", "Kalte Temperatur", "°C", 0.1),
    "P74": ParameterInfo("P74", "Kühle Temperatur", "°C", 0.1),
    "P75": ParameterInfo("P75", "Warme Temperatur", "°C", 0.1),
    "P76": ParameterInfo("P76", "Heiße Temperatur", "°C", 0.1),
    "P77": ParameterInfo("P77", "Typ. Kapazität", "mAh"),
    "P78": ParameterInfo("P78", "Max. Ladestrom", "A", 0.001),
    "P79": ParameterInfo("P79", "Thermistor Beta", None),
    "P80": ParameterInfo("P80", "Thermistor Widerstand", "Ω"),
    "P81": ParameterInfo("P81", "Batterie Spannungsfeedback", "Ω"),
    "P90": ParameterInfo("P90", "Eingangsspannung Min", "V", 0.001),
    "P91": ParameterInfo("P91", "Eingangsspannung Reduziert", "V", 0.001),
    "P92": ParameterInfo("P92", "Eingangsspannung Max", "V", 0.001),
}


class Parser:
    """Stream-orientierter Parser für die tab-separierten Telemetriedaten."""

    def __init__(self) -> None:
        self.meta_hdr: List[str] = []
        self.meta: Dict[str, str] = {}
        self.data_hdr: List[str] = []
        self.phase: str = "find_header"
        self.listeners: List[Callable[[Dict[str, str], Dict[str, Number | str]], None]] = []

    def on_record(self, fn: Callable[[Dict[str, str], Dict[str, Number | str]], None]) -> None:
        self.listeners.append(fn)

    def reset(self) -> None:
        self.meta_hdr = []
        self.meta = {}
        self.data_hdr = []
        self.phase = "find_header"

    def feed(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.feed_line(line)

    def feed_line(self, line: str) -> None:
        if not line.strip():
            return
        tokens = split_ws(line)
        if self.phase == "expect_meta_values":
            self._handle_values(tokens)
            return
        nonnum = sum(1 for tok in tokens if not self._is_number(tok))
        if nonnum >= max(1, len(tokens) // 2):
            self._handle_header(tokens)
            return
        self._handle_values(tokens)

    def _handle_header(self, tokens: List[str]) -> None:
        if not self.meta_hdr:
            self.meta_hdr = tokens
            self.phase = "expect_meta_values"
        elif not self.data_hdr:
            self.data_hdr = tokens
            self.phase = "expect_data_values"
        else:
            # neuer Block → Reset Daten-Header
            self.data_hdr = tokens
            self.phase = "expect_data_values"

    def _handle_values(self, tokens: List[str]) -> None:
        if self.phase == "expect_meta_values":
            self.meta = dict(zip(self.meta_hdr, tokens))
            self.phase = "find_header"
            return
        if self.phase in {"expect_data_values", "data"}:
            self.phase = "data"
            record: Dict[str, Number | str] = {}
            for key, raw in zip(self.data_hdr, tokens):
                info = PARAMETERS.get(key)
                if info:
                    record[key] = info.cast(raw)
                else:
                    record[key] = self._cast_default(raw)
            for cb in self.listeners:
                cb(self.meta, record)

    @staticmethod
    def _is_number(token: str) -> bool:
        if not token:
            return False
        try:
            float(token)
            return True
        except ValueError:
            return False

    @staticmethod
    def _cast_default(raw: str) -> Number | str:
        try:
            if "." in raw or "e" in raw.lower():
                return float(raw)
            return int(raw)
        except ValueError:
            return raw


__all__ = ["Parser", "ParameterInfo", "PARAMETERS"]
