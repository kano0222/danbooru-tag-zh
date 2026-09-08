from __future__ import annotations

import json

from danbooru_tag_zh.cli import parser, run

from .helpers import make_database


def make_root(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/default.toml").write_text(
        """
[source]
repository = "owner/repo"
branch = "main"
database_path = "tag.sqlite"
timeout_seconds = 10.0
maximum_download_bytes = 1048576
[validation]
minimum_records = 1
maximum_record_decrease_ratio = 0.05
maximum_translation_change_ratio = 0.10
[output]
directory = "local-dist"
report_directory = "reports"
""".strip(),
        encoding="utf-8",
    )
    return tmp_path


def test_dry_run_does_not_write_outputs(tmp_path):
    root = make_root(tmp_path)
    source = make_database(tmp_path / "tag.sqlite", [("tag", 0, "翻译", 1)])
    args = parser().parse_args(
        ["update", "--root", str(root), "--source", str(source), "--dry-run"]
    )

    assert run(args) == 0
    assert not (root / "local-dist").exists()
    assert not (root / "reports").exists()


def test_update_validate_and_stats(tmp_path):
    root = make_root(tmp_path)
    source = make_database(tmp_path / "tag.sqlite", [("tag", 0, "翻译", 1)])

    assert run(parser().parse_args(["update", "--root", str(root), "--source", str(source)])) == 0
    assert run(parser().parse_args(["validate", "--root", str(root)])) == 0
    assert run(parser().parse_args(["stats", "--root", str(root)])) == 0
    assert (root / "reports/update-diff.json").exists()
    report = json.loads((root / "reports/update-diff.json").read_text(encoding="utf-8"))
    assert report["previous_commit"] is None
    assert report["current_commit"] == "local"
