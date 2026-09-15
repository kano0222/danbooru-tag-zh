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

`.github/workflows/build-artifacts.yml` 每天北京时间 04:17 运行，也可以从 `main` 手动触发。部署到 GitHub 且具备仓库写入权限后，会自动提交并推送通过检查的 ffdkj 更新，不创建 GitHub Release。定时运行可能延迟。

工作流先解析上游 commit，与已发布 source lock 相同时跳过。否则在临时目录构建，复用现有校验，与当前已发布 JSON 比较。基线缺失、损坏或为空，候选无效或为空，以及删除或改译超限都会停止更新。`config/default.toml` 中的初始保守门槛为删除 0.5%、修改 1%，均以旧词库总数为分母，后续根据实际更新历史调整。新增数量仅统计，不独立阻断。自动流程不使用 `--accept-large-change`。

内容没有变化时不修改任何发布文件，包括 source lock，因此上游新 commit 产生相同内容时，下次可能再次检查。校验和测试通过后，只提交 JSON、manifest 和 source lock；若远端 `main` 在检出后发生变化，则停止发布，留待后续运行，不自动 rebase 或强推。CDN 缓存可能暂时继续返回旧版。

本地准备更新、不提交或推送：

```powershell
uv run danbooru-tag-zh prepare-ffdkj-update
```

命令输出来源 commit 和更新结果，有差异统计时一并输出。失败原因写入工作流日志，候选文件不会发布。`wiki-reviewed` 不由此工作流更新。
