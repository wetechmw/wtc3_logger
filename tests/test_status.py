from wtc3_logger.status import decode_status, label_strategy


def test_decode_status_with_mapping() -> None:
    mapping = {0: "Idle", 2: "Balancing"}
    assert decode_status(5, mapping) == ["Idle", "Balancing"]


def test_decode_status_with_invalid_value() -> None:
    mapping = {1: "Charging"}
    assert decode_status("invalid", mapping) == []


def test_label_strategy_returns_label() -> None:
    labels = {"CC_CV": "Konstantstrom / Konstantspannung"}
    assert label_strategy("CC_CV", labels) == "Konstantstrom / Konstantspannung"
    assert label_strategy("UNKNOWN", labels) is None
