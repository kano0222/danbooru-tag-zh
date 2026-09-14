from __future__ import annotations

from danbooru_tag_zh.wikipedia_client import build_langlinks_url, parse_langlinks


def test_langlinks_url_requests_chinese_titles_in_one_batch():
    url = build_langlinks_url("en", ["Puella Magi Madoka Magica", "Touhou Project"])

    assert url.startswith("https://en.wikipedia.org/w/api.php?")
    assert "lllang=zh" in url
    assert "lllimit=max" in url
    assert "titles=Puella+Magi+Madoka+Magica%7CTouhou+Project" in url


def test_parse_langlinks_follows_normalized_and_redirected_titles():
    payload = {
        "query": {
            "normalized": [{"from": "madoka", "to": "Madoka"}],
            "redirects": [{"from": "Madoka", "to": "Puella Magi Madoka Magica"}],
            "pages": [
                {
                    "title": "Puella Magi Madoka Magica",
                    "langlinks": [{"lang": "zh", "title": "魔法少女小圆"}],
                }
            ],
        }
    }

    assert parse_langlinks(payload, ["madoka"]) == {"madoka": "魔法少女小圆"}
