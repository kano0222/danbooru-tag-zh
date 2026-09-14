from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

import pytest

from danbooru_tag_zh.config import ValidationConfig, load_config
from danbooru_tag_zh.datasets import (
    FFDKJ_LICENSE,
    _dataset_files,
    _ffdkj_mapping,
    _wiki_reviewed_mapping,
    compare_mappings,
    load_ffdkj_lock,
    validate_dataset,
    write_files,
)
from danbooru_tag_zh.models import SourceInfo, TagRecord

from .helpers import make_root


def test_ffdkj_mapping_excludes_artist_and_exact_unchanged_tag():
    mapping, stats = _ffdkj_mapping(
        [
            TagRecord("long_hair", 0, "长发\uff08描述\uff09", 100),
            TagRecord("an_artist", 1, "某画师", 90),
            TagRecord("unchanged", 5, "unchanged", 80),
            TagRecord("18trip", 3, "18Trip", 70),
        ]
    )

    assert mapping == {"18trip": "18Trip", "long_hair": "长发(描述)"}
    assert stats["excluded_artist"] == 1
    assert stats["excluded_unchanged"] == 1


def test_wiki_reviewed_mapping_applies_manual_decisions_over_inference(tmp_path):
    database = tmp_path / "translations.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE candidate_groups (
            tag_name TEXT PRIMARY KEY, category INTEGER, inferred_translation TEXT,
            inference_reason TEXT
        );
        INSERT INTO candidate_groups VALUES
            ('automatic', 0, '自动\uff08译名\uff09', 'wiki_explicit_chinese_name'),
            ('overridden', 4, '旧译名', 'wikipedia_zh_title'),
            ('rejected', 3, '不采用', 'wiki_explicit_chinese_name'),
            ('same', 5, NULL, NULL);
        """
    )
    connection.commit()
    connection.close()
    decisions = tmp_path / "translations.json"
    decisions.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "decisions": {
                    "overridden": {"action": "accept", "translation": "新\uff08译名\uff09"},
                    "rejected": {"action": "no_suitable"},
                    "same": {"action": "accept", "translation": "same"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    mapping, stats = _wiki_reviewed_mapping(database, decisions)

    assert mapping == {"automatic": "自动(译名)", "overridden": "新(译名)"}
    assert stats["excluded_unchanged"] == 1
    assert stats["by_acceptance_source"] == {"manual": 1, "wiki_inferred": 1}


def test_dataset_manifest_validates_compact_artifact(tmp_path):
    files = _dataset_files(
        "wiki-reviewed",
        {"long_hair": "长发"},
        {"method": "test"},
        {"total": 1},
        generated_at="2026-01-01T00:00:00Z",
    )
    write_files(tmp_path, files)

    manifest = validate_dataset(tmp_path, expected_dataset="wiki-reviewed")

    assert manifest["records"]["total"] == 1


def test_large_dataset_change_requires_explicit_acceptance():
    validation = ValidationConfig(0, 0.05, 0.10)

    with pytest.raises(ValueError, match="record decrease"):
        compare_mappings(
            {"a": "甲", "b": "乙"},
            {"a": "甲"},
            validation,
            accept_large_change=False,
        )


def test_ffdkj_lock_preserves_immutable_source_and_license(tmp_path):
    root = make_root(tmp_path)
    source = SourceInfo(
        "owner/repo",
        "main",
        "a" * 40,
        "https://example.test/tag.sqlite",
        "2026-01-01T00:00:00Z",
        "b" * 64,
        123,
    )
    path = root / "data/sources/ffdkj.lock.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": asdict(source),
                "license": FFDKJ_LICENSE,
                "records": 100,
            }
        ),
        encoding="utf-8",
    )

    lock, loaded = load_ffdkj_lock(root, load_config(root).ffdkj)

    assert loaded == source
    assert lock["license"] == FFDKJ_LICENSE
