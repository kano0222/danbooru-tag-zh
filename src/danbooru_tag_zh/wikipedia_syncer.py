from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

from .config import Config
from .storage import get_state, set_state, validate_database, validate_wiki_database
from .wikipedia_client import WikipediaClient

LOGGER = logging.getLogger(__name__)
BATCH_SIZE = 50
SUPPORTED_CATEGORIES = (3, 4)
RELATIONS = ("subject", "related", "unknown")
CLASSIFIER_VERSION = 1
CONTEXT_RADIUS = 120
WIKIPEDIA_LINK = re.compile(
    r"https?://([a-z][a-z0-9-]{1,11})\.wikipedia\.org/wiki/([^\s\]\[<>\"'}]+)",
    re.IGNORECASE,
)
RELATED_CONTEXT = re.compile(
    r"\b(?:based on|adapted from|inspired by|character from|sequel to|prequel to|"
    r"spin[ -]?off of|part of|original novel|source material)\b",
    re.IGNORECASE,
)
TRAILING_QUALIFIER = re.compile(r"\s*\([^()]{1,80}\)\s*$")
NON_ALPHANUMERIC = re.compile(r"[^\w]+", re.UNICODE)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def extract_wikipedia_links(body: str) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in WIKIPEDIA_LINK.finditer(body):
        language = match.group(1).lower()
        if language == "jp":
            continue
        encoded_title = match.group(2).rstrip(".,;:")
        title = unquote(encoded_title).split("#", 1)[0].replace("_", " ").strip()
        key = (language, title.casefold())
        if not title or key in seen:
            continue
        seen.add(key)
        result.append((language, title, match.group(0)))
    return result


def _identity_key(value: str) -> str:
    return NON_ALPHANUMERIC.sub("", value.replace("_", " ").casefold())


def _without_qualifier(value: str) -> str:
    return TRAILING_QUALIFIER.sub("", value).strip()


def _matches_identity(title: str, identities: tuple[str, ...]) -> bool:
    title_key = _identity_key(title)
    if title_key and any(title_key == _identity_key(identity) for identity in identities):
        return True
    title_base = _without_qualifier(title)
    if title_base == title:
        return False
    base_key = _identity_key(title_base)
    return bool(base_key) and any(
        _without_qualifier(identity) != identity
        and base_key == _identity_key(_without_qualifier(identity))
        for identity in identities
    )


def _link_context(body: str, url: str) -> str:
    position = body.find(url)
    if position < 0:
        return ""
    start = max(0, position - CONTEXT_RADIUS)
    end = min(len(body), position + len(url) + CONTEXT_RADIUS)
    return " ".join(body[start:end].split())


def classify_wikipedia_link(title: str, context: str, identities: tuple[str, ...]) -> str:
    if RELATED_CONTEXT.search(context):
        return "related"
    if _matches_identity(title, identities):
        return "subject"
    return "unknown"


