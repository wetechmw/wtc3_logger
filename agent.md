# Agent.md — Serielle Messdaten visualisieren

## 1) Ziel & Scope

Ein kleines, leicht zu deployendes Programm, das zyklisch Messdaten über eine **konfigurierbare serielle Schnittstelle** empfängt, robust parst, optional persistiert und in einem **interaktiven UI** grafisch darstellt (Live-Trend, Tabellen, Filter).
Es wird **keine** aktive Steuerung des Messgeräts benötigt – nur Lesen/Visualisieren.

---

## 2) Datenformat & Beispiel

### 2.1 Beispielstrom (gekürzt)

```
P04     P07     P08     P70     P71     P72     P73     P74     P75     P76     P77     P78     P79     P80     P81     P90     P91     P92
CC_CV   WTC3206 WCM3B-64 REV5   pmnn4889A       LI      8400    0       100     350     450     3100    850     3800    10000   0       4750    9000    36000

P05     P06     P40     P41     P42     P43     P44     P45     P46     P50     P52     P53     P54     P55     P56     P57     P60     P61     P62
31248   1       13030   3299    5681    5752    8400    6990    6990    48      21      49      50      21      0       827     209     201     198
31249   2       13033   3301    6941    7036    8400    7000    7000    52      21      49      400     21      0       827     209     200     198
...
31249   12      12903   3301    7131    8649    8400    7060    7060    266     400     376     400     400     396     1319    214     197     198
```

### 2.2 Protokoll-Annahmen

* Zeilen sind tab/whitespace-getrennt → **Whitespace-Split**.
* **Block A (Meta)**: Headerzeile (nicht-numerische Tokens) + **genau eine** Wertezeile (Strings erlaubt).
* **Block B (Telemetrie)**: neuer Header + **n..m** Wertezeilen (vorwiegend numerisch).
* Keine feste Zeitspalte: Standard-X ist `P06` (Sekunden). Alternativ `P05` (Frame/Zähler) oder Empfangszeit.

---

## 3) Vollständige Parameterliste (vom Gerät)

```
P00  Seriennummer                        uint32_t
P01  Softwareversion                     uint32_t
P02  Herstellungsdatum                   uint32_t
P03  Kalibrierdatum                      uint32_t
P04  Ladestrategie                       char*
P05  Status                              uint32_t
P06  Laufzeit in Sekunden                uint32_t
P07  Name der Halterung                  char*
P08  Name des Lademoduls                 char*
P10  ADC Faktor                          float
P11  ADC Offset                          float
P12  Eingangsspannung Faktor             float
P13  Eingangsspannung Offset             float
P14  Controllerspannung Faktor           float
P15  Controllerspannung Offset           float
P16  Ausgangsspannung Faktor             float
P17  Ausgangsspannung Offset             float
P18  Batteriespannung Faktor             float
P19  Batteriespannung Offset             float
P20  ADC Referenz 5.0                    float
P21  ADC Referenz 2.56                   float
P22  Eingangsstrom Faktor                float
P23  Eingangsstrom Offset                float
P24  Controllerstrom Faktor              float
P25  Controllerstrom Offset              float
P26  Ausgangsstrom Faktor                float
P27  Ausgangsstrom Offset                float
P28  Batteriestrom Faktor                float
P29  Batteriestrom Offset                float
P30  NTC ADC 0° C                        float
P31  NTC ADC 10 C                        float
P32  NTC ADC 35° C                       float
P33  NTC ADC 45° C                       float
P40  Eingangsspannung            mV      uint16_t
P41  Controllerspannung          mV      uint16_t
P42  Ausgangsspannung            mV      uint16_t
P43  Stellspannung               mV      uint16_t
P44  Sollspannung                mV      uint16_t
P45  Batteriespannung            mV      uint16_t
P46  Fuelgauge Batteriespannung  mV      uint16_t
P50  Eingangsstrom               mA      uint16_t
P51  Controllerstrom             mA      uint16_t
P52  Ausgangsstrom               mA      uint16_t
P53  Stellstrom                  mA      uint16_t
P54  Sollstrom                   mA      uint16_t
P55  Batteriestrom               mA      uint16_t
P56  Fuelgauge Ladestrom         mA      uint16_t
P57  Stellstrom                  DAC     uint16_t
P60  Systemtemperatur            °C/10   int16_t
P61  Batterietemperatur          °C/10   int16_t
P62  Fuelgauge Temperatur        °C/10   int16_t
P70  Name                                 char*
P71  Chemie                               char*
P72  Schlussspannung             mV      uint16_t
P73  Kalte Temperatur            °C/10   int16_t
P74  Kühle Temperatur            °C/10   int16_t
P75  Warme Temperatur            °C/10   int16_t
P76  Heiße Temperatur            °C/10   int16_t
P77  Typ. Kapazität              mAh     uint16_t
P78  Max. Ladestrom              mA      uint16_t
P79  Thermistor Beta                     uint16_t
P80  Thermistor Widerstand       R       uint16_t
P81  Batterie Spannungsfeedback R        uint16_t
P90  Eingangsspannung Minimum    mV      uint16_t
P91  Eingangsspannung Reduziert  mV      uint16_t
P92  Eingangsspannung Maximum    mV      uint16_t
```

