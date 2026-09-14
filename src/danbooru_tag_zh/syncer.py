from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .danbooru_client import DanbooruClient
from .storage import get_state, open_database, set_state, validate_database, write_tags

LOGGER = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sync_tags(root: Path, config: Config, *, restart: bool = False) -> dict[str, object]:
    destination = root / config.danbooru.database_path
    partial = destination.with_suffix(destination.suffix + ".partial")
    if restart:
        partial.unlink(missing_ok=True)
    connection = open_database(partial)
    try:
        stored_query = get_state(connection, "query")
        query = {
            "base_url": config.danbooru.base_url.rstrip("/"),
            "minimum_post_count": config.danbooru.minimum_post_count,
            "page_size": config.danbooru.page_size,
        }
        if stored_query is not None and json.loads(stored_query) != query:
            raise ValueError("partial database uses different sync settings; run with --restart")
        set_state(connection, "query", query)
        raw_cursor = get_state(connection, "next_before_id")
        before_id = int(json.loads(raw_cursor)) if raw_cursor is not None else None
        client = DanbooruClient(config.danbooru)
        page_number = 0
        while True:
            tags = client.fetch_page(before_id)
            page_number += 1
            if not tags:
                break
            write_tags(connection, tags)
            before_id = tags[-1].id
            set_state(connection, "next_before_id", before_id)
            set_state(connection, "last_page_at", _now())
            connection.commit()
            count = int(connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
            LOGGER.info("page %d: stored %d tags; next cursor b%d", page_number, count, before_id)
        set_state(connection, "completed_at", _now())
        connection.commit()
    finally:
        connection.close()

    stats = validate_database(partial, minimum_records=config.validation.minimum_records)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(partial, destination)
    partial.with_name(partial.name + "-wal").unlink(missing_ok=True)
    partial.with_name(partial.name + "-shm").unlink(missing_ok=True)
    return {"database": str(destination), **stats}
