from __future__ import annotations

from dataclasses import dataclass

CATEGORY_NAMES = {
    0: "general",
    1: "artist",
    3: "copyright",
    4: "character",
    5: "meta",
}


@dataclass(frozen=True, slots=True)
class Tag:
    id: int
    name: str
    category: int
    post_count: int
    created_at: str
    updated_at: str
    is_deprecated: bool


@dataclass(frozen=True, slots=True)
class WikiPage:
    id: int
    title: str
    body: str
    other_names: tuple[str, ...]
    created_at: str
    updated_at: str
    is_locked: bool
    is_deleted: bool


@dataclass(frozen=True, slots=True)
class TagRecord:
    name: str
    category: int
    cn_name: str
    post_count: int


@dataclass(frozen=True, slots=True)
class SourceInfo:
    repository: str
    branch: str
    commit: str
    download_url: str
    retrieved_at: str
    sqlite_sha256: str
    sqlite_size: int
