from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from app.models import (
    AutonomyLevel,
    ClassificationResult,
    ControlState,
    MarketQuote,
    ParsedAlert,
    ScoreResult,
    SocialPost,
    TradeUpdate,
    utc_now,
)


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.migrate()

    def migrate(self) -> None:
        self.conn.executescript(
            """
            create table if not exists social_posts (
                id integer primary key autoincrement,
                source_platform text not null,
                source_account text not null,
                source_post_id text not null,
                source_url text,
                posted_at text,
                ingested_at text not null,
                raw_text text not null,
                raw_json text,
                classification text,
                classification_confidence real,
                processed integer not null default 0,
                created_at text not null,
                unique(source_platform, source_account, source_post_id)
            );

            create table if not exists parsed_alerts (
                id integer primary key autoincrement,
                social_post_id integer not null,
                ticker text,
                option_type text,
                strike real,
                expiration_date text,
                alert_price real,
                alert_price_raw text,
                contract_symbol text,
                side text,
                strategy text,
                time_horizon text,
                confidence_label text,
                hype_label text,
                raw_alert_text text not null,
                parse_confidence real not null,
                needs_review integer not null,
                metadata_json text,
                created_at text not null
            );

            create table if not exists trade_updates (
                id integer primary key autoincrement,
                social_post_id integer not null,
                related_alert_id integer,
                update_type text not null,
                claimed_price real,
                claimed_percent_gain real,
                claimed_status text,
                raw_update_text text not null,
                created_at text not null
            );

            create table if not exists quotes (
                id integer primary key autoincrement,
                parsed_alert_id integer not null,
                quote_source text not null,
                quote_time text not null,
                underlying_price real,
                option_bid real,
                option_ask real,
                option_last real,
                option_mid real,
                volume integer,
                open_interest integer,
                iv real,
                raw_json text,
                created_at text not null
            );

            create table if not exists scores (
                id integer primary key autoincrement,
                parsed_alert_id integer not null,
                quote_id integer,
                score integer not null,
                decision text not null,
                reason_codes text not null,
                summary text not null,
                created_at text not null
            );

            create table if not exists paper_positions (
                id integer primary key autoincrement,
                parsed_alert_id integer not null,
                status text not null,
                paper_entry_price real,
                paper_entry_time text,
                paper_exit_price real,
                paper_exit_time text,
                paper_pnl_percent real,
                notes text,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists claimed_performance (
                id integer primary key autoincrement,
                social_post_id integer not null,
                related_alert_id integer,
                claimed_gain_percent real,
                claimed_entry real,
                claimed_exit real,
                claimed_text text not null,
                verification_status text not null,
                created_at text not null
            );

            create table if not exists audit_events (
                id integer primary key autoincrement,
                event_type text not null,
                severity text not null,
                message text not null,
                metadata_json text,
                created_at text not null
            );

            create table if not exists control_state (
                id integer primary key check (id = 1),
                paused integer not null,
                kill_switch integer not null,
                autonomy_level text not null,
                last_source_check_at text,
                last_successful_ingest_at text,
                updated_at text not null
            );

            create table if not exists health_checks (
                id integer primary key autoincrement,
                check_name text not null,
                status text not null,
                message text not null,
                created_at text not null
            );
            """
        )
        self.conn.commit()

    def initialize_control_state(self, autonomy_level: AutonomyLevel, kill_switch: bool) -> None:
        now = utc_now().isoformat()
        self.conn.execute(
            """
            insert or ignore into control_state
            (id, paused, kill_switch, autonomy_level, updated_at)
            values (1, 0, ?, ?, ?)
            """,
            (1 if kill_switch else 0, autonomy_level.value, now),
        )
        self.conn.commit()

    def get_control_state(self) -> ControlState:
        row = self.conn.execute("select * from control_state where id = 1").fetchone()
        if not row:
            self.initialize_control_state(AutonomyLevel.MONITOR_ONLY, False)
            row = self.conn.execute("select * from control_state where id = 1").fetchone()
        return ControlState(
            paused=bool(row["paused"]),
            kill_switch=bool(row["kill_switch"]),
            autonomy_level=AutonomyLevel(row["autonomy_level"]),
            last_source_check_at=row["last_source_check_at"],
            last_successful_ingest_at=row["last_successful_ingest_at"],
        )

    def set_paused(self, paused: bool) -> None:
        self._update_control("paused", 1 if paused else 0)

    def set_kill_switch(self, enabled: bool) -> None:
        self._update_control("kill_switch", 1 if enabled else 0)

    def set_autonomy(self, level: AutonomyLevel) -> None:
        self._update_control("autonomy_level", level.value)

    def set_source_check(self, successful: bool = False) -> None:
        now = utc_now().isoformat()
        if successful:
            self.conn.execute(
                "update control_state set last_source_check_at = ?, last_successful_ingest_at = ?, updated_at = ? where id = 1",
                (now, now, now),
            )
        else:
            self.conn.execute(
                "update control_state set last_source_check_at = ?, updated_at = ? where id = 1",
                (now, now),
            )
        self.conn.commit()

    def _update_control(self, field: str, value) -> None:
        now = utc_now().isoformat()
        self.conn.execute(f"update control_state set {field} = ?, updated_at = ? where id = 1", (value, now))
        self.conn.commit()

    def save_social_post(self, post: SocialPost) -> tuple[int, bool]:
        now = utc_now().isoformat()
        cursor = self.conn.execute(
            """
            insert or ignore into social_posts
            (source_platform, source_account, source_post_id, source_url, posted_at, ingested_at,
             raw_text, raw_json, processed, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                post.source_platform,
                post.source_account,
                post.source_post_id,
                post.source_url,
                post.posted_at.isoformat(),
                now,
                post.raw_text,
                post.raw_json,
                now,
            ),
        )
        self.conn.commit()
        inserted = cursor.rowcount > 0
        row = self.conn.execute(
            """
            select id from social_posts
            where source_platform = ? and source_account = ? and source_post_id = ?
            """,
            (post.source_platform, post.source_account, post.source_post_id),
        ).fetchone()
        return int(row["id"]), inserted

    def update_classification(self, social_post_id: int, result: ClassificationResult) -> None:
        self.conn.execute(
            """
            update social_posts
            set classification = ?, classification_confidence = ?, processed = 1
            where id = ?
            """,
            (result.classification.value, result.confidence, social_post_id),
        )
        self.conn.commit()

    def save_parsed_alert(self, social_post_id: int, alert: ParsedAlert) -> int:
        now = utc_now().isoformat()
        metadata = {"inferred_fields": list(alert.inferred_fields)}
        cursor = self.conn.execute(
            """
            insert into parsed_alerts
            (social_post_id, ticker, option_type, strike, expiration_date, alert_price, alert_price_raw,
             contract_symbol, side, strategy, time_horizon, confidence_label, hype_label, raw_alert_text,
             parse_confidence, needs_review, metadata_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                social_post_id,
                alert.ticker,
                alert.option_type.value if alert.option_type else None,
                alert.strike,
                alert.expiration_date,
                alert.alert_price,
                alert.alert_price_raw,
                alert.contract_symbol,
                alert.side,
                alert.strategy,
                alert.time_horizon,
                alert.confidence_label,
                alert.hype_label,
                alert.raw_alert_text,
                alert.parse_confidence,
                1 if alert.needs_review else 0,
                json.dumps(metadata),
                now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def save_trade_update(self, social_post_id: int, update: TradeUpdate) -> int:
        related_alert_id = self.find_latest_alert_id(update.ticker)
        now = utc_now().isoformat()
        cursor = self.conn.execute(
            """
            insert into trade_updates
            (social_post_id, related_alert_id, update_type, claimed_price, claimed_percent_gain,
             claimed_status, raw_update_text, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                social_post_id,
                related_alert_id,
                update.update_type,
                update.claimed_price,
                update.claimed_percent_gain,
                update.claimed_status,
                update.raw_update_text,
                now,
            ),
        )
        if update.claimed_percent_gain is not None or update.claimed_price is not None:
            self.conn.execute(
                """
                insert into claimed_performance
                (social_post_id, related_alert_id, claimed_gain_percent, claimed_entry, claimed_exit,
                 claimed_text, verification_status, created_at)
                values (?, ?, ?, ?, ?, ?, 'unverified', ?)
                """,
                (
                    social_post_id,
                    related_alert_id,
                    update.claimed_percent_gain,
                    None,
                    update.claimed_price,
                    update.raw_update_text,
                    now,
                ),
            )
        self.conn.commit()
        return int(cursor.lastrowid)

    def save_quote(self, parsed_alert_id: int, quote: MarketQuote) -> int:
        now = utc_now().isoformat()
        cursor = self.conn.execute(
            """
            insert into quotes
            (parsed_alert_id, quote_source, quote_time, underlying_price, option_bid, option_ask,
             option_last, option_mid, volume, open_interest, iv, raw_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed_alert_id,
                quote.quote_source,
                quote.quote_time.isoformat(),
                quote.underlying_price,
                quote.option_bid,
                quote.option_ask,
                quote.option_last,
                quote.option_mid,
                quote.volume,
                quote.open_interest,
                quote.iv,
                quote.raw_json,
                now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def save_score(self, parsed_alert_id: int, quote_id: Optional[int], score: ScoreResult) -> None:
        self.conn.execute(
            """
            insert into scores
            (parsed_alert_id, quote_id, score, decision, reason_codes, summary, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed_alert_id,
                quote_id,
                score.score,
                score.decision.value,
                ",".join(score.reason_codes),
                score.summary,
                utc_now().isoformat(),
            ),
        )
        self.conn.commit()

    def create_paper_position(self, parsed_alert_id: int, entry_price: float, notes: str) -> None:
        now = utc_now().isoformat()
        self.conn.execute(
            """
            insert into paper_positions
            (parsed_alert_id, status, paper_entry_price, paper_entry_time, notes, created_at, updated_at)
            values (?, 'open', ?, ?, ?, ?, ?)
            """,
            (parsed_alert_id, entry_price, now, notes, now, now),
        )
        self.conn.commit()

    def find_latest_alert_id(self, ticker: Optional[str]) -> Optional[int]:
        if not ticker:
            return None
        row = self.conn.execute(
            "select id from parsed_alerts where ticker = ? order by created_at desc, id desc limit 1",
            (ticker.upper(),),
        ).fetchone()
        return int(row["id"]) if row else None

    def seen_post_ids(self) -> set[str]:
        return {row["source_post_id"] for row in self.conn.execute("select source_post_id from social_posts")}

    def audit(self, event_type: str, message: str, severity: str = "info", metadata: Optional[dict] = None) -> None:
        self.conn.execute(
            """
            insert into audit_events (event_type, severity, message, metadata_json, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (event_type, severity, message, json.dumps(metadata or {}), utc_now().isoformat()),
        )
        self.conn.commit()

    def health(self, check_name: str, status: str, message: str) -> None:
        self.conn.execute(
            "insert into health_checks (check_name, status, message, created_at) values (?, ?, ?, ?)",
            (check_name, status, message, utc_now().isoformat()),
        )
        self.conn.commit()

