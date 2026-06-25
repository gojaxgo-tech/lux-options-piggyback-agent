from app.database import Database
from app.models import AutonomyLevel


def test_control_state_commands(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    db.initialize_control_state(AutonomyLevel.MONITOR_ONLY, False)

    db.set_paused(True)
    assert db.get_control_state().paused

    db.set_paused(False)
    db.set_autonomy(AutonomyLevel.PAPER_TRADE)
    assert db.get_control_state().autonomy_level == AutonomyLevel.PAPER_TRADE

