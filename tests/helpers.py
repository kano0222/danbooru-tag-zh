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


def make_root(tmp_path: Path, *, minimum_records: int = 1) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/default.toml").write_text(
        f"""
[danbooru]
base_url = "https://example.test"
minimum_post_count = 10
page_size = 1000
request_interval_seconds = 0.0
timeout_seconds = 10.0
maximum_retries = 1
database_path = "data/state/tags.sqlite"
[wiki]
page_size = 1000
request_interval_seconds = 0.0
timeout_seconds = 10.0
maximum_retries = 1
database_path = "data/state/wiki.sqlite"
[wikipedia]
request_interval_seconds = 0.0
timeout_seconds = 10.0
maximum_retries = 1
database_path = "data/state/wikipedia.sqlite"
[ffdkj]
repository = "owner/repo"
branch = "main"
database_path = "tag.sqlite"
lock_path = "data/sources/ffdkj.lock.json"
timeout_seconds = 10.0
maximum_download_bytes = 1048576
[artifacts]
directory = "artifacts"
[translation]
database_path = "data/state/translations.sqlite"
review_report_path = "reports/multiple-candidates.json"
manual_decisions_path = "data/manual/translations.json"
[validation]
minimum_records = {minimum_records}
maximum_record_decrease_ratio = 0.05
maximum_translation_change_ratio = 0.10
""".strip(),
        encoding="utf-8",
    )
    return tmp_path
