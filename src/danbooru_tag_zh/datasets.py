from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Config, SourceConfig, ValidationConfig
from .downloader import acquire_database
from .importer import import_records
from .models import CATEGORY_NAMES, SourceInfo, TagRecord

ARTIFACT_NAME = "zh-hans.min.json"
MANIFEST_NAME = "manifest.json"
DATASETS = ("ffdkj", "wiki-reviewed")
FFDKJ_LICENSE = {
    "spdx_id": "MIT",
    "url": (
        "https://github.com/ffdkj/"
        "ffdkj-Danbooru_Tag-Chinese-English-Translation-Table/blob/main/LICENSE"
    ),
    "permission_url": (
        "https://github.com/ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table/issues/1"
    ),
}
NORMALIZATIONS = ("fullwidth_parentheses_to_ascii",)
FULLWIDTH_LEFT_PARENTHESIS = "\uff08"
FULLWIDTH_RIGHT_PARENTHESIS = "\uff09"


def normalize_translation(value: str) -> str:
    return value.replace(FULLWIDTH_LEFT_PARENTHESIS, "(").replace(FULLWIDTH_RIGHT_PARENTHESIS, ")")


def write_files(directory: Path, files: dict[str, bytes]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for name, data in files.items():
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
                handle.write(data)
                staged.append((Path(handle.name), directory / name))
        for temporary, destination in staged:
            temporary.replace(destination)
    finally:
        for temporary, _destination in staged:
            temporary.unlink(missing_ok=True)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_bytes(value: object, *, compact: bool) -> bytes:
    options: dict[str, Any] = {"ensure_ascii": False, "sort_keys": True}
    if compact:
        options["separators"] = (",", ":")
    else:
        options["indent"] = 2
    suffix = "" if compact else "\n"
    return (json.dumps(value, **options) + suffix).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _source_info(raw: object) -> SourceInfo:
    if not isinstance(raw, dict):
        raise ValueError("ffdkj lock source is invalid")
    try:
        return SourceInfo(
            repository=str(raw["repository"]),
            branch=str(raw["branch"]),
            commit=str(raw["commit"]),
            download_url=str(raw["download_url"]),
            retrieved_at=str(raw["retrieved_at"]),
            sqlite_sha256=str(raw["sqlite_sha256"]),
            sqlite_size=int(raw["sqlite_size"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ffdkj lock source is invalid") from exc


def update_ffdkj_lock(
    root: Path, config: Config, *, commit: str | None = None
) -> dict[str, object]:
    database, source = acquire_database(root, config.ffdkj, commit=commit)
    records = import_records(database, minimum_records=config.validation.minimum_records)
    payload: dict[str, object] = {
        "schema_version": 1,
        "source": asdict(source),
        "license": FFDKJ_LICENSE,
        "records": len(records),
    }
    lock = root / config.ffdkj.lock_path
    write_files(lock.parent, {lock.name: _json_bytes(payload, compact=False)})
    return payload


def load_ffdkj_lock(root: Path, config: SourceConfig) -> tuple[dict[str, object], SourceInfo]:
    path = root / config.lock_path
    if not path.is_file():
        raise ValueError(f"ffdkj lock does not exist: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("ffdkj lock has an unsupported schema")
    source = _source_info(raw.get("source"))
    if source.repository != config.repository or source.branch != config.branch:
        raise ValueError("ffdkj lock does not match the configured repository")
    if len(source.commit) != 40 or any(char not in "0123456789abcdef" for char in source.commit):
        raise ValueError("ffdkj lock commit is invalid")
    if len(source.sqlite_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in source.sqlite_sha256
    ):
        raise ValueError("ffdkj lock checksum is invalid")
    if raw.get("license") != FFDKJ_LICENSE:
        raise ValueError("ffdkj lock license metadata is invalid")
    return raw, source


def _ffdkj_mapping(records: list[TagRecord]) -> tuple[dict[str, str], dict[str, object]]:
    mapping: dict[str, str] = {}
    categories: Counter[str] = Counter()
    excluded_artist = 0
    excluded_unchanged = 0
    for record in records:
        if record.category == 1:
            excluded_artist += 1
            continue
        translation = normalize_translation(record.cn_name)
        if translation == record.name:
            excluded_unchanged += 1
            continue
        mapping[record.name] = translation
        categories[CATEGORY_NAMES[record.category]] += 1
    return dict(sorted(mapping.items())), {
        "source_total": len(records),
        "total": len(mapping),
        "excluded_artist": excluded_artist,
        "excluded_unchanged": excluded_unchanged,
        "by_category": dict(sorted(categories.items())),
    }


def _load_decisions(path: Path) -> dict[str, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("manual translation file has an unsupported schema")
    decisions = raw.get("decisions")
    if not isinstance(decisions, dict):
        raise ValueError("manual translation decisions must be an object")
    return {str(tag): value for tag, value in decisions.items() if isinstance(value, dict)}


def _wiki_reviewed_mapping(
    database_path: Path, decisions_path: Path
) -> tuple[dict[str, str], dict[str, object]]:
    if not database_path.is_file():
        raise ValueError(f"candidate database does not exist: {database_path}")
    decisions = _load_decisions(decisions_path)
    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT tag_name, category, inferred_translation, inference_reason "
            "FROM candidate_groups "
            "WHERE category != 1 ORDER BY tag_name"
        ).fetchall()
    finally:
        connection.close()
    groups = {
        str(tag): (int(category), inferred, reason) for tag, category, inferred, reason in rows
    }
    translations: dict[str, tuple[str, str]] = {
        tag: (
            normalize_translation(str(inferred)),
            "wikipedia_inferred"
            if reason in {"wikipedia_zh_title", "danbooru_wiki_and_wikipedia"}
            else "wiki_inferred",
        )
        for tag, (_category, inferred, reason) in groups.items()
        if inferred is not None and str(inferred) != tag
    }
    excluded_unchanged = 0
    for tag, decision in decisions.items():
        if tag not in groups:
            raise ValueError(f"manual decision refers to an unknown candidate group: {tag}")
        if decision.get("action") != "accept":
            translations.pop(tag, None)
            continue
        translation = decision.get("translation")
        if not isinstance(translation, str) or not translation.strip():
            raise ValueError(f"accepted decision has no translation: {tag}")
        translation = normalize_translation(translation.strip())
        if translation == tag:
            translations.pop(tag, None)
            excluded_unchanged += 1
            continue
        decision_source = decision.get("source")
        source = decision_source if isinstance(decision_source, str) else "manual"
        translations[tag] = (translation, source)
    mapping = {tag: value for tag, (value, _source) in sorted(translations.items())}
    categories: Counter[str] = Counter(CATEGORY_NAMES[groups[tag][0]] for tag in mapping)
    sources: Counter[str] = Counter(source for _value, source in translations.values())
    return mapping, {
        "candidate_groups": len(groups),
        "manual_decisions": len(decisions),
        "total": len(mapping),
        "excluded_unchanged": excluded_unchanged,
        "by_category": dict(sorted(categories.items())),
        "by_acceptance_source": dict(sorted(sources.items())),
    }


def _dataset_files(
    dataset: str,
    mapping: dict[str, str],
    source: Mapping[str, object],
    records: Mapping[str, object],
    *,
    generated_at: str | None = None,
) -> dict[str, bytes]:
    artifact = _json_bytes(mapping, compact=True)
    manifest = {
        "schema_version": 1,
        "dataset": dataset,
        "generated_at": generated_at or _now(),
        "normalizations": list(NORMALIZATIONS),
        "source": source,
        "records": records,
        "artifacts": {
            ARTIFACT_NAME: {
                "size": len(artifact),
                "sha256": hashlib.sha256(artifact).hexdigest(),
            }
        },
    }
    return {ARTIFACT_NAME: artifact, MANIFEST_NAME: _json_bytes(manifest, compact=False)}


def _load_existing_mapping(directory: Path) -> dict[str, str] | None:
    path = directory / ARTIFACT_NAME
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw.items()
    ):
        raise ValueError(f"existing translation artifact is invalid: {path}")
    return raw


def compare_mappings(
    previous: dict[str, str] | None,
    current: dict[str, str],
    validation: ValidationConfig,
    *,
    accept_large_change: bool,
) -> dict[str, object]:
    if previous is None:
        return {
            "previous_records": 0,
            "current_records": len(current),
            "added": len(current),
            "removed": 0,
            "translation_changed": 0,
        }
    old_keys = set(previous)
    new_keys = set(current)
    removed = old_keys - new_keys
    changed = {tag for tag in old_keys & new_keys if previous[tag] != current[tag]}
    reasons: list[str] = []
    if previous and len(removed) / len(previous) > validation.maximum_record_decrease_ratio:
        reasons.append("record decrease exceeds configured ratio")
    if previous and len(changed) / len(previous) > validation.maximum_translation_change_ratio:
        reasons.append("translation changes exceed configured ratio")
    if reasons and not accept_large_change:
        raise ValueError("; ".join(reasons) + "; inspect the diff and use --accept-large-change")
    return {
        "previous_records": len(previous),
        "current_records": len(current),
        "added": len(new_keys - old_keys),
        "removed": len(removed),
        "translation_changed": len(changed),
    }


def build_datasets(
    root: Path,
    config: Config,
    *,
    dataset: str = "all",
    dry_run: bool = False,
    accept_large_change: bool = False,
) -> dict[str, object]:
    if dataset not in {"all", *DATASETS}:
        raise ValueError(f"unsupported dataset: {dataset}")
    output_root = root / config.artifacts.directory
    result: dict[str, object] = {}
    if dataset in {"all", "ffdkj"}:
        lock, locked_source = load_ffdkj_lock(root, config.ffdkj)
        database, actual_source = acquire_database(root, config.ffdkj, commit=locked_source.commit)
        if (
            actual_source.sqlite_sha256 != locked_source.sqlite_sha256
            or actual_source.sqlite_size != locked_source.sqlite_size
        ):
            raise ValueError("downloaded ffdkj database does not match the lock")
        source_records = import_records(database, minimum_records=config.validation.minimum_records)
        mapping, records = _ffdkj_mapping(source_records)
        directory = output_root / "ffdkj"
        difference = compare_mappings(
            _load_existing_mapping(directory),
            mapping,
            config.validation,
            accept_large_change=accept_large_change,
        )
        files = _dataset_files(
            "ffdkj",
            mapping,
            {"upstream": lock["source"], "license": lock["license"]},
            records,
        )
        if not dry_run:
            write_files(directory, files)
        result["ffdkj"] = {"records": records, "diff": difference}
    if dataset in {"all", "wiki-reviewed"}:
        candidate_path = root / config.translation.database_path
        decisions_path = root / config.translation.manual_decisions_path
        mapping, records = _wiki_reviewed_mapping(candidate_path, decisions_path)
        directory = output_root / "wiki-reviewed"
        difference = compare_mappings(
            _load_existing_mapping(directory),
            mapping,
            config.validation,
            accept_large_change=accept_large_change,
        )
        source = {
            "candidate_database_sha256": _sha256(candidate_path),
            "manual_decisions_sha256": _sha256(decisions_path),
            "method": "Danbooru Wiki evidence, Wikipedia title matching, and manual review",
        }
        files = _dataset_files("wiki-reviewed", mapping, source, records)
        if not dry_run:
            write_files(directory, files)
        result["wiki-reviewed"] = {"records": records, "diff": difference}
    return result


def validate_dataset(directory: Path, *, expected_dataset: str) -> dict[str, Any]:
    manifest_path = directory / MANIFEST_NAME
    artifact_path = directory / ARTIFACT_NAME
    if not manifest_path.is_file() or not artifact_path.is_file():
        raise ValueError(f"dataset artifacts are missing: {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mapping = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("dataset manifest has an unsupported schema")
    if manifest.get("dataset") != expected_dataset:
        raise ValueError("dataset manifest has the wrong dataset name")
    if manifest.get("normalizations") != list(NORMALIZATIONS):
        raise ValueError("dataset manifest has the wrong normalization rules")
    if not isinstance(mapping, dict) or not all(
        isinstance(tag, str) and isinstance(value, str) and tag and value
        for tag, value in mapping.items()
    ):
        raise ValueError("translation artifact must map non-empty strings")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("translation artifact metadata is missing")
    metadata = artifacts.get(ARTIFACT_NAME)
    data = artifact_path.read_bytes()
    if not isinstance(metadata, dict):
        raise ValueError("translation artifact metadata is missing")
    if metadata.get("size") != len(data):
        raise ValueError("translation artifact size mismatch")
    if metadata.get("sha256") != hashlib.sha256(data).hexdigest():
        raise ValueError("translation artifact checksum mismatch")
    records = manifest.get("records")
    if not isinstance(records, dict) or records.get("total") != len(mapping):
        raise ValueError("translation artifact record count mismatch")
    if any(tag == translation for tag, translation in mapping.items()):
        raise ValueError("translation artifact contains unchanged tags")
    if any(
        FULLWIDTH_LEFT_PARENTHESIS in translation or FULLWIDTH_RIGHT_PARENTHESIS in translation
        for translation in mapping.values()
    ):
        raise ValueError("translation artifact contains fullwidth parentheses")
    return manifest


def validate_datasets(
    root: Path, config: Config, *, dataset: str = "all"
) -> dict[str, dict[str, Any]]:
    if dataset not in {"all", *DATASETS}:
        raise ValueError(f"unsupported dataset: {dataset}")
    names = DATASETS if dataset == "all" else (dataset,)
    output = root / config.artifacts.directory
    return {name: validate_dataset(output / name, expected_dataset=name) for name in names}
