# 题库格式

题库为 JSON 文件。默认查找 `skills/llm-benchmark/test-questions.json`，用户可指定路径。结构：

```json
{
  "meta": {
    "test_name": "LLM 综合能力评测",
    "test_date": "YYYY-MM-DD",
    "description": "可选说明"
  },
  "questions": [
    {
      "id": "info-1",
      "direction": "info_expression",
      "title": "题目名称",
      "prompt": "发给被测模型的题目全文（作答 agent 唯一能看到的内容）",
      "allow_search": true
    }
  ]
}
```

- 方向取值：`info_expression`（信息能力和表达）、`logic_programming`（逻辑编程测试）、`article_writing`（文章编写测试）。
- `allow_search`（可选，默认 false）：`true` 表示该题作答时允许调用 **tavily 搜索 MCP** 联网检索公开资料（用于信息检索类题目）；未标记或为 false 的题目一律禁止联网。

**执行前先校验**：`questions` 非空、`id` 唯一、`direction` 合法、每题 `prompt` 非空。不合格则向用户说明并停止，不进入评测。
