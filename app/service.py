from __future__ import annotations

import logging
import time


def run_forever(agent, poll_interval_seconds: int) -> None:
    while True:
        try:
            count = agent.run_scan_cycle()
            logging.info("scan complete: %s new posts", count)
        except Exception:
            logging.exception("scan cycle failed")
        time.sleep(poll_interval_seconds)

