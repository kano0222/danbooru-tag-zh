from __future__ import annotations

import sqlite3

import pytest

from danbooru_tag_zh.importer import exclude_unchanged_translations, import_records
from danbooru_tag_zh.models import TagRecord

from .helpers import make_database


def test_imports_all_rows_in_stable_tag_order(tmp_path):
    path = make_database(
        tmp_path / "tags.sqlite",
        [("蓝_eyes", 0, "蓝瞳", 10), ("1girl", 0, "单人女性", 20)],
    )

    records = import_records(path, minimum_records=2)

    assert [record.name for record in records] == ["1girl", "蓝_eyes"]
    assert records[0].cn_name == "单人女性"


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (("", 0, "翻译", 1), "invalid name"),
        (("tag", 2, "翻译", 1), "invalid category"),
        (("tag", 0, "", 1), "invalid Chinese translation"),
        (("tag", 0, "翻译\n文本", 1), "control character"),
        (("tag", 0, "翻译", -1), "invalid post count"),
    ],
)
def test_rejects_invalid_rows(tmp_path, row, message):
    path = make_database(tmp_path / "tags.sqlite", [row])

    with pytest.raises(ValueError, match=message):
        import_records(path, minimum_records=0)


def test_rejects_missing_table(tmp_path):
    path = tmp_path / "empty.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE other (value TEXT)")
    connection.commit()
    connection.close()

    with pytest.raises(ValueError, match="tags table"):
        import_records(path, minimum_records=0)


def test_rejects_non_sqlite_file(tmp_path):
    path = tmp_path / "bad.sqlite"
    path.write_bytes(b"not sqlite")

    with pytest.raises(ValueError, match="not a SQLite"):
        import_records(path, minimum_records=0)


def test_enforces_minimum_record_count(tmp_path):
    path = make_database(tmp_path / "tags.sqlite", [("tag", 0, "翻译", 1)])

    with pytest.raises(ValueError, match="expected at least 2"):
        import_records(path, minimum_records=2)


def test_excludes_only_exact_unchanged_translations():
    records = [
        TagRecord("alice", 4, "alice", 10),
        TagRecord("ALICE", 4, "alice", 9),
        TagRecord("blue_eyes", 0, "blue eyes", 8),
        TagRecord("long_hair", 0, "长发", 7),
    ]

    filtered, excluded = exclude_unchanged_translations(records)

    assert excluded == 1
    assert [record.name for record in filtered] == ["ALICE", "blue_eyes", "long_hair"]
