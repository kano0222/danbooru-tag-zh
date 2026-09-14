from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from .config import WikipediaConfig
from .danbooru_client import USER_AGENT, OpenUrl, Sleep, _open

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def build_langlinks_url(language: str, titles: list[str]) -> str:
    parameters = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "langlinks",
        "lllang": "zh",
        "lllimit": "max",
        "redirects": "1",
        "titles": "|".join(titles),
    }
    return f"https://{language}.wikipedia.org/w/api.php?{urlencode(parameters)}"


def parse_langlinks(payload: object, requested_titles: list[str]) -> dict[str, str | None]:
    if not isinstance(payload, dict) or not isinstance(payload.get("query"), dict):
        raise ValueError("Wikipedia returned an invalid query response")
    query = payload["query"]
    aliases = {title: title for title in requested_titles}
    for key in ("normalized", "redirects"):
        values = query.get(key, [])
        if not isinstance(values, list):
            raise ValueError("Wikipedia returned invalid title mappings")
        for item in values:
            if (
                isinstance(item, dict)
                and isinstance(item.get("from"), str)
                and isinstance(item.get("to"), str)
            ):
                aliases[item["from"]] = item["to"]
    pages = query.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Wikipedia returned invalid pages")
    titles_by_page: dict[str, str | None] = {}
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("title"), str):
            continue
        result: str | None = None
        langlinks = page.get("langlinks", [])
        if isinstance(langlinks, list):
            for link in langlinks:
                if (
                    isinstance(link, dict)
                    and link.get("lang") == "zh"
                    and isinstance(link.get("title"), str)
                ):
                    result = link["title"]
                    break
        titles_by_page[page["title"].casefold()] = result

    results: dict[str, str | None] = {}
    for requested in requested_titles:
        resolved = requested
        for _ in range(4):
            mapped = aliases.get(resolved)
            if mapped is None or mapped == resolved:
                break
            resolved = mapped
        results[requested] = titles_by_page.get(resolved.casefold())
    return results


class WikipediaClient:
    def __init__(
        self,
        config: WikipediaConfig,
        *,
        open_url: OpenUrl = _open,
        sleep: Sleep = time.sleep,
    ) -> None:
        self.config = config
        self.open_url = open_url
        self.sleep = sleep
        self._last_request_finished: float | None = None

    def fetch_zh_titles(self, language: str, titles: list[str]) -> dict[str, str | None]:
        if language == "zh":
            return {title: title for title in titles}
        url = build_langlinks_url(language, titles)
        payload = self._request_json(url)
        return parse_langlinks(payload, titles)

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
                    raise RuntimeError(f"Wikipedia request failed with HTTP {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                self.sleep(delay)
            except (URLError, TimeoutError) as exc:
                self._last_request_finished = time.monotonic()
                if attempt == self.config.maximum_retries:
                    raise RuntimeError(f"Wikipedia request failed: {exc}") from exc
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
