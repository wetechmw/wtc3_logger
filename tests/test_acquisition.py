"""Tests for the acquisition controller."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="PySide6 nicht verf?gbar", exc_type=ImportError)

from wtc3_logger.acquisition import AcquisitionController
from wtc3_logger.config import AppConfig
from wtc3_logger.databus import DataBus


def test_acquisition_controller_reads_sample() -> None:
    sample_path = Path(__file__).resolve().parents[1] / "wtc3_logger" / "sample.txt"
    config = AppConfig(sample_file=sample_path)
    bus = DataBus(maxlen=128)
    controller = AcquisitionController(config, bus)
    controller.start()
    try:
        deadline = time.time() + 1.5
        while not bus.snapshot() and time.time() < deadline:
            time.sleep(0.05)
        assert bus.snapshot()
    finally:
        controller.stop()



def test_raw_log_matches_stream(tmp_path) -> None:
    sample_lines = [
        "P04 P07 P70",
        "CC_CV WTC3206 PMNN4809A",
        "P04 P06 P10 P11",
        "CC_CV 0 1 2",
        "CC_CV 1 2 3",
        "CC_CV 2 3 4",
    ]
    sample_path = tmp_path / 'sample.txt'
    sample_path.write_text('\n'.join(sample_lines), encoding='utf-8')
    log_dir = tmp_path / 'raw'
    config = AppConfig(sample_file=sample_path, persist_csv=True, persist_path=log_dir)
    bus = DataBus(maxlen=16)
    controller = AcquisitionController(config, bus)
    controller.start()
    try:
        deadline = time.time() + 1.5
        while time.time() < deadline:
            raw_path = controller.raw_log_path()
            if raw_path and Path(raw_path).exists():
                recorded = Path(raw_path).read_text(encoding='utf-8').splitlines()
                if len(recorded) >= len(sample_lines):
                    break
            time.sleep(0.05)
        else:
            pytest.fail('raw log was not populated')
    finally:
        controller.stop()

    raw_path = controller.raw_log_path()
    assert raw_path is not None
    recorded = Path(raw_path).read_text(encoding='utf-8').splitlines()
    assert recorded[: len(sample_lines)] == sample_lines
    name = Path(raw_path).stem
    assert 'PMNN4809A' in name and 'WTC3206' in name