def open_wikipedia_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS wikipedia_sources (
            tag_id INTEGER NOT NULL,
            source_language TEXT NOT NULL,
            source_title TEXT NOT NULL,
            source_url TEXT NOT NULL,
            relation TEXT NOT NULL CHECK (relation IN ('subject', 'related', 'unknown')),
            context TEXT NOT NULL,
            zh_title TEXT,
            checked_at TEXT,
            PRIMARY KEY (tag_id, source_language, source_title)
        );
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS wikipedia_sources_tag_idx ON wikipedia_sources(tag_id);
        CREATE INDEX IF NOT EXISTS wikipedia_sources_relation_idx
            ON wikipedia_sources(relation);
        """
    )
    connection.execute("PRAGMA user_version=2")
    return connection


def wikipedia_database_stats(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        sources = int(connection.execute("SELECT COUNT(*) FROM wikipedia_sources").fetchone()[0])
        checked = int(
            connection.execute(
                "SELECT COUNT(*) FROM wikipedia_sources WHERE checked_at IS NOT NULL"
            ).fetchone()[0]
        )
        resolved = int(
            connection.execute(
                "SELECT COUNT(*) FROM wikipedia_sources WHERE zh_title IS NOT NULL"
            ).fetchone()[0]
        )
        tags = int(
            connection.execute(
                "SELECT COUNT(DISTINCT tag_id) FROM wikipedia_sources "
                "WHERE zh_title IS NOT NULL AND relation='subject'"
            ).fetchone()[0]
        )
        relations = {
            str(relation): int(count)
            for relation, count in connection.execute(
                "SELECT relation, COUNT(*) FROM wikipedia_sources GROUP BY relation"
            )
        }
        completed = get_state(connection, "completed_at")
        return {
            "sources": sources,
            "checked": checked,
            "resolved": resolved,
            "tags_with_zh_title": tags,
            "by_relation": {relation: relations.get(relation, 0) for relation in RELATIONS},
            "completed_at": json.loads(completed) if completed else None,
        }
    finally:
        connection.close()


def validate_wikipedia_database(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError("Wikipedia SQLite integrity check failed")
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != 2:
            raise ValueError("unsupported Wikipedia database schema version")
        if get_state(connection, "completed_at") is None:
            raise ValueError("Wikipedia sync is incomplete")
        unresolved = int(
            connection.execute(
                "SELECT COUNT(*) FROM wikipedia_sources WHERE checked_at IS NULL"
            ).fetchone()[0]
        )
        if unresolved:
            raise ValueError("Wikipedia sync contains unchecked sources")
        invalid_relations = int(
            connection.execute(
                "SELECT COUNT(*) FROM wikipedia_sources "
                "WHERE relation NOT IN ('subject', 'related', 'unknown')"
            ).fetchone()[0]
        )
        if invalid_relations:
            raise ValueError("Wikipedia sync contains invalid relations")
    finally:
        connection.close()
    return wikipedia_database_stats(path)


def _source_rows(
    tags_path: Path, wiki_path: Path
) -> tuple[list[tuple[int, str, str, str, str, str]], dict[int, tuple[str, ...]]]:
    tags = sqlite3.connect(f"{tags_path.resolve().as_uri()}?mode=ro", uri=True)
    wiki = sqlite3.connect(f"{wiki_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        targets = {
            int(tag_id): str(name)
            for tag_id, name in tags.execute(
                "SELECT id, name FROM tags WHERE category IN (?, ?)", SUPPORTED_CATEGORIES
            )
        }
        rows: list[tuple[int, str, str, str, str, str]] = []
        identities_by_tag: dict[int, tuple[str, ...]] = {}
        for tag_id, body, raw_other_names in wiki.execute(
            "SELECT tag_id, body, other_names FROM wiki_pages"
        ):
            if int(tag_id) not in targets:
                continue
            other_names = json.loads(str(raw_other_names))
            if not isinstance(other_names, list):
                raise ValueError(f"Wiki aliases are invalid for tag {tag_id}")
            identities = (
                targets[int(tag_id)],
                *(str(value) for value in other_names if isinstance(value, str)),
            )
            identities_by_tag[int(tag_id)] = identities
            for language, title, url in extract_wikipedia_links(str(body)):
                context = _link_context(str(body), url)
                relation = classify_wikipedia_link(title, context, identities)
                rows.append((int(tag_id), language, title, url, relation, context))
        return rows, identities_by_tag
    finally:
        tags.close()
        wiki.close()


def sync_wikipedia(root: Path, config: Config, *, restart: bool = False) -> dict[str, object]:
    tags_path = root / config.danbooru.database_path
    wiki_path = root / config.wiki.database_path
    validate_database(tags_path, minimum_records=config.validation.minimum_records)
    validate_wiki_database(wiki_path)
    destination = root / config.wikipedia.database_path
    partial = destination.with_suffix(destination.suffix + ".partial")
    if restart:
        partial.unlink(missing_ok=True)
    snapshot = {
        "wiki_sha256": _sha256(wiki_path),
        "categories": list(SUPPORTED_CATEGORIES),
        "classifier_version": CLASSIFIER_VERSION,
    }
    connection = open_wikipedia_database(partial)
    try:
        stored_snapshot = get_state(connection, "source")
        if stored_snapshot is not None and json.loads(stored_snapshot) != snapshot:
            raise ValueError(
                "partial Wikipedia database uses different Wiki data; run with --restart"
            )
        set_state(connection, "source", snapshot)
        source_rows, identities_by_tag = _source_rows(tags_path, wiki_path)
        with connection:
            connection.executemany(
                "INSERT OR IGNORE INTO wikipedia_sources "
                "(tag_id, source_language, source_title, source_url, relation, context) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                source_rows,
            )
            checked_at = _now()
            connection.execute(
                "UPDATE wikipedia_sources SET checked_at=? "
                "WHERE relation='related' AND checked_at IS NULL",
                (checked_at,),
            )
            connection.execute(
                "UPDATE wikipedia_sources SET zh_title=source_title, checked_at=? "
                "WHERE source_language='zh' AND relation!='related' AND checked_at IS NULL",
                (checked_at,),
            )

        client = WikipediaClient(config.wikipedia)
        languages = [
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT source_language FROM wikipedia_sources "
                "WHERE source_language != 'zh' AND relation!='related' "
                "AND checked_at IS NULL ORDER BY source_language"
            )
        ]
        batches = 0
        for language in languages:
            titles = [
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT source_title FROM wikipedia_sources "
                    "WHERE source_language=? AND relation!='related' "
                    "AND checked_at IS NULL ORDER BY source_title",
                    (language,),
                )
            ]
            for start in range(0, len(titles), BATCH_SIZE):
                batch = titles[start : start + BATCH_SIZE]
                resolved = client.fetch_zh_titles(language, batch)
                checked_at = _now()
                updates: list[tuple[str | None, str, str, int, str, str]] = []
                for title in batch:
                    zh_title = resolved.get(title)
                    linked_rows = connection.execute(
                        "SELECT tag_id, relation FROM wikipedia_sources "
                        "WHERE source_language=? AND source_title=? AND checked_at IS NULL",
                        (language, title),
                    ).fetchall()
                    for tag_id, relation in linked_rows:
                        updated_relation = str(relation)
                        if (
                            updated_relation == "unknown"
                            and zh_title is not None
                            and _matches_identity(zh_title, identities_by_tag[int(tag_id)])
                        ):
                            updated_relation = "subject"
                        updates.append(
                            (
                                zh_title,
                                checked_at,
                                updated_relation,
                                int(tag_id),
                                language,
                                title,
                            )
                        )
                with connection:
                    connection.executemany(
                        "UPDATE wikipedia_sources SET zh_title=?, checked_at=?, relation=? "
                        "WHERE tag_id=? AND source_language=? AND source_title=?",
                        updates,
                    )
                batches += 1
                LOGGER.info(
                    "Wikipedia batch %d: %s %d/%d",
                    batches,
                    language,
                    min(start + BATCH_SIZE, len(titles)),
                    len(titles),
                )
        set_state(connection, "completed_at", _now())
        connection.commit()
    finally:
        connection.close()

    stats = validate_wikipedia_database(partial)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(partial, destination)
    partial.with_name(partial.name + "-wal").unlink(missing_ok=True)
    partial.with_name(partial.name + "-shm").unlink(missing_ok=True)
    return {"database": str(destination), **stats}
