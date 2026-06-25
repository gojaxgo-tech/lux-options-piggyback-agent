from datetime import date

from app.models import OptionType
from app.parser import parse_first_alert


def test_required_parser_examples():
    examples = [
        ("$HNI 45 CALL 7/17 avg .75", "HNI", 45, OptionType.CALL, 0.75),
        ("$ACGL 105 CALL 7/17 avg .20", "ACGL", 105, OptionType.CALL, 0.20),
        ("HIGH CONFIDENCE $ACGL 105 CALL 7/17 avg .20", "ACGL", 105, OptionType.CALL, 0.20),
        ("SWING OVERNIGHT $HNI 45 CALL 7/17 HERE", "HNI", 45, OptionType.CALL, None),
        ("700% POTENTIAL $HNI 45 CALL 7/17 avg .75", "HNI", 45, OptionType.CALL, 0.75),
    ]

    for text, ticker, strike, option_type, price in examples:
        parsed = parse_first_alert(text, today=date(2026, 6, 25))
        assert parsed.ticker == ticker
        assert parsed.strike == strike
        assert parsed.option_type == option_type
        assert parsed.expiration_date == "2026-07-17"
        assert parsed.alert_price == price


def test_parser_marks_here_without_price_for_review():
    parsed = parse_first_alert("SWING OVERNIGHT $HNI 45 CALL 7/17 HERE", today=date(2026, 6, 25))

    assert parsed.time_horizon == "SWING OVERNIGHT"
    assert parsed.needs_review
    assert "valid_contract_missing_price" in parsed.inferred_fields
    assert "contract_parse_low_confidence" not in parsed.inferred_fields


def test_real_here_posts_are_valid_contract_missing_price():
    examples = [
        "Overnight swing\n\n$HNI 45 CALL 7/17 HERE🚨",
        "SWING OVERNIGHT 🔥🚨\n\n$HNI 45 CALL 7/17 HERE🚨",
        "1000% POTENTIAL 🔥🚨\n\n$MTUS 22.5 CALL 7/17 HERE🚨",
        "10x potential 🔥🚨\n\n$MTUS 22.5 CALL 7/17 HERE🚨",
    ]

    for text in examples:
        parsed = parse_first_alert(text, today=date(2026, 6, 25))
        assert parsed.ticker in {"HNI", "MTUS"}
        assert parsed.expiration_date == "2026-07-17"
        assert parsed.alert_price is None
        assert "valid_contract_missing_price" in parsed.inferred_fields
