"""Persistent user preference helpers for the WTC3 logger."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

PREFERENCES_DIR = Path.home() / '.wtc3_logger'
PREFERENCES_PATH = PREFERENCES_DIR / 'preferences.json'


def load_preferences() -> Dict[str, Any]:
    """Return persisted preferences, or an empty dict on failure."""

    if not PREFERENCES_PATH.exists():
        return {}
    try:
        return json.loads(PREFERENCES_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_preferences(data: Dict[str, Any]) -> None:
    """Persist preferences to disk."""

    PREFERENCES_DIR.mkdir(parents=True, exist_ok=True)
    PREFERENCES_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding='utf-8')


__all__ = ['load_preferences', 'save_preferences', 'PREFERENCES_PATH']
