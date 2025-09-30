"""Pytest Konfiguration."""
from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

try:  # pragma: no cover - optional dependency
    from PySide6 import QtWidgets
except ImportError:  # pragma: no cover - Testumgebungen ohne Qt
    QtWidgets = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def qapp():
    """Stellt eine QApplication für UI-Tests bereit."""

    if QtWidgets is None:  # pragma: no cover - Tests werden übersprungen
        pytest.skip("PySide6 nicht verfügbar")

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app