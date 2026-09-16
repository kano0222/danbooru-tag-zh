# 人工审核指南

[English](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/review-guide.md)

启动本地审核界面：

```powershell
uv run danbooru-tag-zh review
```

决定保存在 `data/manual/translations.json`，重新生成候选不会覆盖人工审核。

## 审核界面

界面默认显示多候选项目，可筛选并查看其他语言别名及 Wikipedia 标题。

可用操作：

- 点击候选或按 `1`～`9`；
- 按 `Enter` 保存；
- 输入自定义短译名；
- 将原 tag 复制到输入框，再调整大小写和空格作为保留原词；
- 暂时跳过；
- 标记无合适译名；
- 撤销上一条决定。

来源中有现成中文名称时优先采用。专名可保留原文，并使用通行大小写；译名保持简短。