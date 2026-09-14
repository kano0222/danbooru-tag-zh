from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from .models import CATEGORY_NAMES, Tag, WikiPage

SCHEMA_VERSION = 1


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            category INTEGER NOT NULL CHECK (category IN (0, 1, 3, 4, 5)),
            post_count INTEGER NOT NULL CHECK (post_count >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_deprecated INTEGER NOT NULL CHECK (is_deprecated IN (0, 1))
        );
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS tags_category_idx ON tags(category);
        CREATE INDEX IF NOT EXISTS tags_post_count_idx ON tags(post_count);
        """
    )
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return connection


def write_tags(connection: sqlite3.Connection, tags: list[Tag]) -> None:
    connection.executemany(
        """
        INSERT INTO tags (
            id, name, category, post_count, created_at, updated_at, is_deprecated
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            category=excluded.category,
            post_count=excluded.post_count,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at,
            is_deprecated=excluded.is_deprecated
        """,
        [
            (
                tag.id,
                tag.name,
                tag.category,
                tag.post_count,
                tag.created_at,
                tag.updated_at,
                int(tag.is_deprecated),
            )
            for tag in tags
        ],
    )


def get_state(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else None


def set_state(connection: sqlite3.Connection, key: str, value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    connection.execute(
        "INSERT INTO sync_state(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, serialized),
    )


def database_stats(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        total = int(connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
        rows = connection.execute("SELECT category, COUNT(*) FROM tags GROUP BY category")
        counts = Counter({CATEGORY_NAMES[int(category)]: int(count) for category, count in rows})
        minimum_id, maximum_id = connection.execute("SELECT MIN(id), MAX(id) FROM tags").fetchone()
        deprecated = int(
            connection.execute("SELECT COUNT(*) FROM tags WHERE is_deprecated = 1").fetchone()[0]
        )
        return {
            "total": total,
            "by_category": dict(sorted(counts.items())),
            "deprecated": deprecated,
            "minimum_id": minimum_id,
            "maximum_id": maximum_id,
        }
    finally:
        connection.close()


def validate_database(path: Path, *, minimum_records: int) -> dict[str, object]:
    connection = sqlite3.connect(path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported database schema version: {version}")
        duplicate_names = int(
            connection.execute(
                "SELECT COUNT(*) FROM (SELECT name FROM tags GROUP BY name HAVING COUNT(*) > 1)"
            ).fetchone()[0]
        )
        if duplicate_names:
            raise ValueError("database contains duplicate tag names")
    finally:
        connection.close()
    stats = database_stats(path)
    total = stats["total"]
    categories = stats["by_category"]
    if not isinstance(total, int) or not isinstance(categories, dict):
        raise ValueError("database statistics are invalid")
    if total < minimum_records:
        raise ValueError(f"database contains {total} tags; expected at least {minimum_records}")
    present = set(categories)
    missing = set(CATEGORY_NAMES.values()) - present
    if missing:
        raise ValueError(f"database is missing categories: {', '.join(sorted(missing))}")
    return stats


def open_wiki_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS wiki_pages (
            id INTEGER PRIMARY KEY,
            tag_id INTEGER NOT NULL UNIQUE,
            title TEXT NOT NULL UNIQUE,
            body TEXT NOT NULL,
            other_names TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_locked INTEGER NOT NULL CHECK (is_locked IN (0, 1)),
            is_deleted INTEGER NOT NULL CHECK (is_deleted IN (0, 1)),
            source_url TEXT NOT NULL,
            retrieved_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS wiki_pages_updated_at_idx ON wiki_pages(updated_at);
        """
    )
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return connection


def write_wiki_pages(
    connection: sqlite3.Connection,
    pages: list[tuple[WikiPage, int]],
    *,
    base_url: str,
    retrieved_at: str,
) -> None:
    connection.executemany(
        """
        INSERT INTO wiki_pages (
            id, tag_id, title, body, other_names, created_at, updated_at,
            is_locked, is_deleted, source_url, retrieved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            tag_id=excluded.tag_id,
            title=excluded.title,
            body=excluded.body,
            other_names=excluded.other_names,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at,
            is_locked=excluded.is_locked,
            is_deleted=excluded.is_deleted,
            source_url=excluded.source_url,
            retrieved_at=excluded.retrieved_at
        """,
        [
            (
                page.id,
                tag_id,
                page.title,
                page.body,
                json.dumps(page.other_names, ensure_ascii=False, separators=(",", ":")),
                page.created_at,
                page.updated_at,
                int(page.is_locked),
                int(page.is_deleted),
                f"{base_url.rstrip('/')}/wiki_pages/{page.id}",
                retrieved_at,
            )
            for page, tag_id in pages
        ],
    )


def wiki_database_stats(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        matched = int(connection.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0])
        deleted = int(
            connection.execute("SELECT COUNT(*) FROM wiki_pages WHERE is_deleted = 1").fetchone()[0]
        )
        with_other_names = int(
            connection.execute(
                "SELECT COUNT(*) FROM wiki_pages WHERE other_names != '[]'"
            ).fetchone()[0]
        )
        scanned_raw = get_state(connection, "scanned_total")
        completed_raw = get_state(connection, "completed_at")
        return {
            "scanned_total": int(json.loads(scanned_raw)) if scanned_raw else 0,
            "matched_non_artist_tags": matched,
            "deleted": deleted,
            "with_other_names": with_other_names,
            "completed_at": json.loads(completed_raw) if completed_raw else None,
        }
    finally:
        connection.close()


def validate_wiki_database(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError("Wiki SQLite integrity check failed")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported Wiki database schema version: {version}")
        completed = get_state(connection, "completed_at")
        if completed is None:
            raise ValueError("Wiki sync is incomplete")
        invalid_other_names = 0
        for (value,) in connection.execute("SELECT other_names FROM wiki_pages"):
            try:
                names = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                invalid_other_names += 1
                continue
            if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
                invalid_other_names += 1
        if invalid_other_names:
            raise ValueError("Wiki database contains invalid other-name data")
    finally:
        connection.close()
    stats = wiki_database_stats(path)
    scanned_total = stats["scanned_total"]
    matched = stats["matched_non_artist_tags"]
    if not isinstance(scanned_total, int) or not isinstance(matched, int):
        raise ValueError("Wiki database statistics are invalid")
    if scanned_total <= 0 or matched <= 0:
        raise ValueError("Wiki database is empty")
    return stats
