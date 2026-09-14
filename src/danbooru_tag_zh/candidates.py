from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from opencc import OpenCC

from .config import Config
from .models import CATEGORY_NAMES
from .storage import validate_database, validate_wiki_database
from .wikipedia_syncer import validate_wikipedia_database

HAN_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))
KANA_RANGES = ((0x3040, 0x30FF), (0xFF66, 0xFF9F))
HANGUL_RANGES = ((0x1100, 0x11FF), (0xAC00, 0xD7AF))
STATUSES = ("no_wiki", "no_candidate", "single_candidate", "multiple_candidates")
TRADITIONAL_TO_SIMPLIFIED = OpenCC("t2s")
EXPLICIT_CHINESE_MARKER = re.compile(
    r"simplified chinese|chinese (?:name|title)|"
    r"wikipedia(?: article)?[^:\n]{0,100}\((?:chinese|ch|cn)\)",
    re.IGNORECASE,
)


def _contains_range(value: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= ord(char) <= end for char in value for start, end in ranges)


def cjk_candidates(other_names: list[object], tag_name: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    normalized_tag = tag_name.replace("_", " ").casefold()
    for raw in other_names:
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if (
            not value
            or not _contains_range(value, HAN_RANGES)
            or _contains_range(value, KANA_RANGES)
            or _contains_range(value, HANGUL_RANGES)
            or TRADITIONAL_TO_SIMPLIFIED.convert(value) != value
            or value.replace("_", " ").casefold() == normalized_tag
            or value in seen
        ):
            continue
        seen.add(value)
        result.append(value)
    return result


def reference_aliases(other_names: list[object], tag_name: str, candidates: list[str]) -> list[str]:
    result: list[str] = []
    seen = set(candidates)
    normalized_tag = tag_name.replace("_", " ").casefold()
    for raw in other_names:
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value or value in seen or value.replace("_", " ").casefold() == normalized_tag:
            continue
        seen.add(value)
        result.append(value)
    return result


def _has_han_boundary(value: str, line: str) -> bool:
    for match in re.finditer(re.escape(value), line):
        before = line[match.start() - 1] if match.start() else ""
        after = line[match.end()] if match.end() < len(line) else ""
        if not _contains_range(before, HAN_RANGES) and not _contains_range(after, HAN_RANGES):
            return True
    return False


def infer_wiki_candidate(body: str, candidates: list[str]) -> tuple[str, str] | None:
    matches: list[str] = []
    for line in body.splitlines():
        if not EXPLICIT_CHINESE_MARKER.search(line):
            continue
        matches.extend(candidate for candidate in candidates if _has_han_boundary(candidate, line))
    unique = list(dict.fromkeys(matches))
    if len(unique) != 1:
        return None
    return unique[0], "wiki_explicit_chinese_name"


def _title_key(value: str) -> str:
    return str(TRADITIONAL_TO_SIMPLIFIED.convert(value)).replace("_", " ").strip().casefold()


def infer_wikipedia_candidate(
    titles: list[tuple[str, str]], candidates: list[str]
) -> tuple[str, str, str] | None:
    candidates_by_key: dict[str, list[str]] = {}
    for candidate in candidates:
        candidates_by_key.setdefault(_title_key(candidate), []).append(candidate)
    matches: list[tuple[str, str]] = []
    for title, source_url in titles:
        values = candidates_by_key.get(_title_key(title), [])
        matches.extend((candidate, source_url) for candidate in values)
    unique_values = list(dict.fromkeys(candidate for candidate, _ in matches))
    if len(unique_values) != 1:
        return None
    selected = unique_values[0]
    source_url = next(url for candidate, url in matches if candidate == selected)
    return selected, "wikipedia_zh_title", source_url


def wikipedia_reference_titles(titles: list[tuple[str, str]], candidates: list[str]) -> list[str]:
    candidate_keys = {_title_key(candidate) for candidate in candidates}
    result: list[str] = []
    seen: set[str] = set()
    for title, _source_url in titles:
        key = _title_key(title)
        if key in candidate_keys or key in seen:
            continue
        seen.add(key)
        result.append(title)
    return result


def _combine_inferences(
    wiki: tuple[str, str] | None,
    wikipedia: tuple[str, str, str] | None,
    wiki_url: str | None,
) -> tuple[str, str, str | None] | None:
    if wiki is not None and wikipedia is not None:
        if wiki[0] != wikipedia[0]:
            return None
        return wiki[0], "danbooru_wiki_and_wikipedia", wikipedia[2]
    if wikipedia is not None:
        return wikipedia
    if wiki is not None:
        return wiki[0], wiki[1], wiki_url
    return None


def _open_output(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE candidate_groups (
            tag_id INTEGER PRIMARY KEY,
            tag_name TEXT NOT NULL UNIQUE,
            category INTEGER NOT NULL CHECK (category IN (0, 3, 4, 5)),
            post_count INTEGER NOT NULL,
            wiki_page_id INTEGER,
            status TEXT NOT NULL CHECK (
                status IN ('no_wiki', 'no_candidate', 'single_candidate', 'multiple_candidates')
            ),
            source_url TEXT,
            reference_aliases TEXT NOT NULL,
            inferred_translation TEXT,
            inference_reason TEXT,
            inference_source_url TEXT,
            wikipedia_references TEXT NOT NULL
        );
        CREATE TABLE translation_candidates (
            tag_id INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            value TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK (source_type = 'wiki_other_name'),
            source_url TEXT NOT NULL,
            PRIMARY KEY (tag_id, rank),
            UNIQUE (tag_id, value),
            FOREIGN KEY (tag_id) REFERENCES candidate_groups(tag_id)
        );
        CREATE INDEX candidate_groups_status_idx ON candidate_groups(status);
        """
    )
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA user_version=5")
    return connection


def _status(has_wiki: bool, candidates: list[str]) -> str:
    if not has_wiki:
        return "no_wiki"
    if not candidates:
        return "no_candidate"
    if len(candidates) == 1:
        return "single_candidate"
    return "multiple_candidates"


def build_candidates(root: Path, config: Config) -> dict[str, object]:
    tags_path = root / config.danbooru.database_path
    wiki_path = root / config.wiki.database_path
    validate_database(tags_path, minimum_records=config.validation.minimum_records)
    validate_wiki_database(wiki_path)
    wikipedia_by_tag: dict[int, list[tuple[str, str]]] = {}
    wikipedia_path = root / config.wikipedia.database_path
    if wikipedia_path.is_file():
        validate_wikipedia_database(wikipedia_path)
        wikipedia = sqlite3.connect(f"{wikipedia_path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            for tag_id, zh_title, source_url in wikipedia.execute(
                "SELECT tag_id, zh_title, source_url FROM wikipedia_sources "
                "WHERE zh_title IS NOT NULL AND relation='subject'"
            ):
                wikipedia_by_tag.setdefault(int(tag_id), []).append(
                    (str(zh_title), str(source_url))
                )
        finally:
            wikipedia.close()
    destination = root / config.translation.database_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
    temporary.unlink()
    output = _open_output(temporary)
    tags = sqlite3.connect(f"{tags_path.resolve().as_uri()}?mode=ro", uri=True)
    wiki = sqlite3.connect(f"{wiki_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        wiki_by_tag = {
            int(tag_id): (int(page_id), json.loads(other_names), str(body), str(source_url))
            for tag_id, page_id, other_names, body, source_url in wiki.execute(
                "SELECT tag_id, id, other_names, body, source_url FROM wiki_pages"
            )
        }
        with output:
            for tag_id, tag_name, category, post_count in tags.execute(
                "SELECT id, name, category, post_count FROM tags "
                "WHERE category != 1 ORDER BY post_count DESC, id"
            ):
                evidence = wiki_by_tag.get(int(tag_id))
                values = cjk_candidates(evidence[1], str(tag_name)) if evidence else []
                aliases = reference_aliases(evidence[1], str(tag_name), values) if evidence else []
                wiki_inference = infer_wiki_candidate(evidence[2], values) if evidence else None
                wikipedia_inference = (
                    infer_wikipedia_candidate(wikipedia_by_tag.get(int(tag_id), []), values)
                    if int(category) in (3, 4)
                    else None
                )
                wikipedia_references = (
                    wikipedia_reference_titles(wikipedia_by_tag.get(int(tag_id), []), values)
                    if int(category) in (3, 4)
                    else []
                )
                inference = _combine_inferences(
                    wiki_inference, wikipedia_inference, evidence[3] if evidence else None
                )
                status = _status(evidence is not None, values)
                source_url = evidence[3] if evidence else None
                output.execute(
                    "INSERT INTO candidate_groups VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tag_id,
                        tag_name,
                        category,
                        post_count,
                        evidence[0] if evidence else None,
                        status,
                        source_url,
                        json.dumps(aliases, ensure_ascii=False, separators=(",", ":")),
                        inference[0] if inference else None,
                        inference[1] if inference else None,
                        inference[2] if inference else None,
                        json.dumps(
                            wikipedia_references,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    ),
                )
                if source_url:
                    output.executemany(
                        "INSERT INTO translation_candidates VALUES (?, ?, ?, ?, ?)",
                        [
                            (tag_id, rank, value, "wiki_other_name", source_url)
                            for rank, value in enumerate(values, start=1)
                        ],
                    )
    finally:
        tags.close()
        wiki.close()
        output.close()
    os.replace(temporary, destination)
    stats = candidate_stats(destination)
    _write_review_report(destination, root / config.translation.review_report_path)
    return {"database": str(destination), **stats}


def candidate_stats(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        status_counts = Counter(
            {
                str(status): int(count)
                for status, count in connection.execute(
                    "SELECT status, COUNT(*) FROM candidate_groups GROUP BY status"
                )
            }
        )
        category_counts: dict[str, dict[str, int]] = {}
        for category, status, count in connection.execute(
            "SELECT category, status, COUNT(*) FROM candidate_groups GROUP BY category, status"
        ):
            category_counts.setdefault(CATEGORY_NAMES[int(category)], {})[str(status)] = int(count)
        total_candidates = int(
            connection.execute("SELECT COUNT(*) FROM translation_candidates").fetchone()[0]
        )
        inferred = int(
            connection.execute(
                "SELECT COUNT(*) FROM candidate_groups WHERE inferred_translation IS NOT NULL"
            ).fetchone()[0]
        )
        return {
            "groups": sum(status_counts.values()),
            "candidates": total_candidates,
            "inferred": inferred,
            "by_status": dict(sorted(status_counts.items())),
            "by_category": dict(sorted(category_counts.items())),
        }
    finally:
        connection.close()


def _write_review_report(database: Path, report: Path) -> None:
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        groups: list[dict[str, Any]] = []
        rows = connection.execute(
            "SELECT tag_id, tag_name, category, post_count, source_url FROM candidate_groups "
            "WHERE status = 'multiple_candidates' AND inferred_translation IS NULL "
            "ORDER BY post_count DESC, tag_name"
        )
        for tag_id, tag_name, category, post_count, source_url in rows:
            candidates = [
                str(row[0])
                for row in connection.execute(
                    "SELECT value FROM translation_candidates WHERE tag_id = ? ORDER BY rank",
                    (tag_id,),
                )
            ]
            groups.append(
                {
                    "tag": tag_name,
                    "category": CATEGORY_NAMES[int(category)],
                    "post_count": post_count,
                    "candidates": candidates,
                    "source_url": source_url,
                }
            )
    finally:
        connection.close()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(groups, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
