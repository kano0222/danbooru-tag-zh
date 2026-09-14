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

`.github/workflows/build-artifacts.yml` is a manually triggered build. It accepts the latest ffdkj commit or a specified commit, validates the result, and uploads the ffdkj Actions artifact. It does not commit files or create a GitHub Release.

The `wiki-reviewed` dataset remains under local review and is not uploaded by the workflow.