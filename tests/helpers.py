from __future__ import annotations

import sqlite3
from pathlib import Path


def make_database(path: Path, rows: list[tuple[object, object, object, object]]) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE tags (name TEXT PRIMARY KEY, category INTEGER, "
            "cn_name TEXT, post_count INTEGER)"
        )
        connection.executemany("INSERT INTO tags VALUES (?, ?, ?, ?)", rows)
        connection.commit()
    finally:
        connection.close()
    return path
