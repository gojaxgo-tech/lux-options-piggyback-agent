from app.classifier import classify_text
from app.models import Classification


def test_classifies_new_trade_alert():
    assert classify_text("$HNI 45 CALL 7/17 avg .75").classification == Classification.NEW_TRADE_ALERT


def test_classifies_claimed_result():
    assert classify_text("Winner sold for 300%").classification == Classification.CLAIMED_RESULT


def test_classifies_unknown_when_uncertain():
    result = classify_text("$HNI maybe soon")
    assert result.classification == Classification.UNKNOWN

