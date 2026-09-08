from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import CATEGORY_NAMES, TagRecord

REQUIRED_COLUMNS = {"name", "category", "cn_name", "post_count"}
SQLITE_HEADER = b"SQLite format 3\x00"


def _contains_control_character(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def import_records(path: Path, *, minimum_records: int) -> list[TagRecord]:
    with path.open("rb") as handle:
        if handle.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
            raise ValueError("source is not a SQLite 3 database")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tags'"
        ).fetchone()
        if table is None:
            raise ValueError("SQLite database does not contain the tags table")
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(tags)")}
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"tags table is missing columns: {', '.join(sorted(missing))}")
        raw_records = connection.execute(
            "SELECT name, category, cn_name, post_count FROM tags ORDER BY name"
        )
        records: list[TagRecord] = []
        previous_name: str | None = None
        for index, row in enumerate(raw_records, start=1):
            name, category, cn_name, post_count = row
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"row {index} has an invalid name")
            if _contains_control_character(name):
                raise ValueError(f"tag {name!r} contains a control character")
            if name == previous_name:
                raise ValueError(f"duplicate tag name: {name}")
            if type(category) is not int or category not in CATEGORY_NAMES:
                raise ValueError(f"tag {name!r} has an invalid category")
            if not isinstance(cn_name, str) or not cn_name.strip():
                raise ValueError(f"tag {name!r} has an invalid Chinese translation")
            if _contains_control_character(cn_name):
                raise ValueError(f"tag {name!r} translation contains a control character")
            if type(post_count) is not int or post_count < 0:
                raise ValueError(f"tag {name!r} has an invalid post count")
            records.append(TagRecord(name, category, cn_name, post_count))
            previous_name = name
        if len(records) < minimum_records:
            raise ValueError(
                f"source contains {len(records)} records; expected at least {minimum_records}"
            )
        return records
    finally:
        connection.close()


def exclude_unchanged_translations(
    records: list[TagRecord],
) -> tuple[list[TagRecord], int]:
    filtered = [record for record in records if record.cn_name != record.name]
    return filtered, len(records) - len(filtered)
