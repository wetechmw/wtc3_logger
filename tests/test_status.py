from wtc3_logger.status import StatusDetail, decode_status, label_strategy


def test_decode_status_returns_structured_fields() -> None:
    detail = decode_status(0)
    assert isinstance(detail, StatusDetail)
    assert detail.raw_value == 0
    assert "Batteriespannung: Tiefentladen" in detail.details
    assert "Fehler: Keine Fehler" in detail.badges


def test_decode_status_with_invalid_value() -> None:
    detail = decode_status("invalid")
    assert detail.raw_value is None
    assert detail.badges == []
    assert detail.details == []


def test_decode_status_includes_bit_flags() -> None:
    value = (1 << 14) | (1 << 22)  # Eingang aktiviert + ΔV Drop
    detail = decode_status(value)
    assert any(text.startswith("Peripherie: Eingang") for text in detail.details)
    assert any("ΔV Drop" in text for text in detail.details)


def test_label_strategy_returns_label() -> None:
    labels = {"CC_CV": "Konstantstrom / Konstantspannung"}
    assert label_strategy("CC_CV", labels) == "Konstantstrom / Konstantspannung"
    assert label_strategy("UNKNOWN", labels) is None