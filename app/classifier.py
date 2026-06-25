from __future__ import annotations

import re

from app.models import Classification, ClassificationResult


CONTRACT_RE = re.compile(
    r"\$?[A-Z]{1,6}\s+\d+(?:\.\d+)?\s+(CALL|PUT|C|P)\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?",
    re.IGNORECASE,
)
CLAIM_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*%|\brunner\b|\bsold\b|\btrim(?:med)?\b|\btook profit\b|\bcongrats\b|\bwinner\b|\bbanked\b)",
    re.IGNORECASE,
)
UPDATE_RE = re.compile(
    r"\b(hold|stop|trim|added|averaged|still in|watch|moving|alert update|runner)\b",
    re.IGNORECASE,
)
MARKET_COMMENTARY_RE = re.compile(r"\b(spy|qqq|market|fomc|fed|cpi|jobs|yields|watchlist)\b", re.IGNORECASE)


def classify_text(text: str) -> ClassificationResult:
    normalized = " ".join(text.split())
    if CONTRACT_RE.search(normalized):
        return ClassificationResult(Classification.NEW_TRADE_ALERT, 0.95, "contract_pattern")
    if CLAIM_RE.search(normalized):
        return ClassificationResult(Classification.CLAIMED_RESULT, 0.85, "claimed_performance_terms")
    if UPDATE_RE.search(normalized):
        return ClassificationResult(Classification.TRADE_UPDATE, 0.75, "update_terms")
    if MARKET_COMMENTARY_RE.search(normalized):
        return ClassificationResult(Classification.GENERAL_MARKET_COMMENTARY, 0.65, "market_commentary_terms")
    if "$" not in normalized and "CALL" not in normalized.upper() and "PUT" not in normalized.upper():
        return ClassificationResult(Classification.NON_TRADE, 0.7, "no_trade_indicators")
    return ClassificationResult(Classification.UNKNOWN, 0.3, "low_confidence")

