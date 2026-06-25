from datetime import datetime, timezone

from app.classifier import classify_text
from app.database import Database
from app.models import SocialPost
from app.parser import parse_alerts, parse_trade_update


def test_claimed_performance_is_stored_separately(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    alert_post = SocialPost("x", "StockOptions888", "1", "$HNI 45 CALL 7/17 avg .75", datetime.now(timezone.utc))
    alert_id, _ = db.save_social_post(alert_post)
    alert = parse_alerts(alert_post.raw_text)[0]
    parsed_id = db.save_parsed_alert(alert_id, alert)

    claim_post = SocialPost("x", "StockOptions888", "2", "Winner sold for 300%", datetime.now(timezone.utc))
    claim_post_id, _ = db.save_social_post(claim_post)
    update = parse_trade_update(claim_post.raw_text)
    db.save_trade_update(claim_post_id, update)

    claim = db.conn.execute("select verification_status from claimed_performance").fetchone()
    assert parsed_id is not None
    assert claim["verification_status"] == "unverified"

