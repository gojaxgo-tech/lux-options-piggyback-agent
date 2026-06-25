from app.database import Database


def test_database_initializes_required_tables(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")

    tables = {row["name"] for row in db.conn.execute("select name from sqlite_master where type='table'")}

    assert "social_posts" in tables
    assert "parsed_alerts" in tables
    assert "scores" in tables
    assert "claimed_performance" in tables
    assert "audit_events" in tables
    assert "control_state" in tables

