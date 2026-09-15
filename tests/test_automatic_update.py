from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace

import pytest

from danbooru_tag_zh import automatic_update, datasets
from danbooru_tag_zh.config import load_config
from danbooru_tag_zh.models import SourceInfo

from .helpers import make_database, make_root


@pytest.fixture
def published(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    config = load_config(root)
    config = replace(
        config,
        validation=replace(
            config.validation,
            maximum_record_decrease_ratio=0.005,
            maximum_translation_change_ratio=0.01,
        ),
    )
    rows = [(f"tag_{i}", 0, f"译文{i}", 100) for i in range(200)]
    selected = [make_database(root / "old.sqlite", rows)]

    def acquire(_root, source_config, *, commit=None):
        data = selected[0].read_bytes()
        return selected[0], SourceInfo(
            source_config.repository,
            source_config.branch,
            commit or "a" * 40,
            "https://example.test/tag.sqlite",
            "2026-01-01T00:00:00Z",
            hashlib.sha256(data).hexdigest(),
            len(data),
        )

    monkeypatch.setattr(datasets, "acquire_database", acquire)
    monkeypatch.setattr(automatic_update, "resolve_commit", lambda _config: "b" * 40)
    datasets.update_ffdkj_lock(root, config, commit="a" * 40)
    datasets.build_datasets(root, config, dataset="ffdkj")
    paths = [
        root / "artifacts/ffdkj" / name
        for name in (
            datasets.ARTIFACT_NAME,
            datasets.MANIFEST_NAME,
        )
    ] + [root / config.ffdkj.lock_path]
    snapshot = {path: path.read_bytes() for path in paths}
    return root, config, rows, selected, snapshot


def test_same_sha_skips_download(published, monkeypatch):
    root, config, _, _, snapshot = published
    monkeypatch.setattr(automatic_update, "resolve_commit", lambda _config: "a" * 40)

    def unexpected(*args, **kwargs):
        pytest.fail("same SHA must not download")

    monkeypatch.setattr(datasets, "acquire_database", unexpected)
    assert automatic_update.prepare_ffdkj_update(root, config)["status"] == "unchanged-source"
    assert all(path.read_bytes() == data for path, data in snapshot.items())


def test_same_content_preserves_source_lock(published):
    root, config, _, _, snapshot = published
    assert automatic_update.prepare_ffdkj_update(root, config)["status"] == "unchanged-content"
    assert all(path.read_bytes() == data for path, data in snapshot.items())


def test_threshold_boundary_and_large_additions_publish_together(published):
    root, config, rows, selected, _ = published
    # Exactly 0.5% removed and 1% modified; additions alone are not a gate.
    rows = rows[1:]
    rows[:2] = [
        (name, category, "新译文" + text, count) for name, category, text, count in rows[:2]
    ]
    rows += [(f"new_{i}", 0, f"新增{i}", 1) for i in range(100)]
    selected[0] = make_database(root / "candidate.sqlite", rows)
    result = automatic_update.prepare_ffdkj_update(root, config)
    assert result["status"] == "updated"
    manifest = datasets.validate_dataset(root / "artifacts/ffdkj", expected_dataset="ffdkj")
    lock, source = datasets.load_ffdkj_lock(root, config.ffdkj)
    assert source.commit == "b" * 40
    assert manifest["source"]["upstream"] == lock["source"]
    assert manifest["records"]["total"] == 299


@pytest.mark.parametrize("problem", ["removed", "modified", "invalid", "empty"])
def test_bad_candidate_never_changes_published_files(published, problem):
    root, config, rows, selected, snapshot = published
    if problem == "removed":
        rows = rows[2:]
    elif problem == "modified":
        rows[:3] = [
            (name, category, "变更" + text, count) for name, category, text, count in rows[:3]
        ]
    elif problem == "invalid":
        rows[0] = ("tag_0", 0, "", 100)
    else:
        rows = [(name, 1, text, count) for name, _, text, count in rows]
        config = replace(
            config,
            validation=replace(
                config.validation,
                maximum_record_decrease_ratio=1.0,
            ),
        )
    selected[0] = make_database(root / "candidate.sqlite", rows)
    with pytest.raises(ValueError):
        automatic_update.prepare_ffdkj_update(root, config)
    assert all(path.read_bytes() == data for path, data in snapshot.items())


@pytest.mark.parametrize("problem", ["missing", "checksum", "lock", "empty"])
def test_invalid_baseline_blocks_update(published, problem, monkeypatch):
    root, config, _, _, _ = published
    directory = root / "artifacts/ffdkj"
    if problem == "missing":
        (directory / datasets.ARTIFACT_NAME).unlink()
    elif problem == "checksum":
        (directory / datasets.ARTIFACT_NAME).write_text("{}", encoding="utf-8")
    elif problem == "lock":
        path = root / config.ffdkj.lock_path
        lock = json.loads(path.read_text(encoding="utf-8"))
        lock["source"]["commit"] = "c" * 40
        path.write_text(json.dumps(lock), encoding="utf-8")
    else:
        manifest = json.loads((directory / datasets.MANIFEST_NAME).read_text(encoding="utf-8"))
        datasets.write_files(
            directory,
            datasets._dataset_files(
                "ffdkj",
                {},
                manifest["source"],
                {"total": 0},
            ),
        )

    def unexpected(_config):
        pytest.fail("invalid baseline must stop before network access")

    monkeypatch.setattr(automatic_update, "resolve_commit", unexpected)
    with pytest.raises(ValueError):
        automatic_update.prepare_ffdkj_update(root, config)


@pytest.mark.parametrize("remote", ["a" * 40, "b" * 40])
def test_remote_head_gate(tmp_path, monkeypatch, remote):
    def run(command, **kwargs):
        assert command == ["git", "ls-remote", "--exit-code", "origin", "refs/heads/main"]
        return subprocess.CompletedProcess(command, 0, f"{remote}\trefs/heads/main\n")

    monkeypatch.setattr(automatic_update.subprocess, "run", run)
    if remote == "a" * 40:
        automatic_update.check_publish_baseline(tmp_path, "a" * 40, "main")
    else:
        with pytest.raises(ValueError, match="remote HEAD changed"):
            automatic_update.check_publish_baseline(tmp_path, "a" * 40, "main")
