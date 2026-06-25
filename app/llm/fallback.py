from __future__ import annotations

from app.llm.client import LlmClient


class LlmFallback:
    """Rules-first fallback. LLM output can only classify, extract, or summarize."""

    def __init__(self, settings, audit_logger):
        self.settings = settings
        self.audit_logger = audit_logger
        self.client = LlmClient(settings.openai_api_key, settings.llm_model_fast)

    def available(self) -> bool:
        return bool(self.settings.llm_enabled and self.settings.openai_api_key)

    def maybe_review(self, text: str, reason: str) -> dict | None:
        if not self.settings.llm_enabled:
            self.audit_logger.log("llm_call_skipped", f"LLM disabled; reason={reason}")
            return None
        if not self.settings.openai_api_key:
            severity = "error" if self.settings.llm_required else "warning"
            self.audit_logger.log("llm_call_skipped", "OPENAI_API_KEY missing; continuing rules-only", severity)
            if self.settings.llm_required:
                raise RuntimeError("LLM_REQUIRED=true but OPENAI_API_KEY is missing")
            return None
        self.audit_logger.log("llm_call_made", f"Low-confidence LLM review requested; reason={reason}")
        result = self.client.classify_or_extract(text)
        if result is None:
            self.audit_logger.log("llm_call_failed", "LLM review failed; continuing with needs_review", "warning")
            return None
        return result
