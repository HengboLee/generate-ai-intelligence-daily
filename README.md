# Generate AI Intelligence Daily

一个可复用的 Codex Skill，用于生成中文 AI 情报与面试日报。

它会按照配置的可信信息源收集候选内容，完成来源核验、去重和排序，保留原始链接，并输出固定格式的 Markdown 日报。未通过核验的内容不会进入日报。

## 主要内容

- `SKILL.md`：完整工作流程
- `config/sources.json`：信息源与筛选配置
- `references/`：来源策略和配置说明
- `scripts/`：采集、去重、排序与生成脚本
- `assets/report-template.md`：固定日报模板
- `examples/`：可复现的示例数据与日报

## 运行示例

```bash
python3 scripts/build_report.py \
  --config config/sources.json \
  --input examples/verified-candidates.sample.jsonl \
  --output /tmp/ai-daily-example.md \
  --audit-output /tmp/ai-daily-example.audit.json \
  --as-of 2026-08-16T08:00:00+08:00
```

详细配置见 [`references/configuration.md`](references/configuration.md)。

## License

[MIT](LICENSE)
