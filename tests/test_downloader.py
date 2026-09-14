from __future__ import annotations

import hashlib

import pytest

from danbooru_tag_zh.config import SourceConfig
from danbooru_tag_zh.downloader import acquire_database, raw_url

from .helpers import make_database


def config(maximum_download_bytes=1024 * 1024) -> SourceConfig:
    return SourceConfig(
        "owner/repo",
        "main",
        "tag.sqlite",
        "data/sources/ffdkj.lock.json",
        10,
        maximum_download_bytes,
    )


def test_raw_url_is_pinned_to_commit():
    assert raw_url(config(), "a" * 40) == (
        "https://raw.githubusercontent.com/owner/repo/" + "a" * 40 + "/tag.sqlite"
    )


def test_local_source_records_digest(tmp_path):
    path = make_database(tmp_path / "tag.sqlite", [("tag", 0, "翻译", 1)])

    actual, info = acquire_database(tmp_path, config(), source=path)

    assert actual == path.resolve()
    assert info.commit == "local"
    assert info.sqlite_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_rejects_oversized_local_source(tmp_path):
    path = tmp_path / "tag.sqlite"
    path.write_bytes(b"1234")

    with pytest.raises(ValueError, match="size limit"):
        acquire_database(tmp_path, config(maximum_download_bytes=3), source=path)
