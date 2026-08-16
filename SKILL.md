---
name: generate-ai-intelligence-daily
description: Collect, verify, deduplicate, rank, and render a daily Chinese AI intelligence and interview-preparation digest with source links and a fixed Markdown format. Use when Codex needs to create or refresh an AI news daily, AI product-manager briefing, interview knowledge cards, simulated interview questions grounded in current sources, or a repeatable daily intelligence workflow without fabricating news, dates, interview experiences, or citations.
---

# Generate AI Intelligence Daily

Produce a source-grounded Markdown daily for AI product managers and job seekers. Treat the format as editorial; treat every factual statement as evidence that must be traceable to an opened source.

## Required reading

- Read [references/source-policy.md](references/source-policy.md) before collecting or verifying information.
- Read [references/configuration.md](references/configuration.md) before changing sources, thresholds, or output limits.
- Use [assets/report-template.md](assets/report-template.md) as the fixed output contract.

## Workflow

1. Resolve the report date, `as_of` time, timezone, lookback window, brand, and output path from `config/sources.json`. Override them only when the user requests it.
2. Collect a candidate pool from enabled sources:
   - Run `scripts/collect_feeds.py` for verified RSS/Atom endpoints.
   - Search official indexes and official domains for sources marked `search`.
   - Use reputable media only to discover or corroborate an event; prefer the original announcement, paper, filing, regulator text, model card, or job description.
3. Open every candidate that may enter the report. Do not rely on a search snippet, aggregator summary, URL slug, or another AI-generated digest.
4. Create verified JSONL records using the schema in `references/configuration.md`. Record the publication timestamp, event date when explicitly known, source tier, canonical URL, evidence URLs, and concise Chinese paraphrases.
5. Apply the evidence rules:
   - Allow one Tier 1 primary source for its own announcement or document.
   - Require two independent domains for a material claim based only on non-primary reporting.
   - Exclude inaccessible, paywalled-only, CAPTCHA-gated, future-dated, stale, or unverified claims when no accessible primary/corroborating evidence exists.
   - Never bypass a paywall, login, robots restriction, or CAPTCHA.
6. Create interview records only after verification:
   - Label questions derived from news, papers, technical posts, or job descriptions as `模拟面试题` or `岗位知识卡`.
   - Label an item `真实面经` only when the source explicitly documents a real interview and provenance is retained. Otherwise do not imply that an invented question was actually asked.
7. Run `scripts/build_report.py`. It validates records, canonicalizes URLs, clusters duplicate events, ranks by freshness/importance/trust/relevance, applies source-diversity caps, and renders the fixed Markdown format.
8. Read the rendered report once. Check each title and summary against its linked evidence, ensure event date and publication date are not conflated, and remove any unsupported adjective, number, ranking, or causal claim.
9. Report omissions honestly. If fewer than 10 news items or 3 interview items pass the threshold, publish fewer; never fill slots with weak or invented material.

## Commands

Run from the skill directory:

```bash
python3 scripts/collect_feeds.py \
  --config config/sources.json \
  --output work/raw-candidates.jsonl

python3 scripts/build_report.py \
  --config config/sources.json \
  --input work/verified-candidates.jsonl \
  --output work/ai-daily.md \
  --audit-output work/ai-daily.audit.json
```

Reproduce the bundled example without network access:

```bash
python3 scripts/build_report.py \
  --config config/sources.json \
  --input examples/verified-candidates.sample.jsonl \
  --output /tmp/ai-daily-example.md \
  --audit-output /tmp/ai-daily-example.audit.json \
  --as-of 2026-08-16T08:00:00+08:00
```

## Non-negotiable output rules

- Preserve clickable original-source links for every news item and interview item.
- Paraphrase briefly; do not copy article bodies or long passages.
- Distinguish `事件日期` from `发布日期`; show `未单独披露` when the event date is not explicit.
- Keep source-backed facts separate from editorial analysis such as `为什么重要`.
- Do not call a source a real interview experience unless the source actually is one.
- Do not produce a poetic closing automatically. Include a closing only when the user supplies or explicitly requests editorial copy.