---

## 4) Architektur

```
┌──────────────────┐   Bytes   ┌─────────────────┐   Records   ┌──────────────────┐   Series   ┌──────────────────┐
│ Serial Reader    ├──────────▶│ Line Assembler  ├────────────▶│ Parser (Blocks)  ├──────────▶│ Data Bus (RxJS)  │
└──────────────────┘           └─────────────────┘             └──────────────────┘            └───────┬──────────┘
                                                                                                        │
                                                                                     ┌──────────────────▼─────────────────┐
                                                                                     │ UI (Charts, Table, KPIs)           │
                                                                                     └──────────────────┬─────────────────┘
                                                                                                        │
                                                                                     ┌──────────────────▼─────────────────┐
                                                                                     │ Sink: CSV/SQLite/WS/HTTP           │
                                                                                     └────────────────────────────────────┘
```

**Technologien (Vorschlag):**

* **Backend**: Python 3.11+, `pyserial`, `pydantic`, optional `fastapi`/WebSocket, `sqlite3`/`pandas`.
* **UI (klein & schnell)**: `PyQt6` + `pyqtgraph`. (Alternative Web-UI: FastAPI + React + recharts.)
* **Packaging**: `pipx`/`uv`; optional `PyInstaller` für Ein-Datei-App.

---

## 5) Konfiguration

### 5.1 `config.yaml`

> Skalenregeln: mV→V = 0.001, mA→A = 0.001, °C/10→°C = 0.1

