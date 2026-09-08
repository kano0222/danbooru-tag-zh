from __future__ import annotations

import json

import pytest

from danbooru_tag_zh.config import ValidationConfig
from danbooru_tag_zh.exporter import (
    build_artifacts,
    compare_records,
    validate_artifacts,
    write_files,
)
from danbooru_tag_zh.models import SourceInfo, TagRecord


def source_info() -> SourceInfo:
    return SourceInfo("owner/repo", "main", "a" * 40, "https://example.test/db", "now", "b" * 64, 1)


def records() -> list[TagRecord]:
    return [
        TagRecord("1girl", 0, "单人女性", 20),
        TagRecord("alice", 4, "爱丽丝", 10),
    ]


def config() -> ValidationConfig:
    return ValidationConfig(0, 0.05, 0.10)


def test_build_is_deterministic_and_preserves_translations(tmp_path):
    first, _ = build_artifacts(records(), source_info())
    second, _ = build_artifacts(records(), source_info())

    assert first == second
    assert json.loads(first["zh-hans.min.json"]) == {
        "1girl": "单人女性",
        "alice": "爱丽丝",
    }
    write_files(tmp_path, first)
    assert validate_artifacts(tmp_path)["records"]["total"] == 2


def test_manifest_records_excluded_unchanged_count(tmp_path):
    files, _ = build_artifacts(
        records(), source_info(), source_record_count=3, excluded_unchanged=1
    )
    write_files(tmp_path, files)

    metadata = validate_artifacts(tmp_path)["records"]
    assert metadata["source_total"] == 3
    assert metadata["total"] == 2
    assert metadata["excluded_unchanged"] == 1


def test_validation_detects_modified_artifact(tmp_path):
    files, _ = build_artifacts(records(), source_info())
    write_files(tmp_path, files)
    (tmp_path / "zh-hans.min.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact size mismatch"):
        validate_artifacts(tmp_path)


def test_large_translation_change_requires_explicit_acceptance():
    previous = records()
    current = [TagRecord("1girl", 0, "一名女孩", 21), previous[1]]

    with pytest.raises(ValueError, match="translation changes"):
        compare_records(previous, current, config(), accept_large_change=False)

    result = compare_records(previous, current, config(), accept_large_change=True)
    assert result["translation_changed"] == 1
    assert result["post_count_changed"] == 1


def test_disappearing_category_requires_explicit_acceptance():
    with pytest.raises(ValueError, match="categories disappeared"):
        compare_records(records(), records()[:1], config(), accept_large_change=False)
