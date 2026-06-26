from __future__ import annotations

import json

from app.classifier import classify_text
from app.parser import parse_alerts
from app.trades import canonical_trade_id


def backfill_rubric(database, audit_logger=None, dry_run: bool = False) -> dict:
    result = {
        "dry_run": dry_run,
        "social_posts_reviewed": 0,
        "social_posts_reclassified": 0,
        "parsed_alerts_reviewed": 0,
        "parsed_alerts_repaired": 0,
        "canonical_trades_rebuilt": 0,
        "paper_positions_linked": 0,
    }
    posts = database.conn.execute(
        "select id, raw_text, classification, classification_confidence from social_posts order by id"
    ).fetchall()
    for post in posts:
        result["social_posts_reviewed"] += 1
        classification = classify_text(post["raw_text"])
        if post["classification"] != classification.classification.value or post["classification_confidence"] != classification.confidence:
            result["social_posts_reclassified"] += 1
            if not dry_run:
                database.conn.execute(
                    """
                    update social_posts
                    set classification = ?, classification_confidence = ?, processed = 1
                    where id = ?
                    """,
                    (classification.classification.value, classification.confidence, post["id"]),
                )

    parsed_rows = database.conn.execute(
        """
        select parsed_alerts.*, social_posts.raw_text as source_raw_text
        from parsed_alerts
        join social_posts on social_posts.id = parsed_alerts.social_post_id
        order by parsed_alerts.id
        """
    ).fetchall()
    for row in parsed_rows:
        result["parsed_alerts_reviewed"] += 1
        repaired = _matching_alert(row)
        if repaired is None:
            repaired = parse_alerts(row["source_raw_text"])[0]
        trade_id = canonical_trade_id(repaired)
        entry_classification = _entry_classification(repaired.inferred_fields)
        metadata = json.dumps({"inferred_fields": list(repaired.inferred_fields)})
        changed = (
            row["ticker"] != repaired.ticker
            or row["option_type"] != (repaired.option_type.value if repaired.option_type else None)
            or row["strike"] != repaired.strike
            or row["expiration_date"] != repaired.expiration_date
            or row["alert_price"] != repaired.alert_price
            or row["metadata_json"] != metadata
            or row["canonical_trade_id"] != trade_id
            or row["entry_classification"] != entry_classification
        )
        if changed:
            result["parsed_alerts_repaired"] += 1
            if not dry_run:
                database.conn.execute(
                    """
                    update parsed_alerts
                    set ticker = ?,
                        option_type = ?,
                        strike = ?,
                        expiration_date = ?,
                        alert_price = ?,
                        alert_price_raw = ?,
                        contract_symbol = ?,
                        side = ?,
                        strategy = ?,
                        time_horizon = ?,
                        confidence_label = ?,
                        hype_label = ?,
                        parse_confidence = ?,
                        needs_review = ?,
                        metadata_json = ?,
                        canonical_trade_id = ?,
                        entry_classification = ?
                    where id = ?
                    """,
                    (
                        repaired.ticker,
                        repaired.option_type.value if repaired.option_type else None,
                        repaired.strike,
                        repaired.expiration_date,
                        repaired.alert_price,
                        repaired.alert_price_raw,
                        repaired.contract_symbol,
                        repaired.side,
                        repaired.strategy,
                        repaired.time_horizon,
                        repaired.confidence_label,
                        repaired.hype_label,
                        repaired.parse_confidence,
                        1 if repaired.needs_review else 0,
                        metadata,
                        trade_id,
                        entry_classification,
                        row["id"],
                    ),
                )

    if not dry_run:
        database.conn.execute("delete from trades")
        trade_rows = database.conn.execute(
            """
            select *
            from parsed_alerts
            where canonical_trade_id is not null
            order by id
            """
        ).fetchall()
        grouped: dict[str, list] = {}
        for row in trade_rows:
            grouped.setdefault(row["canonical_trade_id"], []).append(row)
        for trade_id, rows in grouped.items():
            first = rows[0]
            latest = rows[-1]
            label = _best_label(row["entry_classification"] for row in rows)
            lifecycle = _trade_lifecycle(database, trade_id, label)
            now = latest["created_at"]
            database.conn.execute(
                """
                insert into trades
                (canonical_trade_id, ticker, option_type, strike, expiration_date, lifecycle_state,
                 first_alert_id, latest_alert_id, classification_label, source_quality_confidence, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    latest["ticker"],
                    latest["option_type"],
                    latest["strike"],
                    latest["expiration_date"],
                    lifecycle,
                    first["id"],
                    latest["id"],
                    label,
                    _source_quality_confidence(label),
                    first["created_at"],
                    now,
                ),
            )
        result["canonical_trades_rebuilt"] = len(grouped)
        cursor = database.conn.execute(
            """
            update paper_positions
            set canonical_trade_id = (
                select canonical_trade_id
                from parsed_alerts
                where parsed_alerts.id = paper_positions.parsed_alert_id
            )
            where parsed_alert_id in (select id from parsed_alerts)
            """
        )
        result["paper_positions_linked"] = cursor.rowcount
        database.conn.commit()
        if audit_logger:
            audit_logger.log("repair_backfill_rubric_completed", "Rubric backfill repair completed", metadata=result)
    elif audit_logger:
        audit_logger.log("repair_backfill_rubric_dry_run", "Rubric backfill dry run completed", metadata=result)
    return result


def _matching_alert(row):
    for alert in parse_alerts(row["source_raw_text"]):
        if (
            alert.ticker == row["ticker"]
            and (alert.option_type.value if alert.option_type else None) == row["option_type"]
            and alert.strike == row["strike"]
            and alert.expiration_date == row["expiration_date"]
        ):
            return alert
    return None


def _entry_classification(inferred_fields: tuple[str, ...]) -> str:
    fields = set(inferred_fields)
    if "hype_potential" in fields:
        return "hype_potential"
    if "clean_entry" in fields:
        return "clean_entry"
    if "valid_contract_missing_price" in fields:
        return "valid_contract_missing_price"
    return "ambiguous_update"


def _best_label(labels) -> str:
    priority = {
        "clean_entry": 4,
        "valid_contract_missing_price": 3,
        "hype_potential": 2,
        "ambiguous_update": 1,
    }
    return max(labels, key=lambda label: priority.get(label, 0), default="ambiguous_update")


def _trade_lifecycle(database, trade_id: str, label: str) -> str:
    paper = database.conn.execute(
        "select status from paper_positions where canonical_trade_id = ? order by id desc limit 1",
        (trade_id,),
    ).fetchone()
    if paper:
        if paper["status"] == "closed":
            return "paper_closed"
        if paper["status"] == "source_exit_detected":
            return "source_exited"
        return "paper_open"
    missing_quote = database.conn.execute(
        """
        select scores.id
        from scores
        join parsed_alerts on parsed_alerts.id = scores.parsed_alert_id
        where parsed_alerts.canonical_trade_id = ?
          and scores.reason_codes like '%missing_quote%'
        limit 1
        """,
        (trade_id,),
    ).fetchone()
    if missing_quote or label in ("valid_contract_missing_price", "hype_potential", "ambiguous_update"):
        return "insufficient_data"
    return "new_alert"


def _source_quality_confidence(label: str) -> float:
    return {
        "clean_entry": 0.85,
        "valid_contract_missing_price": 0.65,
        "hype_potential": 0.4,
        "ambiguous_update": 0.2,
    }.get(label, 0.2)
