from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .danbooru_client import DanbooruWikiClient
from .storage import (
    get_state,
    open_wiki_database,
    set_state,
    validate_database,
    validate_wiki_database,
    write_wiki_pages,
)

LOGGER = logging.getLogger(__name__)
INITIAL_CURSOR = 2**31 - 1


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _target_tags(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return {
            str(name): int(tag_id)
            for tag_id, name in connection.execute("SELECT id, name FROM tags WHERE category != 1")
        }
    finally:
        connection.close()


def sync_wiki(root: Path, config: Config, *, restart: bool = False) -> dict[str, object]:
    tags_path = root / config.danbooru.database_path
    validate_database(tags_path, minimum_records=config.validation.minimum_records)
    targets = _target_tags(tags_path)
    destination = root / config.wiki.database_path
    partial = destination.with_suffix(destination.suffix + ".partial")
    if restart:
        partial.unlink(missing_ok=True)
    snapshot = {
        "base_url": config.danbooru.base_url.rstrip("/"),
        "page_size": config.wiki.page_size,
        "tags_sha256": _sha256(tags_path),
    }
    connection = open_wiki_database(partial)
    try:
        stored_snapshot = get_state(connection, "source")
        if stored_snapshot is not None and json.loads(stored_snapshot) != snapshot:
            raise ValueError(
                "partial Wiki database uses a different tag snapshot; run with --restart"
            )
        set_state(connection, "source", snapshot)
        raw_cursor = get_state(connection, "next_before_id")
        before_id = int(json.loads(raw_cursor)) if raw_cursor else INITIAL_CURSOR
        raw_scanned = get_state(connection, "scanned_total")
        scanned_total = int(json.loads(raw_scanned)) if raw_scanned else 0
        client = DanbooruWikiClient(config.danbooru.base_url, config.wiki)
        page_number = 0
        while True:
            pages = client.fetch_page(before_id)
            page_number += 1
            if not pages:
                break
            retrieved_at = _now()
            matched = [(page, targets[page.title]) for page in pages if page.title in targets]
            write_wiki_pages(
                connection,
                matched,
                base_url=config.danbooru.base_url,
                retrieved_at=retrieved_at,
            )
            scanned_total += len(pages)
            before_id = pages[-1].id
            set_state(connection, "next_before_id", before_id)
            set_state(connection, "scanned_total", scanned_total)
            set_state(connection, "last_page_at", retrieved_at)
            connection.commit()
            matched_total = int(connection.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0])
            LOGGER.info(
                "page %d: scanned %d Wiki pages; matched %d tags; next cursor b%d",
                page_number,
                scanned_total,
                matched_total,
                before_id,
            )
        set_state(connection, "completed_at", _now())
        connection.commit()
    finally:
        connection.close()

    stats = validate_wiki_database(partial)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(partial, destination)
    partial.with_name(partial.name + "-wal").unlink(missing_ok=True)
    partial.with_name(partial.name + "-shm").unlink(missing_ok=True)
    return {"database": str(destination), **stats}
