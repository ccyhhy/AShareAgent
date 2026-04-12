from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.database.slim_maintenance import backup_database, rebuild_database_with_compaction


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a compact offline copy of ashare_agent.db without modifying the source DB."
    )
    parser.add_argument(
        "--source",
        default="data/ashare_agent.db",
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--target",
        default="data/ashare_agent.slim.db",
        help="Path to the rebuilt compact SQLite database.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a timestamped backup copy of the source database before rebuilding.",
    )
    args = parser.parse_args()

    source = Path(args.source)
    target = Path(args.target)

    if not source.exists():
        raise SystemExit(f"Source database does not exist: {source}")

    result: dict[str, object] = {}
    if args.backup:
        backup_path = backup_database(source)
        result["backup_path"] = str(backup_path)

    summary = rebuild_database_with_compaction(source_db=source, target_db=target)
    result["summary"] = summary
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
