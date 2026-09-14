from __future__ import annotations

import io
import json
from email.message import Message

import pytest

from danbooru_tag_zh.config import DanbooruConfig, WikiConfig
from danbooru_tag_zh.danbooru_client import (
    DanbooruClient,
    DanbooruWikiClient,
    build_tags_url,
    build_wiki_pages_url,
    parse_tag,
)


class Response(io.BytesIO):
    def __init__(self, value: object) -> None:
        super().__init__(json.dumps(value).encode())
        self.headers = Message()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def config() -> DanbooruConfig:
    return DanbooruConfig("https://example.test", 10, 1000, 0, 10, 1, "tags.sqlite")


def wiki_config() -> WikiConfig:
    return WikiConfig(1000, 0, 10, 1, "wiki.sqlite")


def raw_tag(tag_id: int, *, category: int = 0) -> dict[str, object]:
    return {
        "id": tag_id,
        "name": f"tag_{tag_id}",
        "category": category,
        "post_count": 10,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "is_deprecated": False,
    }


def raw_wiki_page(page_id: int) -> dict[str, object]:
    return {
        "id": page_id,
        "title": f"tag_{page_id}",
        "body": "Definition.",
        "other_names": [f"other_{page_id}"],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "is_locked": False,
        "is_deleted": False,
    }


def test_build_tags_url_contains_filter_order_and_cursor():
    url = build_tags_url(config(), 123)

    assert "limit=1000" in url
    assert "search%5Bpost_count%5D=10.." in url
    assert "search%5Border%5D=id_desc" in url
    assert "page=b123" in url


def test_fetch_page_parses_descending_tags():
    client = DanbooruClient(
        config(), open_url=lambda _request, _timeout: Response([raw_tag(3), raw_tag(2)])
    )

    assert [tag.id for tag in client.fetch_page(4)] == [3, 2]


def test_rejects_unknown_category():
    with pytest.raises(ValueError, match="category"):
        parse_tag(raw_tag(1, category=2))


def test_rejects_cursor_that_does_not_advance():
    client = DanbooruClient(config(), open_url=lambda _request, _timeout: Response([raw_tag(4)]))

    with pytest.raises(ValueError, match="did not advance"):
        client.fetch_page(4)


def test_wiki_url_always_uses_id_cursor():
    url = build_wiki_pages_url("https://example.test/", wiki_config(), 2**31 - 1)

    assert url == "https://example.test/wiki_pages.json?limit=1000&page=b2147483647"


def test_fetch_wiki_page_parses_descending_pages():
    client = DanbooruWikiClient(
        "https://example.test",
        wiki_config(),
        open_url=lambda _request, _timeout: Response([raw_wiki_page(3), raw_wiki_page(2)]),
    )

    pages = client.fetch_page(4)

    assert [page.id for page in pages] == [3, 2]
    assert pages[0].other_names == ("other_3",)
