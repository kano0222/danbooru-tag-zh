from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DanbooruConfig:
    base_url: str
    minimum_post_count: int
    page_size: int
    request_interval_seconds: float
    timeout_seconds: float
    maximum_retries: int
    database_path: str


@dataclass(frozen=True, slots=True)
class ValidationConfig:
    minimum_records: int
    maximum_record_decrease_ratio: float
    maximum_translation_change_ratio: float


@dataclass(frozen=True, slots=True)
class WikiConfig:
    page_size: int
    request_interval_seconds: float
    timeout_seconds: float
    maximum_retries: int
    database_path: str


@dataclass(frozen=True, slots=True)
class WikipediaConfig:
    request_interval_seconds: float
    timeout_seconds: float
    maximum_retries: int
    database_path: str


@dataclass(frozen=True, slots=True)
class SourceConfig:
    repository: str
    branch: str
    database_path: str
    lock_path: str
    timeout_seconds: float
    maximum_download_bytes: int


@dataclass(frozen=True, slots=True)
class ArtifactConfig:
    directory: str


@dataclass(frozen=True, slots=True)
class TranslationConfig:
    database_path: str
    review_report_path: str
    manual_decisions_path: str


@dataclass(frozen=True, slots=True)
class Config:
    danbooru: DanbooruConfig
    wiki: WikiConfig
    wikipedia: WikipediaConfig
    ffdkj: SourceConfig
    artifacts: ArtifactConfig
    translation: TranslationConfig
    validation: ValidationConfig


def load_config(root: Path) -> Config:
    path = root / "config/default.toml"
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    danbooru = DanbooruConfig(**raw["danbooru"])
    wiki = WikiConfig(**raw["wiki"])
    wikipedia = WikipediaConfig(**raw["wikipedia"])
    ffdkj = SourceConfig(**raw["ffdkj"])
    artifacts = ArtifactConfig(**raw["artifacts"])
    translation = TranslationConfig(**raw["translation"])
    validation = ValidationConfig(**raw["validation"])
    if not danbooru.base_url.startswith("https://"):
        raise ValueError("Danbooru base URL must use HTTPS")
    if danbooru.minimum_post_count < 0:
        raise ValueError("minimum post count must be non-negative")
    if not 1 <= danbooru.page_size <= 1000:
        raise ValueError("page size must be between 1 and 1000")
    if danbooru.request_interval_seconds < 0 or danbooru.timeout_seconds <= 0:
        raise ValueError("request timing values are invalid")
    if danbooru.maximum_retries < 0:
        raise ValueError("maximum retries must be non-negative")
    if not 1 <= wiki.page_size <= 1000:
        raise ValueError("Wiki page size must be between 1 and 1000")
    if wiki.request_interval_seconds < 0 or wiki.timeout_seconds <= 0:
        raise ValueError("Wiki request timing values are invalid")
    if wiki.maximum_retries < 0:
        raise ValueError("Wiki maximum retries must be non-negative")
    if wikipedia.request_interval_seconds < 0 or wikipedia.timeout_seconds <= 0:
        raise ValueError("Wikipedia request timing values are invalid")
    if wikipedia.maximum_retries < 0:
        raise ValueError("Wikipedia maximum retries must be non-negative")
    if ffdkj.timeout_seconds <= 0 or ffdkj.maximum_download_bytes <= 0:
        raise ValueError("ffdkj source limits must be positive")
    if validation.minimum_records < 0:
        raise ValueError("minimum records must be non-negative")
    for value in (
        validation.maximum_record_decrease_ratio,
        validation.maximum_translation_change_ratio,
    ):
        if not 0 <= value <= 1:
            raise ValueError("change ratios must be between 0 and 1")
    return Config(
        danbooru=danbooru,
        wiki=wiki,
        wikipedia=wikipedia,
        ffdkj=ffdkj,
        artifacts=artifacts,
        translation=translation,
        validation=validation,
    )
