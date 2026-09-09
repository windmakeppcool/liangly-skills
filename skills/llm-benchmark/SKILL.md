---
name: llm-benchmark
description: 当需要评测一个对话大模型在信息能力与表达、逻辑编程、文章编写三个方向的能力，且已有 JSON 格式测试题库、需要在 Claude Code 中一键运行、如实记录模型输出并生成 Markdown 报告时使用。
---

# 大模型综合能力评测

## 概述

用用户提供的 JSON 题库，对被测模型（当前会话运行的模型）做评测：每个题目在**干净上下文**的 subagent 中作答并**如实保存输出**（不改写、不润色、不评分），汇总成四部分 Markdown 报告供人工对比。作答 subagent 默认继承当前会话模型。

## 何时使用

- 用户提供 JSON 测试题库，要求评测模型在信息能力和表达、逻辑编程测试、文章编写测试方向的能力
- 需要一份可归档、可多次运行对比的原始输出记录

**不使用**：已有现成评测工具/榜单（如 OpenCompass）时；用户只是随便问几个问题而非正式评测。

## 核心工作流（4 步，严格按序）

1. **确认题库**：读取并校验题库（默认 `skills/llm-benchmark/test-questions.json`，可指定路径）。格式与校验见 **必读：question-format.md**。
2. **确认评测环境**：运行 `claude --version` 记录平台；询问用户被测真实模型名（代理别名如 claude-sonnet-5 可能路由到其他模型，**不要臆造模型名**）。用户不确定时记录为「当前会话默认模型」。
3. **逐题作答并如实保存**：按序一题完成再下一题。每题派 `general-purpose` subagent，prompt 只含该题 `prompt` 字段和「请直接给出你的回答」；`allow_search: true` 的题允许作答 agent 调用 tavily 搜索 MCP 检索公开资料，未标记题禁止联网；主 agent 自己不要作答。输出**原样保存**。防泄题铁律见 **必读：anti-leak.md**。
4. **生成报告**：`mkdir -p` 后保存为 `reports/评测报告-{YYYYMMDD}-{模型名}.md`（可指定路径），四部分固定，详细格式见 **必读：report-format.md**。保存后给用户报告路径和一段摘要。

## 纪律自查

- **必读：anti-leak.md** — 防泄题关键规则（不可违反，违者重做）
- **必读：common-mistakes.md** — 常见错误对照
- **必读：report-format.md** — 报告四部分完整格式
- **必读：question-format.md** — 题库格式、方向取值、allow_search 与校验规则

## 模板

填空模板见 `test-questions.template.json`。
