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
from app.trades import canonical_trade_id


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

            create table if not exists trades (
                canonical_trade_id text primary key,
                ticker text not null,
                option_type text not null,
                strike real not null,
                expiration_date text not null,
                lifecycle_state text not null,
                first_alert_id integer,
                latest_alert_id integer,
                classification_label text,
                source_quality_confidence real,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists state_changes (
                id integer primary key autoincrement,
                canonical_trade_id text,
                event_type text not null,
                source_post_id text,
                state_hash text not null,
                previous_state text,
                new_state text,
                message text not null,
                created_at text not null
            );

            create table if not exists notification_dedupe (
                id integer primary key autoincrement,
                canonical_trade_id text,
                event_type text not null,
                source_post_id text,
                state_hash text not null,
                created_at text not null,
                unique(canonical_trade_id, event_type, source_post_id, state_hash)
            );
            """
        )
        self._ensure_columns("parsed_alerts", {
            "canonical_trade_id": "text",
            "entry_classification": "text",
        })
        self._ensure_columns("trade_updates", {
            "canonical_trade_id": "text",
        })
        self._ensure_columns("scores", {
            "recommendation_confidence": "real",
            "quote_confidence": "real",
        })
        self._ensure_paper_columns()
        self._backfill_trades()
        self.conn.commit()

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in self.conn.execute(f"pragma table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                self.conn.execute(f"alter table {table} add column {name} {definition}")

    def _ensure_paper_columns(self) -> None:
        existing = {row["name"] for row in self.conn.execute("pragma table_info(paper_positions)")}
        columns = {
            "source_post_id": "text",
            "source_url": "text",
            "ticker": "text",
            "option_type": "text",
            "strike": "real",
            "expiration_date": "text",
            "paper_entry_source": "text",
            "max_seen_price": "real",
            "max_seen_gain_percent": "real",
            "min_seen_price": "real",
            "max_drawdown_percent": "real",
            "last_price": "real",
            "last_price_time": "text",
            "source_exit_detected": "integer not null default 0",
            "source_exit_post_id": "text",
            "canonical_trade_id": "text",
        }
        for name, definition in columns.items():
            if name not in existing:
                self.conn.execute(f"alter table paper_positions add column {name} {definition}")

    def _backfill_trades(self) -> None:
        rows = self.conn.execute("select * from parsed_alerts where canonical_trade_id is null").fetchall()
        for row in rows:
            alert = _alert_from_row(row)
            trade_id = canonical_trade_id(alert)
            if not trade_id:
                continue
            entry_classification = _entry_classification(row["metadata_json"])
            self.conn.execute(
                "update parsed_alerts set canonical_trade_id = ?, entry_classification = ? where id = ?",
                (trade_id, entry_classification, row["id"]),
            )
            self._upsert_trade_from_row(trade_id, row, entry_classification)
        paper_rows = self.conn.execute(
            """
            select paper_positions.id, parsed_alerts.canonical_trade_id
            from paper_positions
            join parsed_alerts on parsed_alerts.id = paper_positions.parsed_alert_id
            where paper_positions.canonical_trade_id is null and parsed_alerts.canonical_trade_id is not null
            """
        ).fetchall()
        for row in paper_rows:
            self.conn.execute("update paper_positions set canonical_trade_id = ? where id = ?", (row["canonical_trade_id"], row["id"]))

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
        trade_id = canonical_trade_id(alert)
        entry_classification = _entry_classification(json.dumps(metadata))
        cursor = self.conn.execute(
            """
            insert into parsed_alerts
            (social_post_id, ticker, option_type, strike, expiration_date, alert_price, alert_price_raw,
             contract_symbol, side, strategy, time_horizon, confidence_label, hype_label, raw_alert_text,
             parse_confidence, needs_review, metadata_json, created_at, canonical_trade_id, entry_classification)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                trade_id,
                entry_classification,
            ),
        )
        parsed_alert_id = int(cursor.lastrowid)
        if trade_id:
            row = self.conn.execute("select * from parsed_alerts where id = ?", (parsed_alert_id,)).fetchone()
            self._upsert_trade_from_row(trade_id, row, entry_classification)
        self.conn.commit()
        return parsed_alert_id

    def save_trade_update(self, social_post_id: int, update: TradeUpdate) -> int:
        related_alert_id = self.find_latest_alert_id(update.ticker)
        trade_id = None
        if related_alert_id:
            related = self.conn.execute("select canonical_trade_id from parsed_alerts where id = ?", (related_alert_id,)).fetchone()
            trade_id = related["canonical_trade_id"] if related else None
        now = utc_now().isoformat()
        cursor = self.conn.execute(
            """
            insert into trade_updates
            (social_post_id, related_alert_id, canonical_trade_id, update_type, claimed_price, claimed_percent_gain,
             claimed_status, raw_update_text, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                social_post_id,
                related_alert_id,
                trade_id,
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
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    social_post_id,
                    related_alert_id,
                    update.claimed_percent_gain,
                    None,
                    update.claimed_price,
                    update.raw_update_text,
                    "not_enough_data",
                    now,
                ),
            )
        if update.source_exit_detected and related_alert_id:
            source_post_id = self.conn.execute("select source_post_id from social_posts where id = ?", (social_post_id,)).fetchone()
            self.mark_source_exit(related_alert_id, source_post_id["source_post_id"] if source_post_id else None)
        if trade_id:
            lifecycle = _lifecycle_for_update(update.update_type)
            self._set_trade_state(trade_id, lifecycle)
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
        quote_confidence = 0.0 if quote_id is None else 1.0
        recommendation_confidence = max(0.0, min(1.0, score.score / 100))
        self.conn.execute(
            """
            insert into scores
            (parsed_alert_id, quote_id, score, decision, reason_codes, summary, created_at, recommendation_confidence, quote_confidence)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed_alert_id,
                quote_id,
                score.score,
                score.decision.value,
                ",".join(score.reason_codes),
                score.summary,
                utc_now().isoformat(),
                recommendation_confidence,
                quote_confidence,
            ),
        )
        row = self.conn.execute("select canonical_trade_id from parsed_alerts where id = ?", (parsed_alert_id,)).fetchone()
        if row and row["canonical_trade_id"]:
            next_state = "insufficient_data" if "missing_quote" in score.reason_codes else "watching"
            self._set_trade_state(row["canonical_trade_id"], next_state)
        self.conn.commit()

    def create_paper_position(
        self,
        parsed_alert_id: int,
        entry_price: float,
        notes: str,
        entry_source: str = "unknown",
    ) -> None:
        now = utc_now().isoformat()
        alert_row = self.conn.execute(
            """
            select parsed_alerts.*, social_posts.source_post_id, social_posts.source_url
            from parsed_alerts
            join social_posts on social_posts.id = parsed_alerts.social_post_id
            where parsed_alerts.id = ?
            """,
            (parsed_alert_id,),
        ).fetchone()
        self.conn.execute(
            """
            insert into paper_positions
            (parsed_alert_id, status, paper_entry_price, paper_entry_time, notes, created_at, updated_at,
             source_post_id, source_url, ticker, option_type, strike, expiration_date, paper_entry_source,
             max_seen_price, min_seen_price, last_price, last_price_time, canonical_trade_id)
            values (?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed_alert_id,
                entry_price,
                now,
                notes,
                now,
                now,
                alert_row["source_post_id"] if alert_row else None,
                alert_row["source_url"] if alert_row else None,
                alert_row["ticker"] if alert_row else None,
                alert_row["option_type"] if alert_row else None,
                alert_row["strike"] if alert_row else None,
                alert_row["expiration_date"] if alert_row else None,
                entry_source,
                entry_price,
                entry_price,
                entry_price,
                now,
                alert_row["canonical_trade_id"] if alert_row else None,
            ),
        )
        if alert_row and alert_row["canonical_trade_id"]:
            self._set_trade_state(alert_row["canonical_trade_id"], "paper_open")
        self.conn.commit()

    def mark_source_exit(self, parsed_alert_id: int, source_exit_post_id: Optional[str]) -> None:
        now = utc_now().isoformat()
        self.conn.execute(
            """
            update paper_positions
            set status = 'source_exit_detected',
                source_exit_detected = 1,
                source_exit_post_id = ?,
                updated_at = ?
            where parsed_alert_id = ? and status in ('open', 'insufficient_data')
            """,
            (source_exit_post_id, now, parsed_alert_id),
        )
        row = self.conn.execute("select canonical_trade_id from parsed_alerts where id = ?", (parsed_alert_id,)).fetchone()
        if row and row["canonical_trade_id"]:
            self._set_trade_state(row["canonical_trade_id"], "source_exited")
        self.conn.commit()

    def update_paper_position_price(self, parsed_alert_id: int, last_price: float) -> list[int]:
        row = self.conn.execute(
            "select * from paper_positions where parsed_alert_id = ? order by id desc limit 1",
            (parsed_alert_id,),
        ).fetchone()
        if not row or row["paper_entry_price"] in (None, 0):
            return []
        now = utc_now().isoformat()
        entry = float(row["paper_entry_price"])
        gain_pct = round(((last_price - entry) / entry) * 100, 2)
        max_seen = max(last_price, row["max_seen_price"] if row["max_seen_price"] is not None else last_price)
        min_seen = min(last_price, row["min_seen_price"] if row["min_seen_price"] is not None else last_price)
        max_gain = round(((max_seen - entry) / entry) * 100, 2)
        max_drawdown = round(((min_seen - entry) / entry) * 100, 2)
        self.conn.execute(
            """
            update paper_positions
            set last_price = ?,
                last_price_time = ?,
                paper_pnl_percent = ?,
                max_seen_price = ?,
                max_seen_gain_percent = ?,
                min_seen_price = ?,
                max_drawdown_percent = ?,
                updated_at = ?
            where id = ?
            """,
            (last_price, now, gain_pct, max_seen, max_gain, min_seen, max_drawdown, now, row["id"]),
        )
        self.conn.commit()
        crossed = []
        for threshold in (25, 50, 75, 100, 150, 200, 300):
            if gain_pct >= threshold:
                crossed.append(threshold)
        for threshold in (-20, -35, -50, -75, -100):
            if gain_pct <= threshold:
                crossed.append(threshold)
        return crossed

    def paper_position_exists(self, parsed_alert_id: int) -> bool:
        row = self.conn.execute("select id from paper_positions where parsed_alert_id = ? limit 1", (parsed_alert_id,)).fetchone()
        return row is not None

    def should_notify(self, canonical_trade_id: Optional[str], event_type: str, source_post_id: Optional[str], state_hash: str) -> bool:
        cursor = self.conn.execute(
            """
            insert or ignore into notification_dedupe
            (canonical_trade_id, event_type, source_post_id, state_hash, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (canonical_trade_id, event_type, source_post_id, state_hash, utc_now().isoformat()),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def record_state_change(
        self,
        canonical_trade_id: Optional[str],
        event_type: str,
        source_post_id: Optional[str],
        state_hash_value: str,
        previous_state: Optional[str],
        new_state: Optional[str],
        message: str,
    ) -> None:
        self.conn.execute(
            """
            insert into state_changes
            (canonical_trade_id, event_type, source_post_id, state_hash, previous_state, new_state, message, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (canonical_trade_id, event_type, source_post_id, state_hash_value, previous_state, new_state, message, utc_now().isoformat()),
        )
        self.conn.commit()

    def latest_report_data(self) -> dict:
        return {
            "latest_source_posts": [dict(row) for row in self.conn.execute(
                """
                select id, source_post_id, source_url, raw_text, classification, classification_confidence, created_at
                from social_posts order by id desc limit 10
                """
            )],
            "latest_parsed_alerts": [dict(row) for row in self.conn.execute(
                """
                select id, canonical_trade_id, entry_classification, ticker, option_type, strike, expiration_date,
                       alert_price, parse_confidence, needs_review, created_at
                from parsed_alerts order by id desc limit 10
                """
            )],
            "latest_canonical_trades": [dict(row) for row in self.conn.execute(
                "select * from trades order by updated_at desc limit 10"
            )],
            "open_paper_positions": [dict(row) for row in self.conn.execute(
                """
                select id, canonical_trade_id, parsed_alert_id, ticker, option_type, strike, expiration_date,
                       status, paper_entry_price, paper_entry_source, paper_pnl_percent, updated_at
                from paper_positions where status in ('open', 'source_exit_detected', 'insufficient_data')
                order by updated_at desc limit 10
                """
            )],
            "recent_state_changes": [dict(row) for row in self.conn.execute(
                "select * from state_changes order by id desc limit 10"
            )],
            "recent_warnings": [dict(row) for row in self.conn.execute(
                "select id, event_type, severity, message, created_at from audit_events where severity in ('warning', 'error') order by id desc limit 10"
            )],
            "source_quality_summary": self.performance_summary(),
        }

    def _upsert_trade_from_row(self, trade_id: str, row, entry_classification: str) -> None:
        now = utc_now().isoformat()
        existing = self.conn.execute("select * from trades where canonical_trade_id = ?", (trade_id,)).fetchone()
        lifecycle = "new_alert" if entry_classification == "clean_entry" else "insufficient_data"
        if existing:
            self.conn.execute(
                """
                update trades
                set latest_alert_id = ?,
                    classification_label = ?,
                    source_quality_confidence = ?,
                    updated_at = ?
                where canonical_trade_id = ?
                """,
                (row["id"], entry_classification, _source_quality_confidence(entry_classification), now, trade_id),
            )
        else:
            self.conn.execute(
                """
                insert into trades
                (canonical_trade_id, ticker, option_type, strike, expiration_date, lifecycle_state,
                 first_alert_id, latest_alert_id, classification_label, source_quality_confidence, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    row["ticker"],
                    row["option_type"],
                    row["strike"],
                    row["expiration_date"],
                    lifecycle,
                    row["id"],
                    row["id"],
                    entry_classification,
                    _source_quality_confidence(entry_classification),
                    now,
                    now,
                ),
            )

    def _set_trade_state(self, trade_id: str, new_state: str) -> None:
        row = self.conn.execute("select lifecycle_state from trades where canonical_trade_id = ?", (trade_id,)).fetchone()
        if not row or row["lifecycle_state"] == new_state:
            return
        previous = row["lifecycle_state"]
        now = utc_now().isoformat()
        self.conn.execute("update trades set lifecycle_state = ?, updated_at = ? where canonical_trade_id = ?", (new_state, now, trade_id))
        self.record_state_change(trade_id, "lifecycle_state_changed", None, f"{previous}->{new_state}", previous, new_state, f"{trade_id} moved {previous} -> {new_state}")

    def performance_summary(self) -> dict:
        row = self.conn.execute(
            """
            select
              (select count(*) from social_posts) as total_source_posts,
              (select count(*) from parsed_alerts) as total_alerts,
              (select count(*) from parsed_alerts where metadata_json like '%clean_entry%') as clean_priced_entries,
              (select count(*) from parsed_alerts where metadata_json like '%valid_contract_missing_price%') as valid_missing_price_entries,
              (select count(*) from parsed_alerts where metadata_json like '%hype_potential%') as hype_potential_posts,
              (select count(*) from parsed_alerts where metadata_json like '%contract_parse_low_confidence%') as parser_misses,
              (select count(*) from parsed_alerts where metadata_json like '%clean_entry%' or metadata_json like '%valid_contract_missing_price%') as parsed_alerts,
              (select count(*) from parsed_alerts where metadata_json like '%contract_parse_low_confidence%') as unparseable_alerts,
              (select count(*) from trade_updates where update_type = 'trade_update' and raw_update_text like '%add%') as add_updates,
              (select count(*) from trade_updates where update_type = 'trade_update' and (raw_update_text like '%hold%' or raw_update_text like '%watch%')) as hold_updates,
              (select count(*) from trade_updates where update_type = 'source_exit_update' and (raw_update_text like '%trim%' or raw_update_text like '%runner%')) as trim_updates,
              (select count(*) from trade_updates where update_type = 'source_exit_update' and (raw_update_text like '%sold%' or raw_update_text like '%closed%' or raw_update_text like '%out%' or raw_update_text like '%stopped%')) as full_exits,
              (select count(*) from social_posts where classification = 'general_market_commentary') as general_commentary,
              (select count(*) from social_posts where classification = 'unknown') as ambiguous_posts,
              (select count(*) from paper_positions) as paper_copied_alerts,
              (select count(*) from paper_positions where status = 'open') as open_paper_positions,
              (select count(*) from paper_positions where status = 'closed') as closed_paper_positions,
              (select count(*) from paper_positions where status = 'insufficient_data') as insufficient_data,
              (select count(*) from claimed_performance) as source_claims,
              (select count(*) from claimed_performance where verification_status = 'verified_against_quote') as claims_verified,
              (select count(*) from claimed_performance where verification_status = 'contradicted') as claims_contradicted,
              (select count(*) from claimed_performance where verification_status in ('not_enough_data', 'unverified')) as claims_not_enough_data,
              (select count(*) from scores where reason_codes like '%missing_quote%') as alerts_skipped_missing_quote,
              (select count(*) from scores where reason_codes like '%price%chase%' or reason_codes like '%do_not_chase%') as alerts_skipped_chased,
              (select count(*) from scores where reason_codes like '%stale%') as alerts_skipped_stale
            """
        ).fetchone()
        data = dict(row)
        data["hype_potential_posts"] = data["hype_potential_posts"] + self._count_raw_hype_posts()
        gains = [r["paper_pnl_percent"] for r in self.conn.execute("select paper_pnl_percent from paper_positions where paper_pnl_percent is not null")]
        winners = [g for g in gains if g > 0]
        losers = [g for g in gains if g < 0]
        data.update(
            {
                "winners": len(winners),
                "losers": len(losers),
                "win_rate": round(len(winners) / (len(winners) + len(losers)), 4) if winners or losers else None,
                "average_gain": round(sum(winners) / len(winners), 2) if winners else None,
                "average_loss": round(sum(losers) / len(losers), 2) if losers else None,
                "median_gain": sorted(winners)[len(winners) // 2] if winners else None,
                "max_gain": max(winners) if winners else None,
                "max_drawdown": min(losers) if losers else None,
                "average_alert_delay": None,
                "average_time_to_25_percent": None,
                "average_time_to_50_percent": None,
                "average_time_to_minus_35_percent": None,
                "average_hold_time_if_exit_detected": None,
            }
        )
        return data

    def _count_raw_hype_posts(self) -> int:
        rows = self.conn.execute(
            """
            select social_posts.raw_text
            from social_posts
            left join parsed_alerts on parsed_alerts.social_post_id = social_posts.id
            where parsed_alerts.id is null
              and (social_posts.classification != 'new_trade_alert' or social_posts.classification is null)
            """
        ).fetchall()
        count = 0
        for row in rows:
            text = row["raw_text"].lower()
            if "potential" in text or "10x" in text or "1000%" in text:
                count += 1
        return count

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


def _alert_from_row(row) -> ParsedAlert:
    from app.models import OptionType

    option_type = OptionType(row["option_type"]) if row["option_type"] else None
    metadata = json.loads(row["metadata_json"] or "{}")
    return ParsedAlert(
        raw_alert_text=row["raw_alert_text"],
        ticker=row["ticker"],
        option_type=option_type,
        strike=row["strike"],
        expiration_date=row["expiration_date"],
        alert_price=row["alert_price"],
        alert_price_raw=row["alert_price_raw"],
        contract_symbol=row["contract_symbol"],
        side=row["side"],
        strategy=row["strategy"],
        time_horizon=row["time_horizon"],
        confidence_label=row["confidence_label"],
        hype_label=row["hype_label"],
        parse_confidence=row["parse_confidence"],
        needs_review=bool(row["needs_review"]),
        inferred_fields=tuple(metadata.get("inferred_fields", [])),
    )


def _entry_classification(metadata_json: str | None) -> str:
    metadata = json.loads(metadata_json or "{}")
    fields = set(metadata.get("inferred_fields", []))
    if "hype_potential" in fields:
        return "hype_potential"
    if "clean_entry" in fields:
        return "clean_entry"
    if "valid_contract_missing_price" in fields:
        return "valid_contract_missing_price"
    if "contract_parse_low_confidence" in fields:
        return "ambiguous_update"
    return "ambiguous_update"


def _source_quality_confidence(entry_classification: str) -> float:
    if entry_classification == "clean_entry":
        return 0.85
    if entry_classification == "valid_contract_missing_price":
        return 0.65
    if entry_classification == "hype_potential":
        return 0.4
    return 0.2


def _lifecycle_for_update(update_type: str) -> str:
    return {
        "add_update": "source_added",
        "hold_update": "source_holding",
        "trim_update": "source_trimmed",
        "source_exit_update": "source_exited",
        "full_exit": "source_exited",
        "claimed_result": "insufficient_data",
        "trade_update": "source_holding",
    }.get(update_type, "watching")
