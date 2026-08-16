# 配置与数据格式

## 配置文件

主配置为 `config/sources.json`，使用 Python 标准库即可读取。

- `report.brand`：标题品牌，默认“衡见AI”。
- `report.timezone`：IANA 时区，默认 `Asia/Shanghai`。
- `lookback_hours` / `tracking_days`：普通信息与持续跟踪信息的最大年龄。
- `max_news` / `max_interview`：上限，不是必须凑满的数量。
- `max_items_per_source` / `max_items_per_topic`：防止单一公司或主题占满日报。
- `ranking.weights`：时效、重要性、可信度、相关性的权重；总和必须为 1。
- `dedupe`：标题相似阈值、允许的发布日期差和需移除的跟踪参数。
- `sources[].method`：`feed`、`search` 或 `local`。

新增来源前先在浏览器或命令行验证具体 URL。没有确认订阅格式时使用 `search`，不要猜 `feed_url`。

## 原始采集

`collect_feeds.py` 只保存订阅源公开提供的标题、链接、发布时间和短描述，状态为 `raw`。这些记录不能直接发布；必须打开原文并人工或由代理核验后转成以下格式。

## 已核验新闻 JSONL

每行一个 JSON 对象：

```json
{
  "id": "stable-id",
  "kind": "news",
  "status": "verified",
  "title_zh": "有来源支持的中文标题",
  "summary_zh": "对原文的简短中文转述",
  "why_it_matters_zh": "与 AI 产品、行业或求职的关系",
  "topic": "product",
  "source_id": "openai-news",
  "source_name": "OpenAI News",
  "source_kind": "official",
  "source_tier": 1,
  "source_url": "https://example.com/original",
  "published_at": "2026-08-13T19:00:00+08:00",
  "event_date": "2026-08-13",
  "event_date_note": "发布即事件",
  "importance": 4,
  "relevance": 5,
  "verification_status": "confirmed",
  "evidence_urls": ["https://example.com/original"],
  "major_claim": false,
  "tracking": false,
  "event_key": "publisher-product-action-2026-08-13"
}
```

`event_date` 不明确时使用 `null`。`verification_status` 只允许 `confirmed`、`corroborated` 或 `unverified`；最后一种会被排除。Tier 2/3 的 `major_claim: true` 必须是 `corroborated`，且 `evidence_urls` 至少包含两个独立域名。

## 面试 JSONL

```json
{
  "id": "interview-stable-id",
  "kind": "interview",
  "status": "verified",
  "question_type": "模拟面试题",
  "role": "AI 产品经理",
  "question_zh": "如何判断一个超低延迟模型服务是否值得接入？",
  "focus_zh": "模型选型、时延、质量、成本和稳定性的权衡",
  "answer_framework_zh": ["明确业务 SLA", "建立质量与时延评测集", "灰度并监控成本和失败率"],
  "source_item_ids": ["related-news-id"],
  "source_urls": ["https://example.com/original"],
  "importance": 5,
  "relevance": 5
}
```

`question_type` 只允许 `模拟面试题`、`岗位知识卡`、`真实面经`。使用 `真实面经` 时还必须提供 `real_interview_provenance`，说明来源确实记录了真实面试。

## 可复现运行

从 Skill 目录运行：

```bash
python3 scripts/build_report.py \
  --config config/sources.json \
  --input examples/verified-candidates.sample.jsonl \
  --output /tmp/ai-daily-example.md \
  --audit-output /tmp/ai-daily-example.audit.json \
  --as-of 2026-08-16T08:00:00+08:00
```

`audit.json` 会记录输入数、排除原因、去重组和最终入选数，便于复核为什么某条没有进入日报。
