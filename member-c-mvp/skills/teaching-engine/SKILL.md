---
name: teaching-engine
description: 项目内部教学规则包，独立开发版；不是已安装的 Codex 技能。
---

## For the model

遵守已给定教学动作，不自行提升支持程度。禁止项不得出现在输出中。
问题须绑定来源。解释后请学生重答。来源不足时说明缺失，不编造。

## For maintainers

规则由 Python 纯函数决定。仅 For the model 段注入；本段不注入。
规则表为新起草的 v0.1，尚未与 B 冻结契约。
giveup 只在学生明确确认后传入；off_topic 不加载教学上下文。
本包无模型、网络或写存储能力；内容生成与一次重写由宿主执行。
