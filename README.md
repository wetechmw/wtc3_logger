# WTC3 Logger

Ein leichtgewichtiges Tool zum Visualisieren von Telemetrie-Daten eines WTC3-Ladegeräts.
Es liest zyklisch Werte über eine serielle Schnittstelle oder aus Logdateien, parst das
Whitespace-basierte Protokoll und stellt es in einem freundlichen UI dar.

## Features

- Konfigurierbare serielle Schnittstelle (Port, Baudrate, Trennzeichen)
- Parser für Meta- und Datenblöcke nach Agent-Spezifikation
- Live-Plot mehrerer Kennlinien inklusive Achsenwahl
- Tabellenansicht mit Filter- und Exportfunktionen
- Persistenz als CSV-Protokoll
- Design angelehnt an [wetech.de](https://www.wetech.de)

## Status- und Strategiemapping

Über die Konfiguration lassen sich Statusbits (P05) sowie Ladestrategien (P04) in
sprechende Labels übersetzen. Beispiel für einen YAML-Ausschnitt:

```yaml
status_bits:
  0: "Ladefreigabe aktiv"
  3: "Temperaturalarm"
strategy_labels:
  CC_CV: "Konstantstrom / Konstantspannung"
```

Aktive Bits erscheinen im UI als dunkle Badges, während die Strategie als primäre
Badge oberhalb der Metadaten eingeblendet wird.

## Installation

```bash
pip install -e .[dev]
```

## Entwicklung

- Starten mit Beispieldaten: `python -m wtc3_logger --sample`
- Serielle Verbindung: `python -m wtc3_logger --port /dev/ttyUSB0 --baud 115200`

Tests ausführen:

```bash
pytest
```

