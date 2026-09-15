# Artifact building and maintenance

[简体中文](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/artifacts.zh-CN.md)

## Update the ffdkj source

```powershell
uv run danbooru-tag-zh update-ffdkj
```

The command resolves upstream `main` to an immutable commit before downloading and validating `tag.sqlite`. The database stays in the Git-ignored cache. The commit, download URL, SQLite SHA-256, record count, retrieval time, and licensing links are written to `data/sources/ffdkj.lock.json`.

To reproduce a fixed source version:

```powershell
uv run danbooru-tag-zh update-ffdkj --commit <40-character commit SHA>
```

## Build datasets

```powershell
uv run danbooru-tag-zh build-artifacts
uv run danbooru-tag-zh validate-artifacts
uv run danbooru-tag-zh artifact-stats
```

Artifacts are separated by source:

| Dataset | File | Contents |
| --- | --- | --- |
| `ffdkj` | `artifacts/ffdkj/zh-hans.min.json` | Translations read from upstream `tag.sqlite` |
| `wiki-reviewed` | `artifacts/wiki-reviewed/zh-hans.min.json` | Translations selected from Wiki data and `data/manual/translations.json` |

Use `--dataset ffdkj` or `--dataset wiki-reviewed` to build one source. `--dry-run` calculates the change without writing.

Both conversions exclude `artist` and translations equivalent to the original tag. Fullwidth parentheses are normalized to ASCII. Values in `data/manual/translations.json` override automatically selected values in `wiki-reviewed`.

Each dataset has its own `manifest.json` with source information, generation time, normalization rules, counts, and the artifact checksum. A large record decrease or translation change stops the build until the result is inspected and `--accept-large-change` is supplied.

## GitHub Actions

`.github/workflows/build-artifacts.yml` runs daily at 04:17 Beijing time and can also be started manually from `main`. Once deployed to GitHub with repository write permission, it automatically commits and pushes validated ffdkj updates; it does not create a GitHub Release. Scheduled runs may be delayed.

The workflow resolves the upstream commit and skips it when it matches the published source lock. Otherwise, it builds in a temporary directory and compares against the currently published JSON using the existing validation. Missing, invalid or empty baselines, invalid or empty candidates, and excessive deletions or translation changes stop the update. The initial conservative limits in `config/default.toml` are 0.5% deleted and 1% modified, each relative to the previous total; adjust them using observed update history. Additions are counted but do not independently block publication. The automatic workflow never uses `--accept-large-change`.

Unchanged content leaves all published files untouched, including the source lock. A new upstream commit with identical content may therefore be checked again on the next run. Changes that pass validation and tests update only the JSON, manifest and source lock. If remote `main` has moved since checkout, publication stops until a later run; there is no automatic rebase or force push. CDN caches may continue serving the previous version for a while.

For local preparation without committing or pushing:

```powershell
uv run danbooru-tag-zh prepare-ffdkj-update
```

This prints the source commit and update result, including change counts when available. Failures are reported in the workflow log and do not publish candidate files. `wiki-reviewed` is not updated by this workflow.
