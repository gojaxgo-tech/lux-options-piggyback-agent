from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Append a source post to Sniper Alert JSONL feed")
    parser.add_argument("--post-id", required=True)
    parser.add_argument("--url", default="")
    parser.add_argument("--text", required=True)
    parser.add_argument("--path", default=os.getenv("SOURCE_JSONL_PATH", "/app/input/source_posts.jsonl"))
    args = parser.parse_args()
    path = Path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_platform": "x",
        "source_account": "StockOptions888",
        "source_post_id": args.post_id,
        "source_url": args.url,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "raw_text": args.text,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    print(f"appended {args.post_id} to {path}")


if __name__ == "__main__":
    main()
