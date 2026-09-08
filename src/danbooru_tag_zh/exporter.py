from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import ValidationConfig
from .models import CATEGORY_NAMES, SourceInfo, TagRecord


def _json_bytes(value: object, *, compact: bool) -> bytes:
    options: dict[str, Any] = {"ensure_ascii": False, "sort_keys": True}
    if compact:
        options["separators"] = (",", ":")
    else:
        options["indent"] = 2
    return (json.dumps(value, **options) + ("" if compact else "\n")).encode("utf-8")


def _file_metadata(data: bytes) -> dict[str, object]:
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def build_artifacts(
    records: list[TagRecord],
    source: SourceInfo,
    *,
    source_record_count: int | None = None,
    excluded_unchanged: int = 0,
) -> tuple[dict[str, bytes], dict[str, object]]:
    light = {record.name: record.cn_name for record in records}
    audit = [asdict(record) for record in records]
    light_bytes = _json_bytes(light, compact=True)
    audit_bytes = _json_bytes(audit, compact=False)
    files = {
        "zh-hans.min.json": light_bytes,
        "tags.zh-hans.json.gz": gzip.compress(audit_bytes, compresslevel=9, mtime=0),
    }
    category_counts = Counter(CATEGORY_NAMES[record.category] for record in records)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "source": {
            **asdict(source),
            "redistribution_status": "unconfirmed-local-only",
        },
        "records": {
            "source_total": source_record_count
            if source_record_count is not None
            else len(records),
            "total": len(records),
            "excluded_unchanged": excluded_unchanged,
            "by_category": dict(sorted(category_counts.items())),
        },
        "artifacts": {name: _file_metadata(data) for name, data in sorted(files.items())},
    }
    files["manifest.json"] = _json_bytes(manifest, compact=False)
    return files, manifest


def load_previous_records(output: Path) -> list[TagRecord] | None:
    path = output / "tags.zh-hans.json.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, list):
        raise ValueError("previous audit artifact must be an array")
    return [TagRecord(**item) for item in raw]


def compare_records(
    previous: list[TagRecord] | None,
    current: list[TagRecord],
    config: ValidationConfig,
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
            "category_changed": 0,
            "post_count_changed": 0,
            "samples": {},
        }
    old = {record.name: record for record in previous}
    new = {record.name: record for record in current}
    added = sorted(new.keys() - old.keys())
    removed = sorted(old.keys() - new.keys())
    shared = sorted(old.keys() & new.keys())
    translations = [name for name in shared if old[name].cn_name != new[name].cn_name]
    categories = [name for name in shared if old[name].category != new[name].category]
    post_counts = [name for name in shared if old[name].post_count != new[name].post_count]
    previous_categories = {record.category for record in previous}
    current_categories = {record.category for record in current}
    decrease_ratio = len(removed) / len(previous) if previous else 0
    translation_ratio = len(translations) / len(previous) if previous else 0
    reasons: list[str] = []
    if decrease_ratio > config.maximum_record_decrease_ratio:
        reasons.append("record decrease exceeds configured ratio")
    if translation_ratio > config.maximum_translation_change_ratio:
        reasons.append("translation changes exceed configured ratio")
    if previous_categories - current_categories:
        reasons.append("one or more tag categories disappeared")
    if reasons and not accept_large_change:
        raise ValueError("; ".join(reasons) + "; inspect the diff and use --accept-large-change")
    return {
        "previous_records": len(previous),
        "current_records": len(current),
        "added": len(added),
        "removed": len(removed),
        "translation_changed": len(translations),
        "category_changed": len(categories),
        "post_count_changed": len(post_counts),
        "samples": {
            "added": added[:20],
            "removed": removed[:20],
            "translation_changed": [
                {"tag": name, "before": old[name].cn_name, "after": new[name].cn_name}
                for name in translations[:20]
            ],
            "category_changed": [
                {"tag": name, "before": old[name].category, "after": new[name].category}
                for name in categories[:20]
            ],
        },
    }


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
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def validate_artifacts(directory: Path) -> dict[str, Any]:
    manifest_path = directory / "manifest.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("manifest artifacts are missing")
    for name, raw_metadata in artifacts.items():
        if not isinstance(name, str) or not isinstance(raw_metadata, dict):
            raise ValueError("manifest artifact metadata is invalid")
        data = (directory / name).read_bytes()
        if raw_metadata.get("size") != len(data):
            raise ValueError(f"artifact size mismatch: {name}")
        if raw_metadata.get("sha256") != hashlib.sha256(data).hexdigest():
            raise ValueError(f"artifact checksum mismatch: {name}")
    light = json.loads((directory / "zh-hans.min.json").read_text(encoding="utf-8"))
    records = load_previous_records(directory)
    if records is None or not isinstance(light, dict):
        raise ValueError("translation artifacts are missing")
    expected = {record.name: record.cn_name for record in records}
    if light != expected:
        raise ValueError("compact and audit artifacts do not contain the same translations")
    records_metadata = manifest.get("records")
    if not isinstance(records_metadata, dict) or records_metadata.get("total") != len(records):
        raise ValueError("manifest record count mismatch")
    source_total = records_metadata.get("source_total")
    excluded = records_metadata.get("excluded_unchanged")
    if (
        not isinstance(source_total, int)
        or not isinstance(excluded, int)
        or source_total != len(records) + excluded
    ):
        raise ValueError("manifest source record count mismatch")
    return manifest
