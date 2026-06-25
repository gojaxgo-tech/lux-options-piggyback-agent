from datetime import date

from app.models import AutonomyLevel, ControlState, ScoreDecision
from app.parser import parse_first_alert
from app.scoring import EnterabilityScorer


def test_kill_switch_blocks_scoring_action():
    alert = parse_first_alert("$HNI 45 CALL 7/17 avg .75", today=date(2026, 6, 25))
    state = ControlState(paused=False, kill_switch=True, autonomy_level=AutonomyLevel.MONITOR_ONLY)

    score = EnterabilityScorer().score(alert, None, state)

    assert score.decision == ScoreDecision.BLOCKED_BY_KILL_SWITCH
    assert score.reason_codes == ("kill_switch_active",)

