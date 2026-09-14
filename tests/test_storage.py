from __future__ import annotations

import pytest

from danbooru_tag_zh.models import Tag, WikiPage
from danbooru_tag_zh.storage import (
    open_database,
    open_wiki_database,
    set_state,
    validate_database,
    validate_wiki_database,
    write_tags,
    write_wiki_pages,
)


def tag(tag_id: int, category: int) -> Tag:
    return Tag(tag_id, f"tag_{tag_id}", category, 10, "created", "updated", False)


def test_writes_and_validates_all_categories(tmp_path):
    path = tmp_path / "tags.sqlite"
    connection = open_database(path)
    with connection:
        write_tags(connection, [tag(1, 0), tag(2, 1), tag(3, 3), tag(4, 4), tag(5, 5)])
    connection.close()

    stats = validate_database(path, minimum_records=5)

    assert stats["total"] == 5
    assert stats["by_category"] == {
        "artist": 1,
        "character": 1,
        "copyright": 1,
        "general": 1,
        "meta": 1,
    }


def test_rejects_database_below_minimum(tmp_path):
    path = tmp_path / "tags.sqlite"
    connection = open_database(path)
    connection.close()

    with pytest.raises(ValueError, match="expected at least"):
        validate_database(path, minimum_records=1)


def test_schema_has_no_translation_column(tmp_path):
    path = tmp_path / "tags.sqlite"
    connection = open_database(path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(tags)")}
    connection.close()

    assert "translation" not in columns
    assert "cn_name" not in columns


def test_wiki_database_retains_evidence_and_provenance(tmp_path):
    path = tmp_path / "wiki.sqlite"
    connection = open_wiki_database(path)
    page = WikiPage(7, "tag", "Definition.", ("别名",), "created", "updated", False, False)
    with connection:
        write_wiki_pages(
            connection,
            [(page, 9)],
            base_url="https://example.test",
            retrieved_at="retrieved",
        )
        set_state(connection, "scanned_total", 1)
        set_state(connection, "completed_at", "completed")
    row = connection.execute(
        "SELECT tag_id, other_names, source_url, retrieved_at FROM wiki_pages"
    ).fetchone()
    connection.close()

    assert row == (9, '["别名"]', "https://example.test/wiki_pages/7", "retrieved")
    assert validate_wiki_database(path)["matched_non_artist_tags"] == 1
