"""Tests für den DataBus."""
from __future__ import annotations

from wtc3_logger.databus import DataBus


def test_databus_reset_clears_records_and_increments_generation() -> None:
    bus = DataBus()
    bus.append({"P04": "CC_CV"}, {"P06": 1})

    snapshot_before = bus.snapshot()
    generation_before = bus.generation()

    assert snapshot_before

    bus.reset()

    assert bus.snapshot() == []
    assert bus.generation() == generation_before + 1