```yaml
serial:
  port: "/dev/ttyUSB0"   # oder "COM4"
  baudrate: 115200
  bytesize: 8
  parity: "N"            # N/E/O
  stopbits: 1
  rtscts: false
  xonxoff: false
  timeout_s: 0.2
  line_terminator: "\n"  # oder "\r\n"

parser:
  header_lines_expect_min: 1
  allow_mixed_types: true
  second_block_required: true
  decimal: "."
  strict_column_count: false

mapping:
  # ---- Meta (Stammdaten & Kalibrierwerte)
  P00: {label: "Seriennummer",                unit: "",   scale: 1.0,  type: "uint32", group: "meta"}
  P01: {label: "Softwareversion",             unit: "",   scale: 1.0,  type: "uint32", group: "meta"}
  P02: {label: "Herstellungsdatum",           unit: "",   scale: 1.0,  type: "uint32", group: "meta"}
  P03: {label: "Kalibrierdatum",              unit: "",   scale: 1.0,  type: "uint32", group: "meta"}
  P04: {label: "Ladestrategie",               unit: "",   scale: 1.0,  type: "string", group: "meta"}
  P07: {label: "Halterung (Name)",            unit: "",   scale: 1.0,  type: "string", group: "meta"}
  P08: {label: "Lademodul (Name)",            unit: "",   scale: 1.0,  type: "string", group: "meta"}
  P10: {label: "ADC Faktor",                  unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P11: {label: "ADC Offset",                  unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P12: {label: "Eingangsspannung Faktor",     unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P13: {label: "Eingangsspannung Offset",     unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P14: {label: "Controllerspannung Faktor",   unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P15: {label: "Controllerspannung Offset",   unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P16: {label: "Ausgangsspannung Faktor",     unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P17: {label: "Ausgangsspannung Offset",     unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P18: {label: "Batteriespannung Faktor",     unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P19: {label: "Batteriespannung Offset",     unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P20: {label: "ADC Referenz 5.0",            unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P21: {label: "ADC Referenz 2.56",           unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P22: {label: "Eingangsstrom Faktor",        unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P23: {label: "Eingangsstrom Offset",        unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P24: {label: "Controllerstrom Faktor",      unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P25: {label: "Controllerstrom Offset",      unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P26: {label: "Ausgangsstrom Faktor",        unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P27: {label: "Ausgangsstrom Offset",        unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P28: {label: "Batteriestrom Faktor",        unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P29: {label: "Batteriestrom Offset",        unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P30: {label: "NTC ADC 0°C",                 unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P31: {label: "NTC ADC 10°C",                unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P32: {label: "NTC ADC 35°C",                unit: "",   scale: 1.0,  type: "float",  group: "meta"}
  P33: {label: "NTC ADC 45°C",                unit: "",   scale: 1.0,  type: "float",  group: "meta"}

  # ---- Telemetrie (Live)
  P05: {label: "Status",                      unit: "",   scale: 1.0,   type: "uint32", group: "telemetry"} # optional Enum/Bitfeld
  P06: {label: "Laufzeit",                    unit: "s",  scale: 1.0,   type: "uint32", group: "telemetry", role: "index"}

  P40: {label: "Eingangsspannung",            unit: "V",  scale: 0.001, type: "uint16", group: "telemetry"}
  P41: {label: "Controllerspannung",          unit: "V",  scale: 0.001, type: "uint16", group: "telemetry"}
  P42: {label: "Ausgangsspannung",            unit: "V",  scale: 0.001, type: "uint16", group: "telemetry"}
  P43: {label: "Stellspannung",               unit: "V",  scale: 0.001, type: "uint16", group: "telemetry"}
  P44: {label: "Sollspannung",                unit: "V",  scale: 0.001, type: "uint16", group: "telemetry"}
  P45: {label: "Batteriespannung",            unit: "V",  scale: 0.001, type: "uint16", group: "telemetry"}
  P46: {label: "Fuelgauge Batteriespannung",  unit: "V",  scale: 0.001, type: "uint16", group: "telemetry"}

  P50: {label: "Eingangsstrom",               unit: "A",  scale: 0.001, type: "uint16", group: "telemetry"}
  P51: {label: "Controllerstrom",             unit: "A",  scale: 0.001, type: "uint16", group: "telemetry"}
  P52: {label: "Ausgangsstrom",               unit: "A",  scale: 0.001, type: "uint16", group: "telemetry"}
  P53: {label: "Stellstrom",                  unit: "A",  scale: 0.001, type: "uint16", group: "telemetry"}
  P54: {label: "Sollstrom",                   unit: "A",  scale: 0.001, type: "uint16", group: "telemetry"}
  P55: {label: "Batteriestrom",               unit: "A",  scale: 0.001, type: "uint16", group: "telemetry"}
  P56: {label: "Fuelgauge Ladestrom",         unit: "A",  scale: 0.001, type: "uint16", group: "telemetry"}
  P57: {label: "Stellstrom (DAC)",            unit: "DAC",scale: 1.0,   type: "uint16", group: "telemetry"}

  P60: {label: "Systemtemperatur",            unit: "°C", scale: 0.1,   type: "int16",  group: "telemetry"}
  P61: {label: "Batterietemperatur",          unit: "°C", scale: 0.1,   type: "int16",  group: "telemetry"}
  P62: {label: "Fuelgauge Temperatur",        unit: "°C", scale: 0.1,   type: "int16",  group: "telemetry"}

  # ---- Akku-spezifisch (Meta)
  P70: {label: "Akkubezeichnung",             unit: "",   scale: 1.0,   type: "string", group: "meta"}
  P71: {label: "Chemie",                      unit: "",   scale: 1.0,   type: "string", group: "meta"}
  P72: {label: "Schlussspannung",             unit: "V",  scale: 0.001, type: "uint16", group: "meta"}
  P73: {label: "Kalte Temperatur",            unit: "°C", scale: 0.1,   type: "int16",  group: "meta"}
  P74: {label: "Kühle Temperatur",            unit: "°C", scale: 0.1,   type: "int16",  group: "meta"}
  P75: {label: "Warme Temperatur",            unit: "°C", scale: 0.1,   type: "int16",  group: "meta"}
  P76: {label: "Heiße Temperatur",            unit: "°C", scale: 0.1,   type: "int16",  group: "meta"}
  P77: {label: "Typ. Kapazität",              unit: "mAh",scale: 1.0,   type: "uint16", group: "meta"}
  P78: {label: "Max. Ladestrom",              unit: "A",  scale: 0.001, type: "uint16", group: "meta"}
  P79: {label: "Thermistor Beta",             unit: "",   scale: 1.0,   type: "uint16", group: "meta"}
  P80: {label: "Thermistor Widerstand",       unit: "Ω",  scale: 1.0,   type: "uint16", group: "meta"}
  P81: {label: "Batt. Spannungsfeedback R",   unit: "Ω",  scale: 1.0,   type: "uint16", group: "meta"}

  P90: {label: "Vin Minimum",                 unit: "V",  scale: 0.001, type: "uint16", group: "meta"}
  P91: {label: "Vin Reduziert",               unit: "V",  scale: 0.001, type: "uint16", group: "meta"}
  P92: {label: "Vin Maximum",                 unit: "V",  scale: 0.001, type: "uint16", group: "meta"}

ui:
  charts:
    - title: "Spannungen"
      series: ["P40","P41","P42","P45"]
      window_points: 2000
    - title: "Ströme"
      series: ["P50","P52","P54","P55","P56"]
      window_points: 2000
    - title: "Temperaturen"
      series: ["P60","P61","P62"]
      window_points: 2000
  kpis: ["P42","P55","P61"]

persist:
  enabled: true
  kind: "sqlite"      # "csv" | "sqlite" | "none"
  path: "./data/measurements.db"
```

