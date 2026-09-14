# 数据获取与候选生成

[English](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/pipeline.md)

本文说明 `wiki-reviewed` 如何获取 Danbooru 数据并生成翻译候选。

## 1. 获取标签

```powershell
uv run danbooru-tag-zh sync-tags
```

程序通过 Danbooru `/tags.json` 接口按 ID 游标分页，默认每秒请求一次，结果保存到 Git 忽略的 `data/state/tags.sqlite`。

中断后会从 `tags.sqlite.partial` 继续。需要丢弃未完成进度时使用 `--restart`：

```powershell
uv run danbooru-tag-zh sync-tags --restart
uv run danbooru-tag-zh validate-tags
uv run danbooru-tag-zh tag-stats
```

只有分页完成并通过 SQLite 完整性、记录数量和分类检查后，正式数据库才会被替换。`tags` 表保存标签 ID、名称、分类、帖子数量、时间和弃用状态。

## 2. 获取 Danbooru Wiki 数据

```powershell
uv run danbooru-tag-zh sync-wiki
uv run danbooru-tag-zh validate-wiki
uv run danbooru-tag-zh wiki-stats
```

程序使用 ID 游标遍历公开 Wiki 页面，将与非 `artist` 标签匹配的页面保存到 `data/state/wiki.sqlite`，包括正文、`other_names`、页面状态、来源 URL 和获取时间。同步中断后会自动续传；`--restart` 会丢弃未完成进度。

Wiki 内容作为来源数据保存，只有被匹配规则或本地审核选中后才成为译名。

## 3. 获取 Wikipedia 中文标题

```powershell
uv run danbooru-tag-zh sync-wikipedia
uv run danbooru-tag-zh validate-wikipedia
uv run danbooru-tag-zh wikipedia-stats
```

只有 `copyright` 和 `character` 使用 Wikipedia。程序根据 tag 名、`other_names` 和链接附近的关系词进行分类：

- `subject`：链接页面就是当前 tag 对应的主体。
- `related`：链接指向原作、改编来源或其他关联对象。
- `unknown`：无法将链接与当前 tag 对应。

只有 `subject` 的中文标题进入候选生成。`related` 和 `unknown` 连同上下文保留在数据库中。Wiki 数据或分类规则变化后，应使用 `--restart` 重新同步。

## 4. 生成候选

```powershell
uv run danbooru-tag-zh build-candidates
uv run danbooru-tag-zh candidate-stats
```

候选提取只保留包含汉字且不包含假名或韩文的 Wiki 别名。OpenCC `t2s` 会改变的值将被排除，不会转换后生成新候选。纯汉字值仍可能是日文，因此只作为候选。

Wiki 正文明示中文名称且唯一匹配一个候选时，程序会自动选择该候选。对于 `copyright` 和 `character`，`subject` 的 Wikipedia 中文标题也可以选择完全相同的候选。`general` 和 `meta` 不使用 Wikipedia，未匹配的 Wikipedia 标题只作为参考。

多候选项目按标签使用量写入 `reports/multiple-candidates.json`。

下一步参见[人工审核指南](review-guide.zh-CN.md)。