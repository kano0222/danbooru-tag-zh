from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SourceConfig:
    repository: str
    branch: str
    database_path: str
    timeout_seconds: float
    maximum_download_bytes: int


@dataclass(frozen=True, slots=True)
class ValidationConfig:
    minimum_records: int
    maximum_record_decrease_ratio: float
    maximum_translation_change_ratio: float


@dataclass(frozen=True, slots=True)
class OutputConfig:
    directory: str
    report_directory: str


@dataclass(frozen=True, slots=True)
class Config:
    source: SourceConfig
    validation: ValidationConfig
    output: OutputConfig


def load_config(root: Path) -> Config:
    path = root / "config/default.toml"
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    source = SourceConfig(**raw["source"])
    validation = ValidationConfig(**raw["validation"])
    output = OutputConfig(**raw["output"])
    if source.timeout_seconds <= 0 or source.maximum_download_bytes <= 0:
        raise ValueError("source limits must be positive")
    if validation.minimum_records < 0:
        raise ValueError("minimum_records must be non-negative")
    for value in (
        validation.maximum_record_decrease_ratio,
        validation.maximum_translation_change_ratio,
    ):
        if not 0 <= value <= 1:
            raise ValueError("change ratios must be between 0 and 1")
    return Config(source, validation, output)
