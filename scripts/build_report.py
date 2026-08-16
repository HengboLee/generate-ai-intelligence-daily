#!/usr/bin/env python3
"""Validate, deduplicate, rank, and render a verified AI daily as Markdown."""

import argparse
import datetime as dt
import json
import math
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo


PRIMARY_KINDS = {"official", "regulator", "paper", "company-careers", "user-original"}
QUESTION_TYPES = {"模拟面试题", "岗位知识卡", "真实面经"}
VERIFICATION_STATES = {"confirmed", "corroborated", "unverified"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--as-of", help="ISO-8601 timestamp; defaults to now in configured timezone")
    return parser.parse_args()


def read_jsonl(path: Path) -> List[Dict[str, object]]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{number}: invalid JSON: {exc}")
            record["_line"] = number
            records.append(record)
    return records


def parse_datetime(value: object) -> Optional[dt.datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def valid_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def canonical_url(url: str, dropped: Set[str]) -> str:
    parts = urlsplit(url.strip())
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lower = key.lower()
        if lower in dropped or lower.startswith("utm_"):
            continue
        query.append((key, value))
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def normalize_title(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[\[【(（].*?[\]】)）]", " ", value)
    value = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)
    return value


def ngrams(value: str, size: int = 3) -> Set[str]:
    if len(value) <= size:
        return {value} if value else set()
    return {value[index:index + size] for index in range(len(value) - size + 1)}


def title_similarity(left: str, right: str) -> float:
    left_norm = normalize_title(left)
    right_norm = normalize_title(right)
    if not left_norm or not right_norm:
        return 0.0
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_grams, right_grams = ngrams(left_norm), ngrams(right_norm)
    union = left_grams | right_grams
    jaccard = len(left_grams & right_grams) / len(union) if union else 0.0
    return max(sequence, jaccard)


def freshness_score(age_hours: float) -> float:
    if age_hours <= 24:
        return 5.0
    if age_hours <= 48:
        return 4.5
    if age_hours <= 72:
        return 4.0
    if age_hours <= 168:
        return 2.5
    if age_hours <= 720:
        return 1.0
    return 0.0


def trust_score(record: Dict[str, object]) -> float:
    tier = int(record["source_tier"])
    base = {1: 5.0, 2: 3.5, 3: 2.0}[tier]
    if record.get("verification_status") == "corroborated":
        base += 0.25
    return min(5.0, base)


def independent_domains(urls: Sequence[str]) -> Set[str]:
    return {urlsplit(url).netloc.lower().removeprefix("www.") for url in urls if valid_http_url(url)}


def validate_news(record: Dict[str, object], as_of: dt.datetime, config: Dict[str, object]) -> List[str]:
    errors = []
    required_text = ["id", "title_zh", "summary_zh", "why_it_matters_zh", "topic", "source_name", "source_kind"]
    for field in required_text:
        if not isinstance(record.get(field), str) or not str(record[field]).strip():
            errors.append(f"missing {field}")
    if record.get("status") != "verified":
        errors.append("status is not verified")
    if not valid_http_url(record.get("source_url")):
        errors.append("invalid source_url")
    published = parse_datetime(record.get("published_at"))
    if published is None:
        errors.append("published_at must include timezone")
    elif published > as_of + dt.timedelta(minutes=10):
        errors.append("published_at is in the future")
    event_date = record.get("event_date")
    if event_date is not None:
        try:
            dt.date.fromisoformat(str(event_date))
        except ValueError:
            errors.append("event_date must be YYYY-MM-DD or null")
    tier = record.get("source_tier")
    if not isinstance(tier, int) or tier not in {1, 2, 3}:
        errors.append("source_tier must be 1, 2, or 3")
    for field in ("importance", "relevance"):
        value = record.get(field)
        if not isinstance(value, int) or not 1 <= value <= 5:
            errors.append(f"{field} must be an integer from 1 to 5")
    verification = record.get("verification_status")
    if verification not in VERIFICATION_STATES:
        errors.append("invalid verification_status")
    elif verification == "unverified":
        errors.append("verification_status is unverified")
    evidence = record.get("evidence_urls")
    if not isinstance(evidence, list) or not evidence or not all(valid_http_url(url) for url in evidence):
        errors.append("evidence_urls must contain valid links")
    elif valid_http_url(record.get("source_url")) and canonical_url(record["source_url"], set()) not in {
        canonical_url(url, set()) for url in evidence
    }:
        errors.append("source_url is not present in evidence_urls")
    if record.get("source_kind") not in PRIMARY_KINDS and record.get("major_claim"):
        if verification != "corroborated" or not isinstance(evidence, list) or len(independent_domains(evidence)) < 2:
            errors.append("major non-primary claim lacks two independent domains")
    return errors


def validate_interview(record: Dict[str, object]) -> List[str]:
    errors = []
    required = ["id", "role", "question_zh", "focus_zh"]
    for field in required:
        if not isinstance(record.get(field), str) or not str(record[field]).strip():
            errors.append(f"missing {field}")
    if record.get("status") != "verified":
        errors.append("status is not verified")
    if record.get("question_type") not in QUESTION_TYPES:
        errors.append("invalid question_type")
    if record.get("question_type") == "真实面经" and not record.get("real_interview_provenance"):
        errors.append("真实面经 lacks real_interview_provenance")
    framework = record.get("answer_framework_zh")
    if not isinstance(framework, list) or not framework or not all(isinstance(step, str) and step.strip() for step in framework):
        errors.append("answer_framework_zh must be a non-empty string list")
    urls = record.get("source_urls")
    if not isinstance(urls, list) or not urls or not all(valid_http_url(url) for url in urls):
        errors.append("source_urls must contain valid links")
    for field in ("importance", "relevance"):
        value = record.get(field)
        if not isinstance(value, int) or not 1 <= value <= 5:
            errors.append(f"{field} must be an integer from 1 to 5")
    return errors


def score_news(record: Dict[str, object], as_of: dt.datetime, config: Dict[str, object]) -> float:
    published = parse_datetime(record["published_at"])
    age_hours = max(0.0, (as_of - published.astimezone(as_of.tzinfo)).total_seconds() / 3600)
    weights = config["ranking"]["weights"]
    score = (
        freshness_score(age_hours) * float(weights["freshness"])
        + int(record["importance"]) * float(weights["importance"])
        + trust_score(record) * float(weights["trust"])
        + int(record["relevance"]) * float(weights["relevance"])
    )
    return round(score, 3)


def duplicate(left: Dict[str, object], right: Dict[str, object], config: Dict[str, object]) -> bool:
    if left.get("event_key") and left.get("event_key") == right.get("event_key"):
        return True
    if left["canonical_url"] == right["canonical_url"]:
        return True
    left_date = parse_datetime(left["published_at"])
    right_date = parse_datetime(right["published_at"])
    gap = abs((left_date - right_date).total_seconds()) / 86400
    if gap > float(config["dedupe"]["max_publication_gap_days"]):
        return False
    return title_similarity(str(left["title_zh"]), str(right["title_zh"])) >= float(
        config["dedupe"]["title_similarity_threshold"]
    )


def cluster_news(records: List[Dict[str, object]], config: Dict[str, object]) -> Tuple[List[Dict[str, object]], List[List[str]]]:
    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            if duplicate(records[left], records[right], config):
                union(left, right)

    groups: Dict[int, List[Dict[str, object]]] = {}
    for index, record in enumerate(records):
        groups.setdefault(find(index), []).append(record)

    kept = []
    audit_groups = []
    verification_rank = {"corroborated": 2, "confirmed": 1, "unverified": 0}
    for group in groups.values():
        winner = max(
            group,
            key=lambda item: (
                4 - int(item["source_tier"]),
                verification_rank[str(item["verification_status"])],
                float(item["score"]),
                parse_datetime(item["published_at"]).timestamp(),
            ),
        )
        merged = dict(winner)
        merged_urls = []
        for item in group:
            merged_urls.extend(item.get("evidence_urls", []))
        merged["evidence_urls"] = list(dict.fromkeys(merged_urls))
        kept.append(merged)
        if len(group) > 1:
            audit_groups.append([str(item["id"]) for item in group])
    return kept, audit_groups


def select_news(records: List[Dict[str, object]], config: Dict[str, object]) -> List[Dict[str, object]]:
    report = config["report"]
    minimum = float(config["ranking"]["minimum_score"])
    selected = []
    source_counts: Dict[str, int] = {}
    topic_counts: Dict[str, int] = {}
    for record in sorted(records, key=lambda item: (item["score"], item["published_at"]), reverse=True):
        if float(record["score"]) < minimum:
            continue
        source_id = str(record.get("source_id", record["source_name"]))
        topic = str(record["topic"])
        if source_counts.get(source_id, 0) >= int(report["max_items_per_source"]):
            continue
        if topic_counts.get(topic, 0) >= int(report["max_items_per_topic"]):
            continue
        selected.append(record)
        source_counts[source_id] = source_counts.get(source_id, 0) + 1
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        if len(selected) >= int(report["max_news"]):
            break
    return selected


def select_interviews(records: List[Dict[str, object]], selected_news: List[Dict[str, object]], config: Dict[str, object]) -> List[Dict[str, object]]:
    known_news_ids = {str(item["id"]) for item in selected_news}
    eligible = []
    for record in records:
        refs = {str(value) for value in record.get("source_item_ids", [])}
        if refs and not refs.intersection(known_news_ids):
            continue
        record = dict(record)
        record["score"] = round(int(record["importance"]) * 0.6 + int(record["relevance"]) * 0.4, 3)
        eligible.append(record)
    eligible.sort(key=lambda item: item["score"], reverse=True)
    return eligible[: int(config["report"]["max_interview"])]


def stars(score: float) -> str:
    if score >= 4.25:
        return " ⭐⭐⭐"
    if score >= 3.6:
        return " ⭐⭐"
    return " ⭐"


def md_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().replace("[", "\\[").replace("]", "\\]")


def display_date(record: Dict[str, object], timezone: ZoneInfo) -> str:
    parsed = parse_datetime(record["published_at"])
    return parsed.astimezone(timezone).date().isoformat()


def render_report(
    news: List[Dict[str, object]],
    interviews: List[Dict[str, object]],
    config: Dict[str, object],
    as_of: dt.datetime,
) -> str:
    report = config["report"]
    timezone = ZoneInfo(report["timezone"])
    report_date = as_of.astimezone(timezone).date().isoformat()
    lookback = int(report["lookback_hours"])
    lines = [
        f"# 📊【{report['brand']}】{report_date} AI 情报合集",
        "",
        f"> 统计窗口：过去 {lookback} 小时｜生成时间：{as_of.astimezone(timezone).isoformat(timespec='minutes')}｜通过核验：{len(news)} 条新闻、{len(interviews)} 条面试内容",
        "",
        "## 🌐 AI 大事件日报",
        "",
    ]
    if news:
        overview = "；".join(md_text(item["title_zh"]) for item in news[:3])
        lines.extend([f"**今日速览：** {overview}", "", f"### 🏆 全球 AI 大事件 Top {len(news)}", ""])
        for index, item in enumerate(news, start=1):
            event_date = item.get("event_date") or "未单独披露"
            note = str(item.get("event_date_note", "")).strip()
            if event_date != "未单独披露" and note:
                event_date = f"{event_date}（{note}）"
            lines.append(
                f"{index}. **{md_text(item['title_zh'])}**【事件日期：{event_date}】【发布日期（{report['timezone']}）：{display_date(item, timezone)}】{stars(float(item['score']))}"
            )
            lines.append(f"   - {md_text(item['summary_zh'])}")
            lines.append(f"   - **为什么重要：** {md_text(item['why_it_matters_zh'])}")
            source_links = [f"[{md_text(item['source_name'])}]({item['source_url']})"]
            for url in item.get("evidence_urls", []):
                if canonical_url(url, set()) == canonical_url(str(item["source_url"]), set()):
                    continue
                source_links.append(f"[补充来源 {len(source_links)}]({url})")
            lines.extend([f"   - **来源：** {'、'.join(source_links)}", ""])
    else:
        lines.extend(["**今日速览：** 本统计窗口内没有条目通过核验与评分阈值。", ""])
    if len(news) < int(report["max_news"]):
        lines.extend([f"> 本期仅有 {len(news)} 条通过核验；未用低可信或过期信息补足 Top {report['max_news']}。", ""])

    lines.extend([
        "## 🎯 AI 面试日报",
        "",
        "> 本栏默认是基于已核验新闻、论文、技术文章或官方 JD 生成的模拟题/知识卡，不等同于真实面经。",
        "",
    ])
    if interviews:
        overview = "；".join(md_text(item["question_zh"]) for item in interviews)
        lines.extend([f"**今日速览：** {overview}", "", f"### 🎯 今日面试内容 Top {len(interviews)}", ""])
        for index, item in enumerate(interviews, start=1):
            lines.append(
                f"{index}. **「{md_text(item['question_type'])}｜{md_text(item['role'])}」{md_text(item['question_zh'])}**"
            )
            lines.append(f"   - **考察点：** {md_text(item['focus_zh'])}")
            lines.append("   - **回答框架：**")
            for step in item["answer_framework_zh"]:
                lines.append(f"     - {md_text(step)}")
            links = [f"[来源 {number}]({url})" for number, url in enumerate(item["source_urls"], start=1)]
            lines.extend([f"   - **依据：** {'、'.join(links)}", ""])
    else:
        lines.extend(["**今日速览：** 本期没有证据充分的面试内容。", ""])

    lines.extend([
        "## 核验备注",
        "",
        "- 事件日期与发布日期分开记录；原文未明确事件日期时标注“未单独披露”。",
        f"- 发布日期统一换算为 {report['timezone']}；原始页面日期可保留在事件日期说明中。",
        "- 官方原始材料可单源入选；重大非官方结论至少需要两个独立来源。",
        "- 本日报只保留短摘要和来源链接，不复制原文全文。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    weights_total = sum(float(value) for value in config["ranking"]["weights"].values())
    if not math.isclose(weights_total, 1.0, rel_tol=1e-9):
        raise SystemExit("ranking weights must sum to 1.0")
    timezone = ZoneInfo(config["report"]["timezone"])
    as_of = parse_datetime(args.as_of) if args.as_of else dt.datetime.now(timezone)
    if as_of is None:
        raise SystemExit("--as-of must be a valid ISO-8601 timestamp with timezone")
    as_of = as_of.astimezone(timezone)
    records = read_jsonl(args.input)
    dropped_params = {str(value).lower() for value in config["dedupe"]["drop_query_parameters"]}
    valid_news: List[Dict[str, object]] = []
    valid_interviews: List[Dict[str, object]] = []
    exclusions = []

    for record in records:
        kind = record.get("kind")
        if kind == "news":
            errors = validate_news(record, as_of, config)
            published = parse_datetime(record.get("published_at"))
            if published is not None:
                age_hours = (as_of - published.astimezone(as_of.tzinfo)).total_seconds() / 3600
                maximum_hours = int(config["report"]["tracking_days"]) * 24 if record.get("tracking") else int(
                    config["report"]["lookback_hours"]
                )
                if age_hours > maximum_hours:
                    errors.append("outside freshness window")
            if errors:
                exclusions.append({"id": record.get("id", f"line-{record['_line']}"), "reasons": sorted(set(errors))})
                continue
            item = dict(record)
            item["canonical_url"] = canonical_url(str(item["source_url"]), dropped_params)
            item["score"] = score_news(item, as_of, config)
            valid_news.append(item)
        elif kind == "interview":
            errors = validate_interview(record)
            if errors:
                exclusions.append({"id": record.get("id", f"line-{record['_line']}"), "reasons": sorted(set(errors))})
                continue
            valid_interviews.append(dict(record))
        else:
            exclusions.append({"id": record.get("id", f"line-{record['_line']}"), "reasons": ["unknown kind"]})

    deduplicated, duplicate_groups = cluster_news(valid_news, config)
    selected_news = select_news(deduplicated, config)
    selected_interviews = select_interviews(valid_interviews, selected_news, config)
    report_text = render_report(selected_news, selected_interviews, config, as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report_text, encoding="utf-8")

    audit = {
        "as_of": as_of.isoformat(),
        "input_records": len(records),
        "valid_news_before_dedupe": len(valid_news),
        "news_after_dedupe": len(deduplicated),
        "selected_news": len(selected_news),
        "selected_interviews": len(selected_interviews),
        "duplicate_groups": duplicate_groups,
        "excluded": exclusions,
        "selected_news_ids": [item["id"] for item in selected_news],
        "selected_interview_ids": [item["id"] for item in selected_interviews],
    }
    if args.audit_output:
        args.audit_output.parent.mkdir(parents=True, exist_ok=True)
        args.audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(selected_news)} news and {len(selected_interviews)} interview items to {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
