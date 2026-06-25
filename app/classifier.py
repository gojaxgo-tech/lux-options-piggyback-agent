from __future__ import annotations

import re

from app.models import Classification, ClassificationResult


CONTRACT_RE = re.compile(
    r"\$?[A-Z]{1,6}\s+\d+(?:\.\d+)?\s+(CALL|PUT|C|P)\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?",
    re.IGNORECASE,
)
CLAIM_RE = re.compile(
    r"(\bnow\s+\d+(?:\.\d+)?\s*%\+?|\d+(?:\.\d+)?\s*%\+?\s*(?:overnight|stress free|winner|banked)|\bwinner\b|\bbanked\b|\bcongrats\b|\bcalled it\b|\bfrom\s+\.\d+\s+to\s+\d)",
    re.IGNORECASE,
)
HYPE_RE = re.compile(r"\b(\d+x|10x|1000%\s+potential|\d+(?:\.\d+)?\s*%\s+potential|potential)\b", re.IGNORECASE)
EXIT_RE = re.compile(
    r"\b(sold|trim|trimmed|take profit|took profit|cut|stopped|out|closed|runner left|leave runners)\b",
    re.IGNORECASE,
)
UPDATE_RE = re.compile(
    r"\b(hold|still holding|added|averaged|watch|moving|runner|update|alert update)\b",
    re.IGNORECASE,
)
MARKET_COMMENTARY_RE = re.compile(r"\b(spy|qqq|market|fomc|fed|cpi|jobs|yields|watchlist)\b", re.IGNORECASE)


def classify_text(text: str) -> ClassificationResult:
    normalized = " ".join(text.split())
    if CONTRACT_RE.search(normalized):
        reason = "hype_potential" if HYPE_RE.search(normalized) else "contract_pattern"
        return ClassificationResult(Classification.NEW_TRADE_ALERT, 0.95, reason)
    if HYPE_RE.search(normalized):
        return ClassificationResult(Classification.GENERAL_MARKET_COMMENTARY, 0.7, "hype_potential")
    if CLAIM_RE.search(normalized):
        return ClassificationResult(Classification.CLAIMED_RESULT, 0.85, "claimed_performance_terms")
    if EXIT_RE.search(normalized):
        return ClassificationResult(Classification.SOURCE_EXIT_UPDATE, 0.82, "exit_terms")
    if UPDATE_RE.search(normalized):
        return ClassificationResult(Classification.TRADE_UPDATE, 0.75, "update_terms")
    if MARKET_COMMENTARY_RE.search(normalized):
        return ClassificationResult(Classification.GENERAL_MARKET_COMMENTARY, 0.65, "market_commentary_terms")
    if "$" not in normalized and "CALL" not in normalized.upper() and "PUT" not in normalized.upper():
        return ClassificationResult(Classification.NON_TRADE, 0.7, "no_trade_indicators")
    return ClassificationResult(Classification.UNKNOWN, 0.3, "low_confidence")
