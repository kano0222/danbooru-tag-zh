from __future__ import annotations

import sqlite3

from danbooru_tag_zh.config import load_config
from danbooru_tag_zh.models import Tag, WikiPage
from danbooru_tag_zh.storage import (
    open_database,
    open_wiki_database,
    set_state,
    write_tags,
    write_wiki_pages,
)
from danbooru_tag_zh.wikipedia_syncer import (
    classify_wikipedia_link,
    extract_wikipedia_links,
    sync_wikipedia,
)

from .helpers import make_root


def test_extract_wikipedia_links_decodes_titles_and_removes_duplicates():
    body = """
    * https://en.wikipedia.org/wiki/Puella_Magi_Madoka_Magica
    * https://en.wikipedia.org/wiki/Puella_Magi_Madoka_Magica#Characters
    * https://ja.wikipedia.org/wiki/%E9%AD%94%E6%B3%95%E5%B0%91%E5%A5%B3%E3%81%BE%E3%81%A9%E3%81%8B%E2%98%86%E3%83%9E%E3%82%AE%E3%82%AB
    """

    assert extract_wikipedia_links(body) == [
        (
            "en",
            "Puella Magi Madoka Magica",
            "https://en.wikipedia.org/wiki/Puella_Magi_Madoka_Magica",
        ),
        (
            "ja",
            "魔法少女まどか☆マギカ",
            "https://ja.wikipedia.org/wiki/"
            "%E9%AD%94%E6%B3%95%E5%B0%91%E5%A5%B3%E3%81%BE%E3%81%A9%E3%81%8B%E2%98%86%E3%83%9E%E3%82%AE%E3%82%AB",
        ),
    ]


def test_classify_wikipedia_link_requires_subject_identity_and_rejects_relationships():
    assert (
        classify_wikipedia_link(
            "Puella Magi Madoka Magica",
            "A television anime.",
            ("puella_magi_madoka_magica",),
        )
        == "subject"
    )
    assert (
        classify_wikipedia_link(
            "Investiture of the Gods",
            "The plot is loosely based on https://en.wikipedia.org/wiki/example.",
            ("nezha_zhi_motong_jiangshi", "哪吒之魔童降世"),
        )
        == "related"
    )
    assert (
        classify_wikipedia_link("Unrelated title", "See also this page.", ("expected_title",))
        == "unknown"
    )
    assert (
        classify_wikipedia_link(
            "Alice (Blue Archive)", "Character page.", ("alice_(blue_archive)",)
        )
        == "subject"
    )


def test_sync_wikipedia_only_uses_copyright_and_character_pages(tmp_path):
    root = make_root(tmp_path, minimum_records=5)
    config = load_config(root)
    tags = open_database(root / config.danbooru.database_path)
    with tags:
        write_tags(
            tags,
            [
                Tag(1, "general", 0, 10, "created", "updated", False),
                Tag(2, "artist", 1, 10, "created", "updated", False),
                Tag(3, "copyright", 3, 10, "created", "updated", False),
                Tag(4, "character", 4, 10, "created", "updated", False),
                Tag(5, "meta", 5, 10, "created", "updated", False),
            ],
        )
    tags.close()
    wiki = open_wiki_database(root / config.wiki.database_path)
    with wiki:
        write_wiki_pages(
            wiki,
            [
                (
                    WikiPage(
                        10,
                        "general",
                        "https://zh.wikipedia.org/wiki/通用",
                        (),
                        "created",
                        "updated",
                        False,
                        False,
                    ),
                    1,
                ),
                (
                    WikiPage(
                        11,
                        "copyright",
                        "https://zh.wikipedia.org/wiki/魔法少女小圆",
                        ("魔法少女小圆",),
                        "created",
                        "updated",
                        False,
                        False,
                    ),
                    3,
                ),
                (
                    WikiPage(
                        12,
                        "character",
                        "The character is based on "
                        "https://en.wikipedia.org/wiki/Investiture_of_the_Gods",
                        ("哪吒",),
                        "created",
                        "updated",
                        False,
                        False,
                    ),
                    4,
                ),
            ],
            base_url="https://example.test",
            retrieved_at="retrieved",
        )
        set_state(wiki, "scanned_total", 3)
        set_state(wiki, "completed_at", "completed")
    wiki.close()

    result = sync_wikipedia(root, config)

    assert result["sources"] == 2
    assert result["resolved"] == 1
    assert result["by_relation"] == {"subject": 1, "related": 1, "unknown": 0}
    database = sqlite3.connect(root / config.wikipedia.database_path)
    assert database.execute(
        "SELECT tag_id, relation, zh_title, context FROM wikipedia_sources ORDER BY tag_id"
    ).fetchall() == [
        (3, "subject", "魔法少女小圆", "https://zh.wikipedia.org/wiki/魔法少女小圆"),
        (
            4,
            "related",
            None,
            "The character is based on https://en.wikipedia.org/wiki/Investiture_of_the_Gods",
        ),
    ]
    database.close()
