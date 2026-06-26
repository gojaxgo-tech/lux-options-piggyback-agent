from app.classifier import classify_text
from app.models import Classification


def test_classifies_new_trade_alert():
    assert classify_text("$HNI 45 CALL 7/17 avg .75").classification == Classification.CLEAN_ENTRY


def test_classifies_claimed_result():
    assert classify_text("Winner sold for 300%").classification == Classification.CLAIMED_RESULT


def test_hype_potential_is_not_claimed_result():
    result = classify_text("1000% POTENTIAL 🔥🚨\n\n$MTUS 22.5 CALL 7/17 HERE🚨")
    assert result.classification == Classification.HYPE_POTENTIAL
    assert result.reason == "hype_potential"


def test_real_claimed_result_posts_are_claims():
    assert classify_text("$XYL now 220%+").classification == Classification.CLAIMED_RESULT
    assert classify_text("$XYL 200%+ OVERNIGHT STRESS FREE").classification == Classification.CLAIMED_RESULT


def test_classifies_unknown_when_uncertain():
    result = classify_text("$HNI maybe soon")
    assert result.classification == Classification.AMBIGUOUS_UPDATE