### 5.2 CLI-Beispiele

```
mesviz --config config.yaml
mesviz --port /dev/ttyUSB0 --baud 230400 --headless --csv out.csv
```

---

## 6) Parsing-Regeln

1. **Zeilen normalisieren**: `strip()`, Split auf beliebiges Whitespace (`\s+`).
2. **Headererkennung**: Zeile ist Header, wenn **>50 %** Tokens nicht-numerisch sind oder `^P\d+|[A-Z_]+$` matchen.
3. **Block A (Meta)**: Header + **eine** Wertezeile → Key-Value-Map (Strings erlaubt).
4. **Block B (Telemetrie)**: Header + **n..m** Wertezeilen → Records.
5. **Typen & Skalierung**: gemäß `mapping.type` casten; `mapping.scale` anwenden
   (mV→V 0.001, mA→A 0.001, °C/10→°C 0.1).
6. **Zeitachse**: `role: "index"` → `P06` (Sekunden). Fallback: Empfangszeit.
7. **Fehlende Werte**: `""` → `NaN` (float), Log-Warnung.
8. **Status (P05)** *(optional)*: Wenn Bitfelder/Enums vorliegen, im UI als Badges (z. B. „CC“, „CV“, „ERR“) anzeigen.
9. **Datum (P02/P03)**: Falls `YYYYMMDD`, in `YYYY-MM-DD` formatiert darstellen.

---

## 7) Visualisierung (UI)

* **Live-Charts**: Mehrfachserien mit gemeinsamer X-Achse (Standard `P06`).
* **KPI-Kacheln**: aktueller Wert, Min/Max, gleitender Mittelwert (Fenster konfigurierbar).
* **Tabelle**: letzte N Zeilen, Spaltenfilter, CSV-Export.
* **Metadaten-Panel**: zeigt `P00, P01, P02, P03, P04, P70..P72, P77..P81, P90..P92`.
* **Grenzwerte/Highlights**: vergleiche `P40` mit `P90..P92`; farbliche Markierung außerhalb Grenzen.

---

## 8) Fehlerbehandlung & Robustheit

* **Seriell**: Auto-Reconnect (Exponential Backoff), Port-Busy/Timeout-Handling.
* **Parser**: toleriert leere Zeilen/uneinheitliche Spaltenbreite; unerwartete Spalten → Warnung + dynamische Aufnahme.
* **Backpressure**: Ringbuffer (z. B. 50 k Punkte) für Charts; Persistenz asynchron.
* **Encoding**: Standard `utf-8`, Fallback `latin-1`.

---

## 9) Tests & Validierung

