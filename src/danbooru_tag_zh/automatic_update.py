from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import Config
from .datasets import (
    ARTIFACT_NAME,
    MANIFEST_NAME,
    build_datasets,
    load_ffdkj_lock,
    update_ffdkj_lock,
    validate_dataset,
    write_files,
)
from .downloader import resolve_commit


def prepare_ffdkj_update(root: Path, config: Config) -> dict[str, object]:
    """Prepare validated changes locally; never commit or publish them."""
    directory = Path(config.artifacts.directory) / "ffdkj"
    lock_path = Path(config.ffdkj.lock_path)
    manifest = validate_dataset(root / directory, expected_dataset="ffdkj")
    lock, source = load_ffdkj_lock(root, config.ffdkj)
    if manifest["source"] != {"upstream": lock["source"], "license": lock["license"]}:
        raise ValueError("published manifest does not match the source lock")
    if not manifest["records"]["total"]:
        raise ValueError("published translation artifact is empty")
    commit = resolve_commit(config.ffdkj)
    if commit == source.commit:
        return {"status": "unchanged-source", "commit": commit}

    with tempfile.TemporaryDirectory(prefix="ffdkj-update-") as temporary:
        candidate = Path(temporary)
        # Seed the existing comparison logic with the published baseline, not an empty directory.
        (candidate / directory).mkdir(parents=True)
        for name in (ARTIFACT_NAME, MANIFEST_NAME):
            shutil.copyfile(root / directory / name, candidate / directory / name)
        update_ffdkj_lock(candidate, config, commit=commit)
        result = build_datasets(candidate, config, dataset="ffdkj")
        checked = validate_dataset(candidate / directory, expected_dataset="ffdkj")
        if not checked["records"]["total"]:
            raise ValueError("candidate translation artifact is empty")
        old = json.loads((root / directory / ARTIFACT_NAME).read_text(encoding="utf-8"))
        new = json.loads((candidate / directory / ARTIFACT_NAME).read_text(encoding="utf-8"))
        if old == new:
            return {"status": "unchanged-content", "commit": commit, "diff": result}
        # All validation has completed before touching the three publishable files.
        paths = (directory / ARTIFACT_NAME, directory / MANIFEST_NAME, lock_path)
        payload = {path: (candidate / path).read_bytes() for path in paths}
        for path, data in payload.items():
            write_files(root / path.parent, {path.name: data})
    return {"status": "updated", "commit": commit, "diff": result}


def check_publish_baseline(root: Path, baseline: str, branch: str) -> None:
    if not baseline or not branch or branch.startswith("-"):
        raise ValueError("a baseline commit and branch are required")
    result = subprocess.run(  # noqa: S603
        ["git", "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    fields = result.stdout.split()
    if fields != [baseline, f"refs/heads/{branch}"]:
        raise ValueError("remote HEAD changed; stop publishing and rebuild on the next run")
