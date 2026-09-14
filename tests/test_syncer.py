from __future__ import annotations

from typing import ClassVar

import pytest

from danbooru_tag_zh.config import load_config
from danbooru_tag_zh.models import Tag
from danbooru_tag_zh.storage import get_state, open_database
from danbooru_tag_zh.syncer import sync_tags

from .helpers import make_root


def tag(tag_id: int, category: int) -> Tag:
    return Tag(tag_id, f"tag_{tag_id}", category, 10, "created", "updated", False)


class InterruptedClient:
    def __init__(self, _config) -> None:
        pass

    def fetch_page(self, before_id):
        if before_id is None:
            return [tag(5, 0), tag(4, 1), tag(3, 3), tag(2, 4), tag(1, 5)]
        raise RuntimeError("connection lost")


class ResumedClient:
    cursors: ClassVar[list[int | None]] = []

    def __init__(self, _config) -> None:
        pass

    def fetch_page(self, before_id):
        self.cursors.append(before_id)
        return []


def test_interrupted_sync_resumes_from_saved_cursor(tmp_path, monkeypatch):
    root = make_root(tmp_path, minimum_records=5)
    config = load_config(root)
    monkeypatch.setattr("danbooru_tag_zh.syncer.DanbooruClient", InterruptedClient)

    with pytest.raises(RuntimeError, match="connection lost"):
        sync_tags(root, config)

    destination = root / "data/state/tags.sqlite"
    partial = destination.with_suffix(".sqlite.partial")
    assert not destination.exists()
    connection = open_database(partial)
    assert get_state(connection, "next_before_id") == "1"
    connection.close()

    ResumedClient.cursors = []
    monkeypatch.setattr("danbooru_tag_zh.syncer.DanbooruClient", ResumedClient)
    result = sync_tags(root, config)

    assert ResumedClient.cursors == [1]
    assert result["total"] == 5
    assert destination.exists()
    assert not partial.exists()
