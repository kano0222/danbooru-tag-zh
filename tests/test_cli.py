from __future__ import annotations

import json

import pytest

from danbooru_tag_zh import cli
from danbooru_tag_zh.datasets import _dataset_files, write_files
from danbooru_tag_zh.models import Tag
from danbooru_tag_zh.storage import open_database, write_tags

from .helpers import make_root


@pytest.mark.parametrize("command", ["tag-stats", "validate-tags"])
def test_local_commands_report_database(tmp_path, command, capsys):
    root = make_root(tmp_path, minimum_records=1)
    path = root / "data/state/tags.sqlite"
    connection = open_database(path)
    with connection:
        write_tags(
            connection,
            [
                Tag(1, "general", 0, 10, "created", "updated", False),
                Tag(2, "artist", 1, 10, "created", "updated", False),
                Tag(3, "copyright", 3, 10, "created", "updated", False),
                Tag(4, "character", 4, 10, "created", "updated", False),
                Tag(5, "meta", 5, 10, "created", "updated", False),
            ],
        )
    connection.close()

    assert cli.run(cli.parser().parse_args([command, "--root", str(root)])) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 5


@pytest.mark.parametrize("command", ["validate-artifacts", "artifact-stats"])
def test_artifact_commands_handle_both_datasets(tmp_path, command, capsys):
    root = make_root(tmp_path)
    for dataset in ("ffdkj", "wiki-reviewed"):
        write_files(
            root / "artifacts" / dataset,
            _dataset_files(
                dataset,
                {"long_hair": "长发"},
                {"method": "test"},
                {"total": 1},
                generated_at="2026-01-01T00:00:00Z",
            ),
        )

    assert cli.run(cli.parser().parse_args([command, "--root", str(root)])) == 0
    output = json.loads(capsys.readouterr().out)
    assert set(output) == {"ffdkj", "wiki-reviewed"}
