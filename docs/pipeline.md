# Data collection and candidate pipeline

[简体中文](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/pipeline.zh-CN.md)

This document explains how `wiki-reviewed` fetches Danbooru data and creates translation candidates.

## 1. Fetch tags

```powershell
uv run danbooru-tag-zh sync-tags
```

Tags are fetched by ID from Danbooru's `/tags.json` and saved to `data/state/tags.sqlite`. Interrupted runs resume automatically; add `--restart` to start over. Run `uv run danbooru-tag-zh validate-tags` to check the completed data.

## 2. Fetch Danbooru Wiki data

```powershell
uv run danbooru-tag-zh sync-wiki
uv run danbooru-tag-zh validate-wiki
```

Public Wiki pages matching non-artist tags are saved to `data/state/wiki.sqlite` as candidate sources; Wiki content is not used directly as a translation.

## 3. Fetch Chinese Wikipedia titles

```powershell
uv run danbooru-tag-zh sync-wikipedia
uv run danbooru-tag-zh validate-wikipedia
```

Only `copyright` and `character` use Wikipedia. Links are classified as:

- `subject`: the linked page identifies the current tag.
- `related`: the link points to source material, an adaptation source, or another related subject.
- `unknown`: the link cannot be matched to the current tag.

Only `subject` Chinese titles enter candidate generation. Add `--restart` after changing Wiki data or classification rules.

## 4. Build candidates

```powershell
uv run danbooru-tag-zh build-candidates
```

Wiki aliases must contain Han characters and no Kana or Hangul. Values changed by OpenCC `t2s` are excluded. Han-only values may still be Japanese and require review.

An explicit Chinese name in the Wiki body selects a unique matching candidate. For works and characters, a `subject` Wikipedia Chinese title can confirm an exact match. Other material remains reference data for manual review.

Continue with the [manual review guide](review-guide.md).