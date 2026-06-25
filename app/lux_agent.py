from __future__ import annotations

from app.classifier import classify_text
from app.models import AutonomyLevel, Classification, ScoreDecision, SocialPost
from app.notifications import format_alert_notification
from app.paper_trading import PaperTracker
from app.parser import parse_alerts, parse_trade_update


class LuxAgent:
    """Lux is the VPS runtime shell that runs the private Sniper Alert monitor."""

    def __init__(
        self,
        social_provider,
        market_data_provider,
        broker_provider,
        notifier,
        scoring_engine,
        llm_fallback,
        database,
        audit_logger,
        settings,
    ):
        self.social_provider = social_provider
        self.market_data_provider = market_data_provider
        self.broker_provider = broker_provider
        self.notifier = notifier
        self.scoring_engine = scoring_engine
        self.llm_fallback = llm_fallback
        self.database = database
        self.audit_logger = audit_logger
        self.settings = settings
        self.paper_tracker = PaperTracker(database)

    def run_scan_cycle(self) -> int:
        state = self.database.get_control_state()
        self.database.set_source_check(successful=False)
        if state.kill_switch:
            self.audit_logger.log("scan_blocked", "Kill switch active; scan skipped", "warning")
            return 0
        if state.paused:
            self.audit_logger.log("scan_skipped", "Sniper Alert is paused", "info")
            return 0
        seen = self.database.seen_post_ids()
        posts = self.social_provider.fetch_new_posts(seen)
        for post in posts:
            self.process_post(post)
        self.database.set_source_check(successful=bool(posts))
        return len(posts)

    def ingest_manual(self, text: str) -> dict:
        from app.social_provider import manual_post

        post = manual_post(text, self.settings.source_platform, self.settings.source_account)
        result = self.process_post(post)
        if result.get("status") != "duplicate":
            self.database.set_source_check(successful=True)
        return result

    def process_post(self, post: SocialPost) -> dict:
        social_post_id, inserted = self.database.save_social_post(post)
        if not inserted:
            self.audit_logger.log("post_deduplicated", f"Duplicate post skipped: {post.source_post_id}")
            return {"status": "duplicate", "social_post_id": social_post_id}

        self.audit_logger.log("post_ingested", f"Ingested post {post.source_post_id}")
        classification = classify_text(post.raw_text)
        if classification.confidence < 0.6:
            llm_result = self.llm_fallback.maybe_review(post.raw_text, "low_classification_confidence")
            if llm_result:
                self.audit_logger.log("llm_review_result", f"classification={llm_result.get('classification', 'unknown')}")
        self.database.update_classification(social_post_id, classification)
        self.audit_logger.log("post_classified", f"{post.source_post_id}: {classification.classification.value}")

        if classification.classification == Classification.NEW_TRADE_ALERT:
            return self._handle_new_alert(social_post_id, post)
        if classification.classification in (Classification.CLAIMED_RESULT, Classification.TRADE_UPDATE, Classification.SOURCE_EXIT_UPDATE):
            return self._handle_update(social_post_id, post, classification.classification)

        self.audit_logger.log("llm_call_skipped", f"Rules classified post as {classification.classification.value}")
        return {"status": classification.classification.value, "social_post_id": social_post_id}

    def _handle_new_alert(self, social_post_id: int, post: SocialPost) -> dict:
        parsed_alert_ids: list[int] = []
        for alert in parse_alerts(post.raw_text):
            if alert.parse_confidence < 0.8:
                llm_result = self.llm_fallback.maybe_review(post.raw_text, "low_parse_confidence")
                if llm_result:
                    self.audit_logger.log("llm_review_result", f"summary={llm_result.get('summary', 'reviewed')}")
            parsed_alert_id = self.database.save_parsed_alert(social_post_id, alert)
            parsed_alert_ids.append(parsed_alert_id)
            self.audit_logger.log("alert_parsed", f"Parsed alert {parsed_alert_id}: {alert.contract_symbol}")
            quote = self.market_data_provider.get_option_quote(alert)
            quote_id = self.database.save_quote(parsed_alert_id, quote) if quote else None
            if not quote:
                self.audit_logger.log("market_data_unavailable", f"No quote for alert {parsed_alert_id}", "warning")
            score = self.scoring_engine.score(alert, quote, self.database.get_control_state())
            self.database.save_score(parsed_alert_id, quote_id, score)
            self.audit_logger.log("score_generated", f"Alert {parsed_alert_id}: {score.decision.value} {score.score}")
            self._notify_alert(alert, quote, score)
            if self.database.get_control_state().autonomy_level == AutonomyLevel.PAPER_TRADE:
                opened = self.paper_tracker.maybe_open(parsed_alert_id, alert, quote, enabled=True)
                if opened:
                    self.audit_logger.log("paper_position_opened", f"Paper position opened for alert {parsed_alert_id}")
        return {"status": "processed", "social_post_id": social_post_id, "parsed_alert_ids": parsed_alert_ids}

    def _handle_update(self, social_post_id: int, post: SocialPost, classification: Classification) -> dict:
        update = parse_trade_update(post.raw_text)
        update_id = self.database.save_trade_update(social_post_id, update)
        if classification == Classification.CLAIMED_RESULT:
            event = "claimed_performance_detected"
        elif classification == Classification.SOURCE_EXIT_UPDATE or update.source_exit_detected:
            event = "source_exit_detected"
        else:
            event = "source_update_matched"
        self.audit_logger.log(event, f"Update {update_id} stored as unverified unless quote data verifies it")
        return {"status": classification.value, "social_post_id": social_post_id, "update_id": update_id}

    def _notify_alert(self, alert, quote, score) -> None:
        state = self.database.get_control_state()
        if state.paused or state.kill_switch:
            self.audit_logger.log("notification_skipped", "Paused or kill switch active")
            return
        message = format_alert_notification(self.settings.source_account, alert, quote, score)
        try:
            self.notifier.send("Sniper Alert", message)
            self.audit_logger.log("notification_sent", "Private alert notification sent")
        except Exception as exc:
            self.audit_logger.log("notification_failed", str(exc), "error")
