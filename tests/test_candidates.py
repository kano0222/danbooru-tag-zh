from __future__ import annotations

import json
import sqlite3

from danbooru_tag_zh.candidates import (
    build_candidates,
    cjk_candidates,
    infer_wiki_candidate,
    infer_wikipedia_candidate,
    reference_aliases,
    wikipedia_reference_titles,
)
from danbooru_tag_zh.config import load_config
from danbooru_tag_zh.models import Tag, WikiPage
from danbooru_tag_zh.storage import (
    open_database,
    open_wiki_database,
    set_state,
    write_tags,
    write_wiki_pages,
)

from .helpers import make_root


def test_cjk_candidates_filter_language_and_duplicate_values():
    values = cjk_candidates(
        ["初音未来", "初音未來", "初音ミク", "하츠네 미쿠", "初音未来", "tag_name"],
        "tag_name",
    )
    assert values == ["初音未来"]


def test_reference_aliases_exclude_candidates_original_and_duplicates():
    assert reference_aliases(
        ["长发", "ロングヘア", "long hair", "long_hair", "long hair", " 긴 머리 "],
        "long_hair",
        ["长发"],
    ) == ["ロングヘア", "긴 머리"]


def test_infer_wiki_candidate_requires_unique_explicit_chinese_evidence():
    assert infer_wiki_candidate(
        "Simplified Chinese: 中秋节; Traditional Chinese: 中秋節",
        ["中秋", "中秋节"],
    ) == ("中秋节", "wiki_explicit_chinese_name")
    assert (
        infer_wiki_candidate("The Chinese names are 少女前线 and 少前.", ["少女前线", "少前"])
        is None
    )
    assert infer_wiki_candidate("A pose also called 鸭子坐.", ["割座", "鸭子坐"]) is None


def test_wikipedia_inference_only_selects_one_matching_candidate():
    assert infer_wikipedia_candidate(
        [("魔法少女小圆", "https://zh.wikipedia.org/wiki/example")],
        ["魔法少女小圆", "小圆"],
    ) == (
        "魔法少女小圆",
        "wikipedia_zh_title",
        "https://zh.wikipedia.org/wiki/example",
    )


def test_unmatched_wikipedia_titles_are_kept_as_references():
    assert wikipedia_reference_titles(
        [
            ("电锯人", "https://example.test/a"),
            ("链锯人", "https://example.test/b"),
            ("鏈鋸人", "https://example.test/c"),
        ],
        ["链锯人", "其他候选"],
    ) == ["电锯人"]
    assert (
        infer_wikipedia_candidate(
            [("作品甲", "https://example.test/a"), ("作品乙", "https://example.test/b")],
            ["作品甲", "作品乙"],
        )
        is None
    )


def test_build_candidates_separates_multiple_values_for_review(tmp_path):
    root = make_root(tmp_path, minimum_records=5)
    config = load_config(root)
    tags = open_database(root / config.danbooru.database_path)
    with tags:
        write_tags(
            tags,
            [
                Tag(1, "general", 0, 100, "created", "updated", False),
                Tag(2, "artist", 1, 90, "created", "updated", False),
                Tag(3, "copyright", 3, 80, "created", "updated", False),
                Tag(4, "character", 4, 70, "created", "updated", False),
                Tag(5, "meta", 5, 60, "created", "updated", False),
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
                        11,
                        "general",
                        "Body",
                        ("短译", "较长译名", "一般", "ジェネラル"),
                        "created",
                        "updated",
                        False,
                        False,
                    ),
                    1,
                )
            ],
            base_url="https://example.test",
            retrieved_at="retrieved",
        )
        set_state(wiki, "scanned_total", 1)
        set_state(wiki, "completed_at", "completed")
    wiki.close()

    result = build_candidates(root, config)

    assert result["groups"] == 4
    assert result["inferred"] == 0
    assert result["by_status"] == {"multiple_candidates": 1, "no_wiki": 3}
    report = json.loads((root / config.translation.review_report_path).read_text(encoding="utf-8"))
    assert report[0]["tag"] == "general"
    assert report[0]["candidates"] == ["短译", "较长译名", "一般"]
    database = sqlite3.connect(root / config.translation.database_path)
    raw_aliases = database.execute(
        "SELECT reference_aliases FROM candidate_groups WHERE tag_name = 'general'"
    ).fetchone()[0]
    database.close()
    assert json.loads(raw_aliases) == ["ジェネラル"]
