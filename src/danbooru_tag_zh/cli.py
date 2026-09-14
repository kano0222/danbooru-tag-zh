from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .candidates import build_candidates, candidate_stats
from .config import load_config
from .datasets import build_datasets, update_ffdkj_lock, validate_datasets
from .review import run_review_server
from .storage import (
    database_stats,
    validate_database,
    validate_wiki_database,
    wiki_database_stats,
)
from .syncer import sync_tags
from .wiki_syncer import sync_wiki
from .wikipedia_syncer import (
    sync_wikipedia,
    validate_wikipedia_database,
    wikipedia_database_stats,
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="danbooru-tag-zh")
    result.add_argument(
        "command",
        choices=(
            "sync-tags",
            "validate-tags",
            "tag-stats",
            "sync-wiki",
            "validate-wiki",
            "wiki-stats",
            "sync-wikipedia",
            "validate-wikipedia",
            "wikipedia-stats",
            "build-candidates",
            "candidate-stats",
            "review",
            "update-ffdkj",
            "build-artifacts",
            "validate-artifacts",
            "artifact-stats",
        ),
    )
    result.add_argument("--root", type=Path, default=project_root())
    result.add_argument(
        "--restart", action="store_true", help="discard a partial tag sync and start again"
    )
    result.add_argument("--verbose", action="store_true")
    result.add_argument("--host", default="127.0.0.1")
    result.add_argument("--port", type=int, default=8765)
    result.add_argument("--no-browser", action="store_true")
    result.add_argument("--commit")
    result.add_argument("--dataset", choices=("all", "ffdkj", "wiki-reviewed"), default="all")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--accept-large-change", action="store_true")
    return result


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
    )
    root = args.root.resolve()
    config = load_config(root)
    tag_database = root / config.danbooru.database_path
    wiki_database = root / config.wiki.database_path
    candidate_database = root / config.translation.database_path
    wikipedia_database = root / config.wikipedia.database_path
    result: object
    if args.command == "sync-tags":
        result = sync_tags(root, config, restart=args.restart)
    elif args.command == "validate-tags":
        result = validate_database(tag_database, minimum_records=config.validation.minimum_records)
    elif args.command == "tag-stats":
        if not tag_database.is_file():
            raise ValueError(f"tag database does not exist: {tag_database}")
        result = database_stats(tag_database)
    elif args.command == "sync-wiki":
        result = sync_wiki(root, config, restart=args.restart)
    elif args.command == "validate-wiki":
        result = validate_wiki_database(wiki_database)
    elif args.command == "wiki-stats":
        if not wiki_database.is_file():
            raise ValueError(f"Wiki database does not exist: {wiki_database}")
        result = wiki_database_stats(wiki_database)
    elif args.command == "sync-wikipedia":
        result = sync_wikipedia(root, config, restart=args.restart)
    elif args.command == "validate-wikipedia":
        result = validate_wikipedia_database(wikipedia_database)
    elif args.command == "wikipedia-stats":
        if not wikipedia_database.is_file():
            raise ValueError(f"Wikipedia database does not exist: {wikipedia_database}")
        result = wikipedia_database_stats(wikipedia_database)
    elif args.command == "build-candidates":
        result = build_candidates(root, config)
    elif args.command == "candidate-stats":
        if not candidate_database.is_file():
            raise ValueError(f"candidate database does not exist: {candidate_database}")
        result = candidate_stats(candidate_database)
    elif args.command == "update-ffdkj":
        result = update_ffdkj_lock(root, config, commit=args.commit)
    elif args.command == "build-artifacts":
        result = build_datasets(
            root,
            config,
            dataset=args.dataset,
            dry_run=args.dry_run,
            accept_large_change=args.accept_large_change,
        )
    elif args.command in {"validate-artifacts", "artifact-stats"}:
        manifests = validate_datasets(root, config, dataset=args.dataset)
        result = (
            {name: manifest["records"] for name, manifest in manifests.items()}
            if args.command == "artifact-stats"
            else manifests
        )
    else:
        if not 0 <= args.port <= 65535:
            raise ValueError("review server port must be between 0 and 65535")
        run_review_server(
            candidate_database,
            root / config.translation.manual_decisions_path,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )
        return 0
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