* **Unit-Tests**: Header-/Block-Erkennung, Typ-/Skalenmapping, Edge Cases (NaN, leere Tokens).
* **Golden Sample**: das bereitgestellte Datenbeispiel als Regressionstest.
* **Load-Test**: ≥1 k Zeilen/s; Chart-FPS ≥30.

---

## 10) (Optional) API

* **GET** `/meta` → Map aus Block A.
* **GET** `/latest?cols=P40,P41` → letzte Telemetriezeile (skaliert).
* **WS** `/stream` → JSONL-Records in Echtzeit.

**Beispiel-Record**

```json
{
  "ts":"2025-09-30T12:34:56.789Z",
  "meta":{"P04":"CC_CV","P07":"WTC3206","P08":"WCM3B-64","P70":"REV5","P71":"pmnn4889A","P72":8.4},
  "data":{"P06":3,"P40":13.012,"P41":3.301,"P42":7.028,"P50":0.086,"P52":0.049,"P60":20.9}
}
```

---

## 11) Deployment

* **Dev**: `pip install -r requirements.txt`; `python -m mesviz --config config.yaml`
* **Desktop-Bundle**: `pyinstaller --onefile app.py`
* **Service** (Linux): systemd-Unit mit `Restart=always`; Logrotate für CSV.

---

## 12) Sicherheit

* Serielle Ports nur für vertrauenswürdige Nutzer/Gruppen (uucp/dialout).
* Web-UI (falls aktiv): restriktives CORS, read-only Endpunkte, optional Basic-Auth.
* Keine Rohdatenmanipulation, nur Visualisierung/Export.

---

## 13) Akzeptanzkriterien (DoD)

* App liest reale Daten über konfigurierbaren Port.
* Block-A-Metadaten erscheinen im UI.
* Mind. **3 auswählbare Serien** (z. B. `P40`, `P41`, `P50`) werden live geplottet.
* CSV-Export der letzten N Zeilen funktioniert.
* Parser übersteht Störungen (leere Zeilen, unerwartete Spalten) ohne Absturz.
* Headless-Modus schreibt kontinuierlich in CSV/SQLite.

---

## 14) Abgeleitete Signale (optional)

* **Pin/Pout**: `Pin = P40[V] * P50[A]`, `Pout = P42[V] * P52[A]`.
* **Wirkungsgrad**: `eta = Pout / Pin` (Clamping 0..1).
* **ΔT**: `P61 - P60`.

---

## 15) Minimaler Code-Skeleton (Python, PyQt + pyqtgraph)

> Hinweis: Für Produktion in Module aufteilen, Logging/CLI hinzufügen. Dieser Skeleton liest eine Beispieldatei; den Serial-Reader aktivierst du mit der markierten Stelle.

