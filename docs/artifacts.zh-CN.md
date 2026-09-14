# 产物生成与维护

[English](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/artifacts.md)

## 更新 ffdkj 数据源

```powershell
uv run danbooru-tag-zh update-ffdkj
```

命令先将上游 `main` 解析为不可变 commit，再下载并验证 `tag.sqlite`。数据库保存在 Git 忽略缓存中；commit、下载地址、SQLite SHA-256、记录数量、获取时间和授权链接写入 `data/sources/ffdkj.lock.json`。

复现指定来源版本：

```powershell
uv run danbooru-tag-zh update-ffdkj --commit <40 位 commit SHA>
```

## 生成数据集

```powershell
uv run danbooru-tag-zh build-artifacts
uv run danbooru-tag-zh validate-artifacts
uv run danbooru-tag-zh artifact-stats
```

产物按来源分开：

| 数据集 | 文件 | 内容 |
| --- | --- | --- |
| `ffdkj` | `artifacts/ffdkj/zh-hans.min.json` | 从上游 `tag.sqlite` 读取的译名 |
| `wiki-reviewed` | `artifacts/wiki-reviewed/zh-hans.min.json` | 从 Wiki 数据和 `data/manual/translations.json` 选出的译名 |

使用 `--dataset ffdkj` 或 `--dataset wiki-reviewed` 可以只生成一套数据；`--dry-run` 只计算变化，不写入文件。

两套转换都会排除 `artist` 和与原 tag 等价的译名，并将全角括号统一为英文括号。`data/manual/translations.json` 中的译名会覆盖 `wiki-reviewed` 的自动选择结果。

每套数据各有一个 `manifest.json`，记录数据来源、生成时间、规范化规则、数量和产物哈希。记录大量减少或译名大范围变化时，构建会停止；检查结果后才能使用 `--accept-large-change`。

## GitHub Actions

`.github/workflows/build-artifacts.yml` 是手动触发的构建流程。它可以使用 ffdkj 最新 commit 或指定 commit，验证后上传 ffdkj Actions artifact，不会自动提交文件或创建 GitHub Release。

`wiki-reviewed` 仍在本地审核，不会由工作流上传。