# 人工审核指南

[English](https://github.com/kano0222/danbooru-tag-zh/blob/main/docs/review-guide.md)

启动仅监听本机的审核界面：

```powershell
uv run danbooru-tag-zh review
```

审核决定会原子写入 `data/manual/translations.json`。重新生成候选不会覆盖该文件。

## 审核界面

默认按标签使用量显示多候选项目。可以按分类、候选数量、审核状态和 tag 名筛选。其他语言别名及未匹配的 Wikipedia 标题会显示在候选旁供参考。

可用操作：

- 点击候选或按 `1`～`9`；
- 按 `Enter` 保存；
- 输入自定义短译名；
- 将原 tag 复制到输入框，再调整大小写和空格作为保留原词；
- 暂时跳过；
- 标记无合适译名；
- 撤销上一条决定。

来源中有现成中文名称时采用该名称。产品名和作品名可以保留原文，但应调整为实际使用的大小写，例如 `18Trip`。不要加入解释句，译名尽可能简短。