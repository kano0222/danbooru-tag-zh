# 产物生成与维护

[English](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/artifacts.md)

## 更新 ffdkj 数据源

```powershell
uv run danbooru-tag-zh update-ffdkj
```

下载并验证 ffdkj `tag.sqlite`，将上游 commit 和校验信息记录在 `data/sources/ffdkj.lock.json`。原始数据库不进入 Git。

使用指定上游版本：

```powershell
uv run danbooru-tag-zh update-ffdkj --commit <40 位 commit SHA>
```

## 生成数据集

```powershell
uv run danbooru-tag-zh build-artifacts --dataset ffdkj
uv run danbooru-tag-zh validate-artifacts --dataset ffdkj
```

产物按来源分开：

| 数据集 | 文件 | 内容 |
| --- | --- | --- |
| `ffdkj` | `artifacts/ffdkj/zh-hans.min.json` | 从上游 `tag.sqlite` 读取的译名 |
| `wiki-reviewed` | `artifacts/wiki-reviewed/zh-hans.min.json` | 从 Wiki 数据和 `data/manual/translations.json` 选出的译名 |

准备好 Wiki 审核数据后，可改用 `--dataset wiki-reviewed` 生成本地预览；`--dry-run` 不写入文件。

两套产物独立生成，排除画师标签和未变化的译名。人工译名优先于 `wiki-reviewed` 的自动候选。

每套产物的 `manifest.json` 记录来源和校验信息。大量删改会停止构建；人工确认结果后才使用 `--accept-large-change`。

## GitHub Actions

工作流每天北京时间 04:17 检查 ffdkj 更新，也可在 `main` 手动触发。有变化且校验、测试通过时，只提交 ffdkj JSON、manifest 和 source lock；`wiki-reviewed` 不自动发布，也不创建 GitHub Release。

基线或候选无效、译名删除超过 0.5%、修改超过 1%，或远端 `main` 已变化时，自动发布会停止。自动流程不会绕过阈值。

本地预览更新：

```powershell
uv run danbooru-tag-zh prepare-ffdkj-update
```

该命令仅准备并校验 ffdkj 更新，不提交或推送。
