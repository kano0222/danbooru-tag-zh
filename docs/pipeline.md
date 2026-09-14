# Data collection and candidate pipeline

[简体中文](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/pipeline.zh-CN.md)

This document explains how `wiki-reviewed` fetches Danbooru data and creates translation candidates.

## 1. Fetch tags

```powershell
uv run danbooru-tag-zh sync-tags
```

The command follows ID cursor pagination through Danbooru's `/tags.json` endpoint and defaults to one request per second. It stores the Git-ignored database at `data/state/tags.sqlite`.

An interrupted run resumes from `tags.sqlite.partial`. Use `--restart` to discard partial progress:

```powershell
uv run danbooru-tag-zh sync-tags --restart
uv run danbooru-tag-zh validate-tags
uv run danbooru-tag-zh tag-stats
```

The completed database replaces the previous version only after pagination, SQLite integrity, record-count, and category checks pass. The `tags` table stores identifiers, names, categories, post counts, timestamps, and deprecation state.

## 2. Fetch Danbooru Wiki data

```powershell
uv run danbooru-tag-zh sync-wiki
uv run danbooru-tag-zh validate-wiki
uv run danbooru-tag-zh wiki-stats
```

The sync walks public Wiki pages with an ID cursor and stores pages matching non-`artist` tags at `data/state/wiki.sqlite`. It retains the body, `other_names`, page state, source URL, and retrieval time. Interrupted runs resume automatically; `--restart` discards partial progress.

Wiki content is stored as source data. It becomes a translation only after a matching rule or local review selects it.

## 3. Fetch Chinese Wikipedia titles

```powershell
uv run danbooru-tag-zh sync-wikipedia
uv run danbooru-tag-zh validate-wikipedia
uv run danbooru-tag-zh wikipedia-stats
```

Only `copyright` and `character` pages use Wikipedia. Links are classified from the tag name, `other_names`, and nearby relationship phrases:

- `subject`: the linked page identifies the current tag.
- `related`: the link points to source material, an adaptation source, or another related subject.
- `unknown`: the link cannot be matched to the current tag.

Only `subject` titles enter candidate generation. `related` and `unknown` links remain in the database with their context. Run with `--restart` after changing Wiki data or classification rules.

## 4. Build candidates

```powershell
uv run danbooru-tag-zh build-candidates
uv run danbooru-tag-zh candidate-stats
```

Candidate extraction keeps Wiki aliases containing Han characters but no Kana or Hangul. Values that OpenCC would change under `t2s` are excluded instead of being converted into new candidates. A Han-only value remains a candidate because it may still be Japanese.

A candidate is selected automatically when the Wiki body labels a Chinese name and uniquely matches one candidate. For `copyright` and `character`, a `subject` Wikipedia Chinese title can also select an exact match. `general` and `meta` do not use Wikipedia. Unmatched Wikipedia titles remain references.

Groups with multiple candidates are written to `reports/multiple-candidates.json` in descending tag usage order.

Continue with the [manual review guide](review-guide.md).