from __future__ import annotations

import json
import time
from collections.abc import Callable
from email.message import Message
from types import TracebackType
from typing import Protocol, Self, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import DanbooruConfig, WikiConfig
from .models import CATEGORY_NAMES, Tag, WikiPage

USER_AGENT = "danbooru-tag-zh/0.1 (+https://github.com/kano0222/danbooru-tag-zh)"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class HttpResponse(Protocol):
    headers: Message

    def read(self, size: int = -1) -> bytes: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


OpenUrl = Callable[[Request, float], HttpResponse]
Sleep = Callable[[float], None]


def _open(request: Request, timeout: float) -> HttpResponse:
    return cast(HttpResponse, urlopen(request, timeout=timeout))  # noqa: S310


def build_tags_url(config: DanbooruConfig, before_id: int | None) -> str:
    parameters = {
        "limit": str(config.page_size),
        "search[post_count]": f"{config.minimum_post_count}..",
        "search[order]": "id_desc",
    }
    if before_id is not None:
        parameters["page"] = f"b{before_id}"
    return f"{config.base_url.rstrip('/')}/tags.json?{urlencode(parameters)}"


def build_wiki_pages_url(base_url: str, config: WikiConfig, before_id: int) -> str:
    parameters = {"limit": str(config.page_size), "page": f"b{before_id}"}
    return f"{base_url.rstrip('/')}/wiki_pages.json?{urlencode(parameters)}"


def parse_tag(raw: object) -> Tag:
    if not isinstance(raw, dict):
        raise ValueError("Danbooru returned a non-object tag")
    tag_id = raw.get("id")
    name = raw.get("name")
    category = raw.get("category")
    post_count = raw.get("post_count")
    created_at = raw.get("created_at")
    updated_at = raw.get("updated_at")
    is_deprecated = raw.get("is_deprecated")
    if type(tag_id) is not int or tag_id <= 0:
        raise ValueError("Danbooru returned an invalid tag ID")
    if not isinstance(name, str) or not name or any(ord(char) < 32 for char in name):
        raise ValueError(f"Danbooru returned an invalid name for tag {tag_id}")
    if type(category) is not int or category not in CATEGORY_NAMES:
        raise ValueError(f"Danbooru returned an invalid category for tag {tag_id}")
    if type(post_count) is not int or post_count < 0:
        raise ValueError(f"Danbooru returned an invalid post count for tag {tag_id}")
    if not isinstance(created_at, str) or not isinstance(updated_at, str):
        raise ValueError(f"Danbooru returned invalid timestamps for tag {tag_id}")
    if type(is_deprecated) is not bool:
        raise ValueError(f"Danbooru returned an invalid deprecation state for tag {tag_id}")
    return Tag(tag_id, name, category, post_count, created_at, updated_at, is_deprecated)


def parse_wiki_page(raw: object) -> WikiPage:
    if not isinstance(raw, dict):
        raise ValueError("Danbooru returned a non-object Wiki page")
    page_id = raw.get("id")
    title = raw.get("title")
    body = raw.get("body")
    other_names = raw.get("other_names")
    created_at = raw.get("created_at")
    updated_at = raw.get("updated_at")
    is_locked = raw.get("is_locked")
    is_deleted = raw.get("is_deleted")
    if type(page_id) is not int or page_id <= 0:
        raise ValueError("Danbooru returned an invalid Wiki page ID")
    if not isinstance(title, str) or not title:
        raise ValueError(f"Danbooru returned an invalid title for Wiki page {page_id}")
    if not isinstance(body, str):
        raise ValueError(f"Danbooru returned an invalid body for Wiki page {page_id}")
    if not isinstance(other_names, list) or not all(isinstance(name, str) for name in other_names):
        raise ValueError(f"Danbooru returned invalid other names for Wiki page {page_id}")
    if not isinstance(created_at, str) or not isinstance(updated_at, str):
        raise ValueError(f"Danbooru returned invalid timestamps for Wiki page {page_id}")
    if type(is_locked) is not bool or type(is_deleted) is not bool:
        raise ValueError(f"Danbooru returned invalid flags for Wiki page {page_id}")
    return WikiPage(
        page_id,
        title,
        body,
        tuple(other_names),
        created_at,
        updated_at,
        is_locked,
        is_deleted,
    )


