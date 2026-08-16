#!/usr/bin/env python3
"""Collect public RSS/Atom metadata into raw JSONL candidates."""

import argparse
import datetime as dt
import email.utils
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--as-of", help="ISO-8601 timestamp; defaults to now")
    parser.add_argument("--lookback-hours", type=int)
    parser.add_argument("--source", action="append", default=[], help="Source id; repeatable")
    parser.add_argument("--allow-empty", action="store_true")
    return parser.parse_args()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(element):
        if local_name(child.tag) in wanted and child.text:
            return child.text.strip()
    return ""


def clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_timestamp(value: str) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def atom_link(entry: ET.Element) -> str:
    fallback = ""
    for child in list(entry):
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "").strip()
        rel = child.attrib.get("rel", "alternate")
        if href and rel == "alternate":
            return href
        if href and not fallback:
            fallback = href
    return fallback


def parse_feed(payload: bytes) -> Iterable[Dict[str, object]]:
    root = ET.fromstring(payload)
    root_name = local_name(root.tag)
    if root_name == "rss" or any(local_name(child.tag) == "channel" for child in root):
        channel = next((child for child in root if local_name(child.tag) == "channel"), root)
        entries = [child for child in channel if local_name(child.tag) == "item"]
        for entry in entries:
            published = child_text(entry, "pubdate", "published", "updated")
            categories = [clean_html(child.text or "") for child in entry if local_name(child.tag) == "category"]
            yield {
                "title": clean_html(child_text(entry, "title")),
                "url": child_text(entry, "link") or child_text(entry, "guid"),
                "published_at": parse_timestamp(published),
                "summary": clean_html(child_text(entry, "description", "summary", "content")),
                "tags": [tag for tag in categories if tag],
            }
        return

    entries = [child for child in root.iter() if local_name(child.tag) == "entry"]
    for entry in entries:
        published = child_text(entry, "published", "updated")
        categories = [child.attrib.get("term", "").strip() for child in entry if local_name(child.tag) == "category"]
        yield {
            "title": clean_html(child_text(entry, "title")),
            "url": atom_link(entry),
            "published_at": parse_timestamp(published),
            "summary": clean_html(child_text(entry, "summary", "content")),
            "tags": [tag for tag in categories if tag],
        }


def fetch(url: str, config: Dict[str, object]) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": str(config["user_agent"])})
    with urllib.request.urlopen(request, timeout=int(config["timeout_seconds"])) as response:
        maximum = int(config["max_feed_bytes"])
        payload = response.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError(f"feed exceeds max_feed_bytes={maximum}")
    return payload


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    collection = config["collection"]
    report = config["report"]
    as_of = parse_timestamp(args.as_of) if args.as_of else dt.datetime.now(dt.timezone.utc)
    if as_of is None:
        raise SystemExit("--as-of must be a valid ISO-8601 timestamp")
    lookback = args.lookback_hours or int(report["lookback_hours"])
    earliest = as_of - dt.timedelta(hours=lookback)
    selected_ids = set(args.source)
    records: List[Dict[str, object]] = []
    failures: List[str] = []

    for source in config["sources"]:
        if not source.get("enabled") or source.get("method") != "feed":
            continue
        if selected_ids and source["id"] not in selected_ids:
            continue
        try:
            payload = fetch(source["feed_url"], collection)
            parsed = list(parse_feed(payload))[: int(collection["max_items_per_feed"])]
        except Exception as exc:  # Surface partial failures; do not hide them.
            failures.append(f"{source['id']}: {exc}")
            continue
        for item in parsed:
            published = item["published_at"]
            if not item["title"] or not item["url"] or published is None:
                continue
            if published < earliest or published > as_of + dt.timedelta(minutes=10):
                continue
            records.append({
                "schema_version": 1,
                "kind": "news",
                "status": "raw",
                "source_id": source["id"],
                "source_name": source["name"],
                "source_kind": source["kind"],
                "source_tier": source["tier"],
                "title_raw": item["title"],
                "summary_raw": item["summary"],
                "source_url": item["url"],
                "published_at": published.isoformat(),
                "tags": item["tags"],
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "discovery_method": "feed"
            })

    records.sort(key=lambda record: record["published_at"], reverse=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    for failure in failures:
        print(f"WARN {failure}", file=sys.stderr)
    print(f"Wrote {len(records)} raw candidates to {args.output}", file=sys.stderr)
    if not records and not args.allow_empty:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