```python
# app.py
import sys, time, threading, re, pathlib
from dataclasses import dataclass
from typing import Callable, Dict, Any
from PyQt6 import QtWidgets
import pyqtgraph as pg

# Optional: pip install pyserial
# import serial

def is_number(tok: str) -> bool:
    try:
        float(tok); return True
    except Exception:
        return False

def split_ws(line: str):
    return re.split(r"\s+", line.strip())

@dataclass
class FieldCfg:
    label: str = ""
    unit: str = ""
    scale: float = 1.0
    type: str = "float"
    role: str | None = None
    group: str | None = None

# ---- Mapping (aus config.yaml zur Illustration inline gespiegelt, gekürzt)
mapping: Dict[str, Dict[str, Any]] = {
    "P06": {"label":"Laufzeit","unit":"s","scale":1.0,"type":"uint32","role":"index","group":"telemetry"},
    "P40": {"label":"Vin","unit":"V","scale":0.001,"type":"uint16","group":"telemetry"},
    "P41": {"label":"Vctrl","unit":"V","scale":0.001,"type":"uint16","group":"telemetry"},
    "P42": {"label":"Vout","unit":"V","scale":0.001,"type":"uint16","group":"telemetry"},
    "P45": {"label":"Vbat","unit":"V","scale":0.001,"type":"uint16","group":"telemetry"},
    "P50": {"label":"Iin","unit":"A","scale":0.001,"type":"uint16","group":"telemetry"},
    "P52": {"label":"Iout","unit":"A","scale":0.001,"type":"uint16","group":"telemetry"},
    "P60": {"label":"Tsys","unit":"°C","scale":0.1,"type":"int16","group":"telemetry"},
    "P61": {"label":"Tbat","unit":"°C","scale":0.1,"type":"int16","group":"telemetry"},
    "P62": {"label":"Tfg","unit":"°C","scale":0.1,"type":"int16","group":"telemetry"},
}

def cast_and_scale(name: str, raw):
    cfg = mapping.get(name, {})
    ty = cfg.get("type")
    scale = cfg.get("scale", 1.0)
    v = raw
    if ty in ("uint16","uint32","int16"):
        v = int(float(raw))
    elif ty == "float":
        v = float(raw)
    else:
        # string/unknown
        return raw
    return v * scale

class Parser:
    def __init__(self):
        self.meta_hdr = []
        self.meta = {}
        self.data_hdr = []
        self.phase = "find_header"
        self.listeners: list[Callable[[dict, dict], None]] = []

    def on_record(self, fn: Callable[[dict, dict], None]):
        self.listeners.append(fn)

    def feed_line(self, line: str):
        if not line.strip():
            return
        toks = split_ws(line)
        nonnum = sum(1 for t in toks if not is_number(t))
        # Header?
        if nonnum >= max(1, len(toks)//2):
            # Header wechselt
            if not self.meta_hdr:
                self.meta_hdr = toks
                self.phase = "expect_meta_values"
            else:
                self.data_hdr = toks
                self.phase = "expect_data_values"
            return
        # Wertezeile
        if self.phase == "expect_meta_values":
            self.meta = dict(zip(self.meta_hdr, toks))
            return
        if self.phase in ("expect_data_values","data"):
            self.phase = "data"
            rec = {}
            for k, raw in zip(self.data_hdr, toks):
                if is_number(raw) and k in mapping:
                    rec[k] = cast_and_scale(k, raw)
                else:
                    rec[k] = float(raw) if is_number(raw) else raw
            for cb in self.listeners:
                cb(self.meta, rec)

class LivePlot(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MesViz")
        self.plot = pg.PlotWidget()
        self.setCentralWidget(self.plot)
        self.curves: Dict[str, Any] = {}
        self.x: list[float] = []
        self.y: Dict[str, list[float]] = {}
        self.t0 = time.time()
        self.series = ["P40","P41","P42","P50","P52","P60","P61"]  # Default-Serien

    def add_point(self, meta: dict, rec: dict):
        # X
        x = rec.get("P06", None)
        if x is None:
            x = time.time()-self.t0
        self.x.append(x)
        # Y-Serien
        for key in self.series:
            v = rec.get(key)
            if v is None: 
                continue
            self.y.setdefault(key, []).append(v)
            if key not in self.curves:
                self.curves[key] = self.plot.plot(name=key)
        for k, curve in self.curves.items():
            curve.setData(self.x, self.y.get(k, []))

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = LivePlot()
    win.resize(1100, 650)
    win.show()

    parser = Parser()
    parser.on_record(lambda meta, rec: win.add_point(meta, rec))

    # ---- Echtbetrieb: Serial aktivieren
    # sr = SerialReader("/dev/ttyUSB0", 115200, parser.feed_line); sr.start()

    # ---- Dev: Beispieldatei streamen
    sample = pathlib.Path("sample.txt")
    if sample.exists():
        for ln in sample.read_text(encoding="utf-8").splitlines():
            parser.feed_line(ln)

    sys.exit(app.exec())

# class SerialReader(threading.Thread):
#     def __init__(self, port, baud, callback):
#         super().__init__(daemon=True); self.callback = callback
#         self.sp = serial.Serial(port, baudrate=baud, timeout=0.2)
#     def run(self):
#         buf = b""
#         while True:
#             b = self.sp.read(1024)
#             if not b: continue
#             buf += b
#             while b"\n" in buf:
#                 line, buf = buf.split(b"\n", 1)
#                 self.callback(line.decode(errors="ignore"))

if __name__ == "__main__":
    main()
```

---

## 16) To-Dos / Erweiterungen

* **Status-Bits (P05)** und **Ladestrategie-Enum (P04)** konkretisieren → Decoder & UI-Badges.
* **Export**: Chart-Screenshot (PNG), vollständiger CSV-Dump.
* **API**: REST/WS aktivieren, falls mehrere Clients mitlesen sollen.
* **Alarme**: Schwellwerte je Spalte aus Mapping; Marker im Chart.
* **Mehrsprachigkeit**: DE/EN Umschaltbar.

---