class DanbooruClient:
    def __init__(
        self,
        config: DanbooruConfig,
        *,
        open_url: OpenUrl = _open,
        sleep: Sleep = time.sleep,
    ) -> None:
        self.config = config
        self.open_url = open_url
        self.sleep = sleep
        self._last_request_finished: float | None = None

    def fetch_page(self, before_id: int | None) -> list[Tag]:
        url = build_tags_url(self.config, before_id)
        payload = self._request_json(url)
        if not isinstance(payload, list):
            raise ValueError("Danbooru tags response must be an array")
        tags = [parse_tag(item) for item in payload]
        if any(tag.post_count < self.config.minimum_post_count for tag in tags):
            raise ValueError("Danbooru returned a tag below the requested post-count limit")
        self._validate_page([tag.id for tag in tags], before_id, "tags")
        return tags

    def _request_json(self, url: str) -> object:
        for attempt in range(self.config.maximum_retries + 1):
            self._wait_for_interval()
            request = Request(  # noqa: S310
                url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
            )
            try:
                with self.open_url(request, self.config.timeout_seconds) as response:
                    payload = json.load(response)
                self._last_request_finished = time.monotonic()
                return payload
            except HTTPError as exc:
                self._last_request_finished = time.monotonic()
                if exc.code not in RETRYABLE_STATUS_CODES or attempt == self.config.maximum_retries:
                    raise RuntimeError(f"Danbooru request failed with HTTP {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                self.sleep(delay)
            except (URLError, TimeoutError) as exc:
                self._last_request_finished = time.monotonic()
                if attempt == self.config.maximum_retries:
                    raise RuntimeError(f"Danbooru request failed: {exc}") from exc
                self.sleep(2**attempt)
        raise AssertionError("retry loop terminated unexpectedly")

    def _wait_for_interval(self) -> None:
        if self._last_request_finished is None:
            return
        remaining = self.config.request_interval_seconds - (
            time.monotonic() - self._last_request_finished
        )
        if remaining > 0:
            self.sleep(remaining)

    @staticmethod
    def _validate_page(ids: list[int], before_id: int | None, resource: str) -> None:
        if len(ids) != len(set(ids)):
            raise ValueError(f"Danbooru returned duplicate {resource} IDs in one page")
        if ids != sorted(ids, reverse=True):
            raise ValueError(f"Danbooru {resource} are not ordered by descending ID")
        if before_id is not None and any(tag_id >= before_id for tag_id in ids):
            raise ValueError("Danbooru cursor pagination did not advance")


class DanbooruWikiClient:
    def __init__(
        self,
        base_url: str,
        config: WikiConfig,
        *,
        open_url: OpenUrl = _open,
        sleep: Sleep = time.sleep,
    ) -> None:
        self.base_url = base_url
        self.config = config
        self.open_url = open_url
        self.sleep = sleep
        self._last_request_finished: float | None = None

    def fetch_page(self, before_id: int) -> list[WikiPage]:
        url = build_wiki_pages_url(self.base_url, self.config, before_id)
        payload = self._request_json(url)
        if not isinstance(payload, list):
            raise ValueError("Danbooru Wiki response must be an array")
        pages = [parse_wiki_page(item) for item in payload]
        DanbooruClient._validate_page([page.id for page in pages], before_id, "Wiki pages")
        return pages

    def _request_json(self, url: str) -> object:
        for attempt in range(self.config.maximum_retries + 1):
            self._wait_for_interval()
            request = Request(  # noqa: S310
                url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
            )
            try:
                with self.open_url(request, self.config.timeout_seconds) as response:
                    payload = json.load(response)
                self._last_request_finished = time.monotonic()
                return payload
            except HTTPError as exc:
                self._last_request_finished = time.monotonic()
                if exc.code not in RETRYABLE_STATUS_CODES or attempt == self.config.maximum_retries:
                    raise RuntimeError(f"Danbooru request failed with HTTP {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                self.sleep(delay)
            except (URLError, TimeoutError) as exc:
                self._last_request_finished = time.monotonic()
                if attempt == self.config.maximum_retries:
                    raise RuntimeError(f"Danbooru request failed: {exc}") from exc
                self.sleep(2**attempt)
        raise AssertionError("retry loop terminated unexpectedly")

    def _wait_for_interval(self) -> None:
        if self._last_request_finished is None:
            return
        remaining = self.config.request_interval_seconds - (
            time.monotonic() - self._last_request_finished
        )
        if remaining > 0:
            self.sleep(remaining)
