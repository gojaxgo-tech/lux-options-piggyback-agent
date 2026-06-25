from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.models import SocialPost


class SocialProvider(Protocol):
    def fetch_new_posts(self, seen_post_ids: set[str]) -> list[SocialPost]:
        ...


class FileSocialProvider:
    def __init__(self, path: str | None, source_platform: str, source_account: str):
        self.path = Path(path) if path else None
        self.source_platform = source_platform
        self.source_account = source_account

    def fetch_new_posts(self, seen_post_ids: set[str]) -> list[SocialPost]:
        if not self.path or not self.path.exists():
            return []
        posts: list[SocialPost] = []
        for index, line in enumerate(self.path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            post = self._parse_line(line, index)
            if post.source_post_id not in seen_post_ids:
                posts.append(post)
        return posts

    def _parse_line(self, line: str, index: int) -> SocialPost:
        try:
            payload = json.loads(line)
            posted_at = payload.get("posted_at")
            text = payload["text"]
            return SocialPost(
                source_platform=payload.get("source_platform", self.source_platform),
                source_account=payload.get("source_account", self.source_account).lstrip("@"),
                source_post_id=str(payload.get("source_post_id", payload.get("post_id", index))),
                source_url=payload.get("source_url") or payload.get("url"),
                posted_at=datetime.fromisoformat(posted_at) if posted_at else datetime.now(timezone.utc),
                raw_text=text,
                raw_json=json.dumps(payload),
            )
        except json.JSONDecodeError:
            return manual_post(line.strip(), self.source_platform, self.source_account, source_post_id=f"file-{index}")


class JsonlSourceProvider:
    def __init__(self, path: str | Path, default_platform: str, default_account: str, audit_logger=None):
        self.path = Path(path)
        self.default_platform = default_platform
        self.default_account = default_account
        self.audit_logger = audit_logger

    def fetch_new_posts(self, seen_post_ids: set[str]) -> list[SocialPost]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
            return []
        posts: list[SocialPost] = []
        for index, line in enumerate(self.path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                post = SocialPost(
                    source_platform=payload.get("source_platform", self.default_platform),
                    source_account=payload.get("source_account", self.default_account).lstrip("@"),
                    source_post_id=str(payload["source_post_id"]),
                    source_url=payload.get("source_url"),
                    posted_at=datetime.fromisoformat(payload["posted_at"]) if payload.get("posted_at") else datetime.now(timezone.utc),
                    raw_text=payload["raw_text"],
                    raw_json=json.dumps(payload),
                )
            except Exception as exc:
                if self.audit_logger:
                    self.audit_logger.log("jsonl_line_invalid", f"Invalid JSONL line {index}: {exc}", "warning")
                continue
            if post.source_post_id in seen_post_ids:
                if self.audit_logger:
                    self.audit_logger.log("jsonl_duplicate_skipped", f"Duplicate source post skipped: {post.source_post_id}")
                continue
            seen_post_ids.add(post.source_post_id)
            posts.append(post)
            if self.audit_logger:
                self.audit_logger.log("jsonl_line_ingested", f"JSONL source post ready for ingest: {post.source_post_id}")
        return posts


class XApiPlaceholderProvider:
    def __init__(self, bearer_token: str):
        self.bearer_token = bearer_token

    def fetch_new_posts(self, seen_post_ids: set[str]) -> list[SocialPost]:
        return []


def manual_post(text: str, source_platform: str, source_account: str, source_post_id: str | None = None) -> SocialPost:
    stable_id = source_post_id or "manual-" + hashlib.sha256(text.encode()).hexdigest()[:16]
    return SocialPost(
        source_platform=source_platform,
        source_account=source_account.lstrip("@"),
        source_post_id=stable_id,
        source_url=None,
        posted_at=datetime.now(timezone.utc),
        raw_text=text,
    )
