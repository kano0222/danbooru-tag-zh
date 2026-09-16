# Manual review guide

[简体中文](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/review-guide.zh-CN.md)

Start the local review interface:

```powershell
uv run danbooru-tag-zh review
```

Decisions are saved in `data/manual/translations.json`; rebuilding candidates does not overwrite manual review.

## Review interface

The interface shows multiple-candidate groups by default, with filters and other-language aliases or Wikipedia titles for reference.

Available actions include:

- click a candidate or press `1`–`9`;
- press `Enter` to save;
- enter a custom concise translation;
- copy the original tag into the input, then adjust capitalization and spacing for a retained term;
- skip the current item;
- mark that no suitable translation exists;
- undo the latest decision.

Prefer an existing Chinese name from a source. Proper names may keep their original spelling with common capitalization; keep translations concise.