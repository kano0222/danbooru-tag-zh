# danbooru-tag-zh

Converts `tag.sqlite` from
[`ffdkj-Danbooru_Tag-Chinese-English-Translation-Table`](https://github.com/ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table)
into Simplified Chinese tag JSON suitable for web clients. The conversion preserves upstream
translations unchanged except for excluding rows whose Chinese value exactly equals the original
tag. It does not query the Danbooru Wiki, call an LLM, or require API keys.

## Local usage

Install [uv](https://docs.astral.sh/uv/) and Python 3.12, then run:

```powershell
uv sync --frozen
uv run danbooru-tag-zh update
```

`update` resolves `main` to an immutable commit before downloading and validating the SQLite file.
It writes Git-ignored artifacts to `local-dist/`:

- `zh-hans.min.json`: complete `English tag → Chinese translation` map.
- `tags.zh-hans.json.gz`: complete audit data including category and post count.
- `manifest.json`: upstream commit, SQLite SHA-256, record counts, and artifact hashes.

The filter uses the exact comparison `cn_name == name`; case-only differences and underscore-to-
space values are retained.

The update comparison is written to `reports/update-diff.json`.

Rebuild from a fixed upstream commit:

```powershell
uv run danbooru-tag-zh update --commit <40-character commit SHA>
```

Convert an existing local database:

```powershell
uv run danbooru-tag-zh update --source D:\Downloads\tag.sqlite
```

Validate without replacing artifacts:

```powershell
uv run danbooru-tag-zh update --dry-run
```

Validate current artifacts or show counts:

```powershell
uv run danbooru-tag-zh validate
uv run danbooru-tag-zh stats
```

The update stops when record removal, translation changes, or disappearing categories exceed the
configured safeguards. Inspect the change before explicitly using `--accept-large-change`.

## Development checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

## Data permission

The converter code is MIT licensed. The upstream repository currently has no explicit data license,
so generated artifacts are marked `unconfirmed-local-only` and remain in Git-ignored directories.
Do not commit or publicly redistribute them until copying and redistribution permission is confirmed.
See [DATA_LICENSE.md](DATA_LICENSE.md).
