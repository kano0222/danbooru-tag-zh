# Manual review guide

[简体中文](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/review-guide.zh-CN.md)

Start the local review interface:

```powershell
uv run danbooru-tag-zh review
```

The service listens locally and saves decisions atomically to `data/manual/translations.json`. Rebuilding candidates does not overwrite this file.

## Review interface

The default view shows multiple-candidate groups ordered by tag usage. Filters cover category, candidate count, review state, and tag name. Other-language aliases and unmatched Wikipedia titles appear beside the candidates for reference.

Available actions include:

- click a candidate or press `1`–`9`;
- press `Enter` to save;
- enter a custom concise translation;
- copy the original tag into the input, then adjust capitalization and spacing for a retained term;
- skip the current item;
- mark that no suitable translation exists;
- undo the latest decision.

Use an existing Chinese name when a source provides one. Product names and titles may retain their original spelling with corrected capitalization, such as `18Trip`. Avoid explanatory text and keep translations concise.