# danbooru-tag-zh

[简体中文](https://github.com/kano0222/danbooru-tag-zh/blob/main/README.zh-CN.md)

Fetches Danbooru tags and builds Simplified Chinese tag files for web clients such as Danbooru Masonry.

## Datasets

| Dataset | Contents | Status |
| --- | --- | --- |
| `ffdkj` | Translations converted from ffdkj `tag.sqlite` | Available |
| `wiki-reviewed` | Names from Danbooru Wiki, Wikipedia titles, and local review | Local preview |

The datasets are built separately and omit artist tags and translations identical to the original tag.

## Tag scope

The inventory contains Danbooru tags with `post_count >= 10` from all five categories; artist tags remain inventory data only. Entries without a clear translation are omitted.

## Quick start

Install [uv](https://docs.astral.sh/uv/) and Python 3.12:

```powershell
uv sync --frozen
```

Update the ffdkj source and build its artifact:

```powershell
uv run danbooru-tag-zh update-ffdkj
uv run danbooru-tag-zh build-artifacts --dataset ffdkj
uv run danbooru-tag-zh validate-artifacts --dataset ffdkj
```

To work on the Wiki-reviewed dataset:

```powershell
uv run danbooru-tag-zh sync-tags
uv run danbooru-tag-zh sync-wiki
uv run danbooru-tag-zh sync-wikipedia
uv run danbooru-tag-zh build-candidates
uv run danbooru-tag-zh review
```

## Documentation

- [Data collection and candidate pipeline](docs/pipeline.md)
- [Manual review guide](docs/review-guide.md)
- [Artifact building and maintenance](docs/artifacts.md)

## Credits

Thanks to the author of [`ffdkj-Danbooru_Tag-Chinese-English-Translation-Table`](https://github.com/ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table) for allowing this project to use relevant data.

## Development checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

The project code is MIT licensed.