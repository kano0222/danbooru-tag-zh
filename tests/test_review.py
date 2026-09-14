from __future__ import annotations

import json
import sqlite3

import pytest

from danbooru_tag_zh.review import ReviewStore


def make_candidates(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE candidate_groups (
            tag_id INTEGER PRIMARY KEY, tag_name TEXT, category INTEGER, post_count INTEGER,
            wiki_page_id INTEGER, status TEXT, source_url TEXT, reference_aliases TEXT,
            inferred_translation TEXT, inference_reason TEXT, inference_source_url TEXT,
            wikipedia_references TEXT
        );
        CREATE TABLE translation_candidates (
            tag_id INTEGER, rank INTEGER, value TEXT, source_type TEXT, source_url TEXT
        );
        INSERT INTO candidate_groups VALUES
            (1, 'long_hair', 0, 100, 10, 'multiple_candidates',
             'https://example.test/10', '["ロングヘア","긴 머리"]', NULL, NULL, NULL, '[]'),
            (2, 'smile', 0, 90, 11, 'single_candidate',
             'https://example.test/11', '[]', '微笑', 'wiki_explicit_chinese_name',
             'https://example.test/11', '["笑脸"]'),
            (3, 'fate/stay_night', 3, 80, 12, 'no_candidate',
             'https://example.test/12', '[]', NULL, NULL, NULL, '["Fate/stay night"]');
        INSERT INTO translation_candidates VALUES
            (1, 1, '长发', 'wiki_other_name', 'https://example.test/10'),
            (1, 2, '长头发', 'wiki_other_name', 'https://example.test/10'),
            (2, 1, '微笑', 'wiki_other_name', 'https://example.test/11');
        """
    )
    connection.close()


def test_review_decision_is_saved_separately_and_pending_advances(tmp_path):
    database = tmp_path / "candidates.sqlite"
    decisions = tmp_path / "manual/translations.json"
    make_candidates(database)
    store = ReviewStore(database, decisions)

    first = store.item(
        offset=0,
        category="all",
        candidate_status="multiple_candidates",
        review_status="pending",
        query="",
    )
    assert first["item"]["tag"] == "long_hair"
    assert first["item"]["reference_aliases"] == ["ロングヘア", "긴 머리"]
    assert first["item"]["wikipedia_references"] == []
    store.decide({"tag": "long_hair", "action": "accept", "translation": "长发"})

    saved = json.loads(decisions.read_text(encoding="utf-8"))
    assert saved["decisions"]["long_hair"]["source"] == "wiki_other_name"
    pending = store.item(
        offset=0,
        category="all",
        candidate_status="multiple_candidates",
        review_status="pending",
        query="",
    )
    assert pending["total"] == 0


def test_custom_translation_is_marked_manual(tmp_path):
    database = tmp_path / "candidates.sqlite"
    decisions = tmp_path / "translations.json"
    make_candidates(database)
    store = ReviewStore(database, decisions)

    result = store.decide({"tag": "smile", "action": "accept", "translation": "笑容"})

    assert result["decision"]["source"] == "manual"


def test_original_tag_can_be_recorded_as_an_intentional_term(tmp_path):
    database = tmp_path / "candidates.sqlite"
    decisions = tmp_path / "translations.json"
    make_candidates(database)
    store = ReviewStore(database, decisions)

    result = store.decide({"tag": "smile", "action": "accept", "translation": "smile"})

    assert result["decision"]["source"] == "original_term"
    assert result["decision"]["translation"] == "smile"

    branded = store.decide(
        {"tag": "fate/stay_night", "action": "accept", "translation": "Fate/stay night"}
    )
    assert branded["decision"]["source"] == "original_term"


def test_no_candidate_group_with_wikipedia_reference_can_be_reviewed(tmp_path):
    database = tmp_path / "candidates.sqlite"
    make_candidates(database)
    store = ReviewStore(database, tmp_path / "translations.json")

    result = store.item(
        offset=0,
        category="copyright",
        candidate_status="no_candidate",
        review_status="pending",
        query="",
    )

    assert result["item"]["tag"] == "fate/stay_night"
    assert result["item"]["candidates"] == []
    assert result["item"]["wikipedia_references"] == ["Fate/stay night"]


def test_inferred_translation_is_accepted_without_entering_pending_queue(tmp_path):
    database = tmp_path / "candidates.sqlite"
    make_candidates(database)
    store = ReviewStore(database, tmp_path / "translations.json")

    pending = store.item(
        offset=0,
        category="all",
        candidate_status="single_candidate",
        review_status="pending",
        query="",
    )
    accepted = store.item(
        offset=0,
        category="all",
        candidate_status="single_candidate",
        review_status="accept",
        query="",
    )

    assert pending["total"] == 0
    assert accepted["item"]["decision"] == {
        "action": "accept",
        "translation": "微笑",
        "source": "wiki_inferred",
        "reason": "wiki_explicit_chinese_name",
        "source_url": "https://example.test/11",
    }


def test_undo_restores_previous_decision(tmp_path):
    database = tmp_path / "candidates.sqlite"
    decisions = tmp_path / "translations.json"
    make_candidates(database)
    store = ReviewStore(database, decisions)

    store.decide({"tag": "long_hair", "action": "accept", "translation": "长发"})
    store.decide({"tag": "long_hair", "action": "accept", "translation": "长头发"})
    assert store.undo() == {"ok": True, "tag": "long_hair"}

    saved = json.loads(decisions.read_text(encoding="utf-8"))
    assert saved["decisions"]["long_hair"]["translation"] == "长发"
    with pytest.raises(ValueError, match="no decision"):
        store.undo()


def test_rejects_empty_translation(tmp_path):
    database = tmp_path / "candidates.sqlite"
    make_candidates(database)
    store = ReviewStore(database, tmp_path / "translations.json")

    with pytest.raises(ValueError, match="length"):
        store.decide({"tag": "smile", "action": "accept", "translation": "  "})
