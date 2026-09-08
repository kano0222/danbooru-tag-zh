# danbooru-tag-zh

将 [`ffdkj-Danbooru_Tag-Chinese-English-Translation-Table`](https://github.com/ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table)
中的 `tag.sqlite` 转换为适合网页使用的简体中文标签 JSON。转换过程保留上游有效翻译，并排除中文值与原始 tag 完全相同的记录；不读取 Danbooru Wiki，不调用大模型，也不需要 API Key。

## 本地使用

安装 [uv](https://docs.astral.sh/uv/) 和 Python 3.12，然后执行：

```powershell
uv sync --frozen
uv run danbooru-tag-zh update
```

`update` 会先把 `main` 解析为固定 commit，再下载和校验 SQLite。生成结果写入被 Git 忽略的 `local-dist/`：

- `zh-hans.min.json`：完整的 `英文标签 → 中文翻译` 映射。
- `tags.zh-hans.json.gz`：保留分类和帖子数的完整审计数据。
- `manifest.json`：上游 commit、SQLite SHA-256、记录数及产物哈希。

过滤仅使用精确比较 `cn_name == name`，不会把大小写不同或下划线替换为空格的值视为相同。

差异报告写入 `reports/update-diff.json`。

指定上游 commit 可以复现一次更新：

```powershell
uv run danbooru-tag-zh update --commit <40位commit SHA>
```

也可以转换已经下载的文件：

```powershell
uv run danbooru-tag-zh update --source D:\Downloads\tag.sqlite
```

只检查而不覆盖产物：

```powershell
uv run danbooru-tag-zh update --dry-run
```

验证当前产物或查看统计：

```powershell
uv run danbooru-tag-zh validate
uv run danbooru-tag-zh stats
```

当记录数下降、翻译批量变化或分类消失超过保护阈值时，更新会停止。检查差异后可显式使用 `--accept-large-change`。

## 开发检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

## 数据授权

代码使用 MIT 许可证。上游仓库目前没有明确的数据许可证，因此本工具将产物标记为 `unconfirmed-local-only` 并保持在 Git 忽略目录中。确认复制和再分发授权前，不应提交或公开发布转换结果。详情见 [DATA_LICENSE.md](DATA_LICENSE.md)。
