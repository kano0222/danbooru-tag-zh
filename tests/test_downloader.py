from __future__ import annotations

import hashlib
import io
import json
from email.message import Message

import pytest

from danbooru_tag_zh import downloader
from danbooru_tag_zh.config import SourceConfig
from danbooru_tag_zh.downloader import acquire_database, raw_url, resolve_commit

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


@pytest.mark.parametrize("token", [None, "", "test-token"])
def test_commit_query_uses_optional_github_token(monkeypatch, token):
    if token is None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    else:
        monkeypatch.setenv("GITHUB_TOKEN", token)

    def urlopen(request, *, timeout):
        assert request.full_url == "https://api.github.com/repos/owner/repo/commits/main"
        assert request.get_header("User-agent") == downloader.USER_AGENT
        assert request.get_header("Authorization") == (f"Bearer {token}" if token else None)
        assert timeout == config().timeout_seconds
        return io.BytesIO(json.dumps({"sha": "a" * 40}).encode())

    monkeypatch.setattr(downloader, "urlopen", urlopen)
    assert resolve_commit(config()) == "a" * 40


def test_database_download_does_not_send_github_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    data = make_database(tmp_path / "tag.sqlite", [("tag", 0, "翻译", 1)]).read_bytes()

    def urlopen(request, *, timeout):
        assert request.full_url == raw_url(config(), "a" * 40)
        assert request.get_header("Authorization") is None
        response = io.BytesIO(data)
        response.headers = Message()
        return response

    monkeypatch.setattr(downloader, "urlopen", urlopen)
    actual, info = acquire_database(tmp_path, config(), commit="a" * 40)
    assert actual.read_bytes() == data
    assert info.commit == "a" * 40


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
