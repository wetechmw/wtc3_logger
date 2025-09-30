"""Tests für den Parser."""
from __future__ import annotations

from wtc3_logger.parser import Parser, PARAMETERS


SAMPLE = """
P04 P07 P08
CC_CV WTC3206 WCM3B-64
P05 P06 P40 P41
31248 1 13030 3299
31249 2 13033 3301
""".strip().splitlines()


def test_parser_reads_meta_and_records() -> None:
    parsed_meta: dict[str, str] = {}
    records: list[dict[str, float | int | str]] = []

    parser = Parser()
    parser.on_record(lambda meta, record: (parsed_meta.update(meta), records.append(record)))
    parser.feed(SAMPLE)

    assert parsed_meta["P04"] == "CC_CV"
    assert len(records) == 2
    assert records[0]["P06"] == 1
    assert abs(records[0]["P40"] - 13.03) < 1e-6
    assert "P41" in PARAMETERS
