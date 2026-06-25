from __future__ import annotations

import json
import urllib.error
import urllib.request


class LlmClient:
    def __init__(self, api_key: str, model: str, timeout_seconds: int = 20):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def classify_or_extract(self, text: str) -> dict | None:
        if not self.api_key:
            return None
        prompt = (
            "Classify or extract this private options alert post. Return JSON only. "
            "Allowed classifications: new_trade_alert, trade_update, claimed_result, "
            "general_market_commentary, non_trade, unknown. Extract fields only if present. "
            "Never approve a trade, size a trade, recommend buying, or override safety controls.\n\n"
            f"Post:\n{text}"
        )
        payload = {
            "model": self.model,
            "input": prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "sniper_alert_llm_review",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "classification": {"type": "string"},
                            "summary": {"type": "string"},
                            "ticker": {"type": ["string", "null"]},
                            "option_type": {"type": ["string", "null"]},
                            "strike": {"type": ["number", "null"]},
                            "expiration": {"type": ["string", "null"]},
                            "alert_price": {"type": ["number", "null"]},
                            "confidence": {"type": "number"},
                            "needs_review": {"type": "boolean"},
                        },
                        "required": [
                            "classification",
                            "summary",
                            "ticker",
                            "option_type",
                            "strike",
                            "expiration",
                            "alert_price",
                            "confidence",
                            "needs_review",
                        ],
                    },
                    "strict": True,
                }
            },
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

        text_output = body.get("output_text")
        if not text_output:
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in ("output_text", "text"):
                        text_output = content.get("text")
                        break
                if text_output:
                    break
        if not text_output:
            return None
        try:
            return json.loads(text_output)
        except json.JSONDecodeError:
            return {"classification": "unknown", "summary": text_output, "needs_review": True}
