# danbooru-tag-zh

[English](https://github.com/kano0222/danbooru-tag-zh/blob/main/README.md)

从 Danbooru 官方接口获取标签，并为 Danbooru Masonry 等网页客户端生成简体中文标签文件。

<img src="https://count.getloli.com/@danbooru-tag-zh?theme=moebooru" alt="Moe Counter">

## 数据集

| 数据集 | 内容 | 状态 |
| --- | --- | --- |
| `ffdkj` | 从 ffdkj `tag.sqlite` 转换的译名 | 可用 |
| `wiki-reviewed` | 来自 Danbooru Wiki、Wikipedia 标题和本地审核的译名 | 本地预览 |

两套译名独立生成，排除画师标签和与原 tag 相同的译名。

## 标签范围

标签清单来自 Danbooru 五个分类中 `post_count >= 10` 的标签；画师仅保留标签数据。无法确定的译名不写入结果。

## 快速开始

安装 [uv](https://docs.astral.sh/uv/) 和 Python 3.12：

```powershell
uv sync --frozen
```

更新 ffdkj 数据并生成产物：

```powershell
uv run danbooru-tag-zh update-ffdkj
uv run danbooru-tag-zh build-artifacts --dataset ffdkj
uv run danbooru-tag-zh validate-artifacts --dataset ffdkj
```

维护 Wiki 审核数据：

```powershell
uv run danbooru-tag-zh sync-tags
uv run danbooru-tag-zh sync-wiki
uv run danbooru-tag-zh sync-wikipedia
uv run danbooru-tag-zh build-candidates
uv run danbooru-tag-zh review
```

## 文档

- [数据获取与候选生成](docs/pipeline.zh-CN.md)
- [人工审核指南](docs/review-guide.zh-CN.md)
- [产物生成与维护](docs/artifacts.zh-CN.md)

## 致谢

感谢 [`ffdkj-Danbooru_Tag-Chinese-English-Translation-Table`](https://github.com/ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table) 的作者允许本项目使用相关数据。

## 开发检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

项目代码使用 MIT 许可证。