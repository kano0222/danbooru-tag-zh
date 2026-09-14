from __future__ import annotations

from typing import ClassVar

from danbooru_tag_zh.config import load_config
from danbooru_tag_zh.models import Tag, WikiPage
from danbooru_tag_zh.storage import open_database, write_tags
from danbooru_tag_zh.wiki_syncer import INITIAL_CURSOR, sync_wiki

from .helpers import make_root


class WikiClient:
    cursors: ClassVar[list[int]] = []

    def __init__(self, _base_url, _config) -> None:
        pass

    def fetch_page(self, before_id):
        self.cursors.append(before_id)
        if before_id == INITIAL_CURSOR:
            return [
                WikiPage(20, "general", "Body", (), "created", "updated", False, False),
                WikiPage(19, "artist", "Body", (), "created", "updated", False, False),
            ]
        return []


def test_wiki_sync_only_stores_non_artist_tag_matches(tmp_path, monkeypatch):
    root = make_root(tmp_path, minimum_records=5)
    config = load_config(root)
    tag_path = root / config.danbooru.database_path
    connection = open_database(tag_path)
    with connection:
        write_tags(
            connection,
            [
                Tag(1, "general", 0, 10, "created", "updated", False),
                Tag(2, "artist", 1, 10, "created", "updated", False),
                Tag(3, "copyright", 3, 10, "created", "updated", False),
                Tag(4, "character", 4, 10, "created", "updated", False),
                Tag(5, "meta", 5, 10, "created", "updated", False),
            ],
        )
    connection.close()
    WikiClient.cursors = []
    monkeypatch.setattr("danbooru_tag_zh.wiki_syncer.DanbooruWikiClient", WikiClient)

    result = sync_wiki(root, config)

    assert WikiClient.cursors == [INITIAL_CURSOR, 19]
    assert result["scanned_total"] == 2
    assert result["matched_non_artist_tags"] == 1
