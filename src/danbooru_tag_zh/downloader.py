from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import SourceConfig
from .models import SourceInfo

USER_AGENT = "danbooru-tag-zh/0.1"


class BinaryReader(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class BinaryWriter(Protocol):
    def write(self, data: bytes) -> int: ...


class HttpResponse(BinaryReader, Protocol):
    headers: Message

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


def _request(url: str, timeout: float) -> HttpResponse:
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        response = urlopen(request, timeout=timeout)  # noqa: S310
        return cast(HttpResponse, response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"failed to download {url}: {exc}") from exc


def resolve_commit(config: SourceConfig) -> str:
    repository = quote(config.repository, safe="/")
    branch = quote(config.branch, safe="")
    url = f"https://api.github.com/repos/{repository}/commits/{branch}"
    with _request(url, config.timeout_seconds) as response:
        payload = json.load(response)
    commit = payload.get("sha") if isinstance(payload, dict) else None
    if not isinstance(commit, str) or len(commit) != 40:
        raise RuntimeError("GitHub returned an invalid commit SHA")
    return commit


def raw_url(config: SourceConfig, commit: str) -> str:
    repository = quote(config.repository, safe="/")
    path = quote(config.database_path, safe="/")
    return f"https://raw.githubusercontent.com/{repository}/{commit}/{path}"


def _copy_limited(source: BinaryReader, destination: BinaryWriter, maximum_bytes: int) -> int:
    total = 0
    while chunk := source.read(1024 * 1024):
        total += len(chunk)
        if total > maximum_bytes:
            raise RuntimeError("upstream SQLite file exceeds the configured size limit")
        destination.write(chunk)
    return total


def acquire_database(
    root: Path,
    config: SourceConfig,
    *,
    commit: str | None = None,
    source: Path | None = None,
) -> tuple[Path, SourceInfo]:
    retrieved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if source is not None:
        path = source.resolve()
        if not path.is_file():
            raise ValueError(f"SQLite source does not exist: {path}")
        size = path.stat().st_size
        if size > config.maximum_download_bytes:
            raise ValueError("local SQLite file exceeds the configured size limit")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        info = SourceInfo(
            repository=config.repository,
            branch=config.branch,
            commit="local",
            download_url=path.as_uri(),
            retrieved_at=retrieved_at,
            sqlite_sha256=digest,
            sqlite_size=size,
        )
        return path, info

    resolved = commit or resolve_commit(config)
    if len(resolved) != 40 or any(char not in "0123456789abcdefABCDEF" for char in resolved):
        raise ValueError("commit must be a 40-character hexadecimal SHA")
    resolved = resolved.lower()
    url = raw_url(config, resolved)
    cache = root / ".cache/upstream" / resolved / "tag.sqlite"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with _request(url, config.timeout_seconds) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > config.maximum_download_bytes:
                raise RuntimeError("upstream SQLite file exceeds the configured size limit")
            with tempfile.NamedTemporaryFile(dir=cache.parent, delete=False) as handle:
                temporary = Path(handle.name)
                try:
                    _copy_limited(response, handle, config.maximum_download_bytes)
                except Exception:
                    handle.close()
                    temporary.unlink(missing_ok=True)
                    raise
        temporary.replace(cache)
    size = cache.stat().st_size
    digest = hashlib.sha256(cache.read_bytes()).hexdigest()
    info = SourceInfo(
        repository=config.repository,
        branch=config.branch,
        commit=resolved,
        download_url=url,
        retrieved_at=retrieved_at,
        sqlite_sha256=digest,
        sqlite_size=size,
    )
    return cache, info
