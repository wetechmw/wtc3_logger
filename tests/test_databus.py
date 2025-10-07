"""Tests for the DataBus."""
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


def test_databus_subscribe_unsubscribe() -> None:
    bus = DataBus()
    seen: list[int] = []

    def listener(_meta: dict[str, str], record: dict[str, int | str]) -> None:
        value = record.get("P06")
        if isinstance(value, int):
            seen.append(value)

    bus.subscribe(listener)
    bus.append({"P04": "CC"}, {"P06": 1})
    assert seen == [1]

    bus.unsubscribe(listener)
    bus.append({"P04": "CC"}, {"P06": 2})
    assert seen == [1]
