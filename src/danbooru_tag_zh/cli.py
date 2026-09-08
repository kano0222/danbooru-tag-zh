from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import load_config
from .downloader import acquire_database
from .exporter import (
    build_artifacts,
    compare_records,
    load_previous_records,
    validate_artifacts,
    write_files,
)
from .importer import exclude_unchanged_translations, import_records


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="danbooru-tag-zh")
    result.add_argument("command", choices=("update", "validate", "stats"))
    result.add_argument("--root", type=Path, default=project_root())
    source = result.add_mutually_exclusive_group()
    source.add_argument("--commit")
    source.add_argument("--source", type=Path)
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--accept-large-change", action="store_true")
    result.add_argument("--verbose", action="store_true")
    return result


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
    )
    root = args.root.resolve()
    config = load_config(root)
    output = root / config.output.directory
    if args.command == "validate":
        manifest = validate_artifacts(output)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    if args.command == "stats":
        manifest = validate_artifacts(output)
        print(json.dumps(manifest["records"], ensure_ascii=False, indent=2))
        return 0
    database, source = acquire_database(root, config.source, commit=args.commit, source=args.source)
    source_records = import_records(database, minimum_records=config.validation.minimum_records)
    records, excluded_unchanged = exclude_unchanged_translations(source_records)
    previous = load_previous_records(output)
    previous_commit: str | None = None
    previous_manifest = output / "manifest.json"
    if previous_manifest.exists():
        previous_data = json.loads(previous_manifest.read_text(encoding="utf-8"))
        previous_source = previous_data.get("source") if isinstance(previous_data, dict) else None
        if isinstance(previous_source, dict) and isinstance(previous_source.get("commit"), str):
            previous_commit = previous_source["commit"]
    difference = compare_records(
        previous,
        records,
        config.validation,
        accept_large_change=args.accept_large_change,
    )
    difference["previous_commit"] = previous_commit
    difference["current_commit"] = source.commit
    files, manifest = build_artifacts(
        records,
        source,
        source_record_count=len(source_records),
        excluded_unchanged=excluded_unchanged,
    )
    result = {"source": manifest["source"], "records": manifest["records"], "diff": difference}
    if not args.dry_run:
        write_files(output, files)
        report = json.dumps(difference, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        write_files(root / config.output.report_directory, {"update-diff.json": report})
        validate_artifacts(output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    try:
        raise SystemExit(run(parser().parse_args()))
    except (ValueError, RuntimeError, OSError) as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
