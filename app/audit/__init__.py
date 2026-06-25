from __future__ import annotations

import logging
from pathlib import Path


def configure_disk_logging(log_file: Path, level: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )


class AuditLogger:
    def __init__(self, database):
        self.database = database

    def log(self, event_type: str, message: str, severity: str = "info", metadata: dict | None = None) -> None:
        self.database.audit(event_type, message, severity, metadata)
        getattr(logging, severity if severity in ("debug", "info", "warning", "error") else "info")(message)
