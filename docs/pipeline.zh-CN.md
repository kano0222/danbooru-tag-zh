# 数据获取与候选生成

[English](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/pipeline.md)

本文说明 `wiki-reviewed` 如何获取 Danbooru 数据并生成翻译候选。

## 1. 获取标签

```powershell
uv run danbooru-tag-zh sync-tags
```

从 Danbooru `/tags.json` 按 ID 分页读取，保存到 `data/state/tags.sqlite`。中断后自动续传；需要重头开始时加 `--restart`。完成后可运行 `uv run danbooru-tag-zh validate-tags` 检查数据。

## 2. 获取 Danbooru Wiki 数据

```powershell
uv run danbooru-tag-zh sync-wiki
uv run danbooru-tag-zh validate-wiki
```

匹配非画师标签的公开 Wiki 页面保存在 `data/state/wiki.sqlite`，作为候选来源；Wiki 内容不会直接成为译名。

## 3. 获取 Wikipedia 中文标题

```powershell
uv run danbooru-tag-zh sync-wikipedia
uv run danbooru-tag-zh validate-wikipedia
```

仅 `copyright` 和 `character` 使用 Wikipedia。链接分为：

- `subject`：链接页面就是当前 tag 对应的主体。
- `related`：链接指向原作、改编来源或其他关联对象。
- `unknown`：无法将链接与当前 tag 对应。

仅 `subject` 的中文标题参与候选生成。Wiki 数据或分类规则变化后，需加 `--restart` 重新同步。

## 4. 生成候选

```powershell
uv run danbooru-tag-zh build-candidates
```

Wiki 别名须包含汉字且不含假名或韩文；OpenCC `t2s` 会改变的值不作为候选。纯汉字也可能是日文，因此仍需审核。

Wiki 正文明示中文名称且唯一匹配候选时会自动选中；作品和角色还可由 `subject` 的 Wikipedia 中文标题确认完全相同的候选。其他内容只供人工参考。

下一步参见[人工审核指南](review-guide.zh-CN.md)。