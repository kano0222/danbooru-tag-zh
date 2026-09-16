# Artifact building and maintenance

[简体中文](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/artifacts.zh-CN.md)

## Update the ffdkj source

```powershell
uv run danbooru-tag-zh update-ffdkj
```

Downloads and validates ffdkj `tag.sqlite`, recording the upstream commit and checksum in `data/sources/ffdkj.lock.json`. The source database is not committed.

To use a fixed upstream version:

```powershell
uv run danbooru-tag-zh update-ffdkj --commit <40-character commit SHA>
```

## Build datasets

```powershell
uv run danbooru-tag-zh build-artifacts --dataset ffdkj
uv run danbooru-tag-zh validate-artifacts --dataset ffdkj
```

Artifacts are separated by source:

| Dataset | File | Contents |
| --- | --- | --- |
| `ffdkj` | `artifacts/ffdkj/zh-hans.min.json` | Translations read from upstream `tag.sqlite` |
| `wiki-reviewed` | `artifacts/wiki-reviewed/zh-hans.min.json` | Translations selected from Wiki data and `data/manual/translations.json` |

Once Wiki review data is ready, use `--dataset wiki-reviewed` for a local preview. `--dry-run` writes no files.

The datasets are built separately and omit artist tags and unchanged translations. Manual translations take precedence over `wiki-reviewed` automatic candidates.

Each artifact has a `manifest.json` with source and validation details. Large deletions or changes stop the build; use `--accept-large-change` only after reviewing the result.

## GitHub Actions

The workflow checks for ffdkj updates daily at 04:17 Beijing time and can be run manually from `main`. When changes pass validation and tests, it commits only the ffdkj JSON, manifest, and source lock. `wiki-reviewed` is not published automatically, and no GitHub Release is created.

Automatic publication stops if the baseline or candidate is invalid, translations deleted exceed 0.5%, translations changed exceed 1%, or remote `main` has moved. The workflow does not bypass these limits.

To preview an update locally:

```powershell
uv run danbooru-tag-zh prepare-ffdkj-update
```

The command prepares and validates ffdkj changes without committing or pushing.
