# -*- coding: utf-8 -*-
"""
ai-news-radar: 每日自动抓取 AI 新闻并生成聚合摘要。

用法:
  python radar.py                        # 抓取新闻，输出 Markdown
  python radar.py --summarize            # 抓取 + LLM 摘要
  python radar.py --publish              # 抓取 + 发布为 GitHub Issue
  python radar.py --summarize --publish  # 抓取 + 摘要 + 发布
"""
import argparse
import html
import os
import re
import json
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import yaml
import requests
from dateutil import parser as dateparser

FEEDS_PATH = Path(__file__).parent / "sources" / "feeds.yaml"
OUTPUT_DIR = Path(__file__).parent / "output"
SEEN_FILE = Path(__file__).parent / "output" / ".seen_hashes.json"

AI_KEYWORDS = [
    "ai", "artificial intelligence", "llm", "gpt", "claude", "gemini",
    "machine learning", "deep learning", "neural", "openai", "anthropic",
    "大模型", "人工智能", "机器学习", "深度学习", "智能体", "agent",
    "transformer", "diffusion", "stable diffusion", "midjourney", "sora",
    "copilot", "chatbot", "rag", "fine-tune", "微调", "向量",
]

MAX_ITEMS_PER_FEED = 20
MAX_AGE_HOURS = 48


def load_feeds(path=FEEDS_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["feeds"]


def content_hash(title, link):
    raw = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


def load_seen():
    if SEEN_FILE.exists():
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def is_ai_related(title, summary=""):
    text = f"{title} {summary}".lower()
    return any(kw in text for kw in AI_KEYWORDS)


def clean_html(raw):
    text = re.sub(r"<[^>]+>", "", raw or "")
    return html.unescape(text).strip()


def parse_published(entry):
    for attr in ("published_parsed", "updated_parsed"):
        tp = getattr(entry, attr, None)
        if tp:
            from time import mktime
            return datetime.fromtimestamp(mktime(tp), tz=timezone.utc)
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return dateparser.parse(val)
            except Exception:
                pass
    return None


def fetch_feed(feed_cfg):
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)

    try:
        parsed = feedparser.parse(feed_cfg["url"])
    except Exception as e:
        print(f"  [ERROR] {feed_cfg['name']}: {e}")
        return items

    for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
        title = clean_html(getattr(entry, "title", ""))
        link = getattr(entry, "link", "")
        summary = clean_html(getattr(entry, "summary", ""))
        pub_date = parse_published(entry)

        if not title or not link:
            continue

        if pub_date and pub_date.tzinfo and pub_date < cutoff:
            continue

        if feed_cfg.get("category") != "学术论文" and not is_ai_related(title, summary):
            continue

        if len(summary) > 300:
            summary = summary[:297] + "..."

        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "source": feed_cfg["name"],
            "category": feed_cfg.get("category", "其他"),
            "lang": feed_cfg.get("lang", "en"),
            "published": pub_date.isoformat() if pub_date else "",
            "hash": content_hash(title, link),
        })

    return items


def fetch_all(feeds):
    all_items = []
    seen = load_seen()
    new_seen = set(seen)

    for feed_cfg in feeds:
        print(f"  Fetching: {feed_cfg['name']} ...")
        items = fetch_feed(feed_cfg)
        for item in items:
            if item["hash"] not in seen:
                all_items.append(item)
                new_seen.add(item["hash"])
        print(f"    → {len(items)} items")

    save_seen(new_seen)

    all_items.sort(key=lambda x: x.get("published", ""), reverse=True)
    return all_items


def summarize_with_llm(items):
    api_key = os.environ.get("LLM_API_KEY")
    api_base = os.environ.get("LLM_API_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    if not api_key:
        print("  [WARN] LLM_API_KEY not set, skipping summarization")
        return None

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=api_base)

    news_text = ""
    for i, item in enumerate(items[:40], 1):
        news_text += f"{i}. [{item['source']}] {item['title']}\n"
        if item["summary"]:
            news_text += f"   {item['summary'][:150]}\n"
        news_text += f"   链接: {item['link']}\n\n"

    prompt = f"""你是一位资深AI行业编辑。以下是今天抓取到的 AI 相关新闻条目，请你：

1. 从中筛选出最重要、最有价值的 8-15 条新闻
2. 按重要性排序
3. 为每条新闻写一段简洁的中文摘要（2-3句话）
4. 按以下分类整理：行业动态、产品发布、开源生态、学术论文、其他

输出格式（Markdown）：
## 🔥 重点新闻
### 1. [新闻标题]
摘要内容...
> 来源：[来源名] | [链接]

---

今日新闻原始条目：
{news_text}"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"  [ERROR] LLM summarization failed: {e}")
        return None


def generate_raw_markdown(items, date_str):
    lines = [f"# AI 新闻雷达 - {date_str}\n"]
    lines.append(f"共抓取到 **{len(items)}** 条 AI 相关新闻\n")
    lines.append("---\n")

    categories = {}
    for item in items:
        cat = item["category"]
        categories.setdefault(cat, []).append(item)

    cat_order = ["行业动态", "官方动态", "开源生态", "深度报道", "社区热议", "学术论文", "其他"]
    for cat in cat_order:
        if cat not in categories:
            continue
        lines.append(f"\n## {cat}\n")
        for item in categories[cat]:
            lines.append(f"### {item['title']}")
            if item["summary"]:
                lines.append(f"\n{item['summary']}\n")
            lines.append(f"> 来源：{item['source']} | [链接]({item['link']})\n")

    return "\n".join(lines)


def generate_daily_report(items, date_str, llm_summary=None):
    if llm_summary:
        header = f"# AI 新闻雷达 - {date_str}（LLM 精选）\n\n"
        header += f"共抓取 {len(items)} 条，以下为 LLM 精选摘要：\n\n---\n\n"
        return header + llm_summary
    return generate_raw_markdown(items, date_str)


def publish_to_issue(content, date_str, repo_name=None):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("G_T")
    repo = repo_name or os.environ.get("RADAR_REPO")

    if not token or not repo:
        print("  [WARN] GITHUB_TOKEN/G_T and RADAR_REPO not set, skipping publish")
        return None

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "title": f"AI 新闻雷达 - {date_str}",
        "body": content,
        "labels": ["radar"],
    }

    try:
        resp = requests.post(url, headers=headers, json=data)
        resp.raise_for_status()
        issue_url = resp.json().get("html_url")
        print(f"  Published: {issue_url}")
        return issue_url
    except Exception as e:
        print(f"  [ERROR] Publish failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="AI News Radar")
    parser.add_argument("--summarize", action="store_true", help="Use LLM to summarize")
    parser.add_argument("--publish", action="store_true", help="Publish as GitHub Issue")
    parser.add_argument("--repo", help="Target repo for publishing (owner/repo)")
    parser.add_argument("--hours", type=int, default=None, help="Max age in hours")
    args = parser.parse_args()

    if args.hours is not None:
        global MAX_AGE_HOURS
        MAX_AGE_HOURS = args.hours

    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"\n🔍 AI News Radar - {date_str}")
    print("=" * 50)

    feeds = load_feeds()
    print(f"\n📡 Fetching from {len(feeds)} sources...")
    items = fetch_all(feeds)
    print(f"\n📰 Total: {len(items)} new items")

    llm_summary = None
    if args.summarize:
        print("\n🤖 Generating LLM summary...")
        llm_summary = summarize_with_llm(items)

    report = generate_daily_report(items, date_str, llm_summary)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"radar_{date_str}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n💾 Saved: {output_file}")

    if args.publish:
        print("\n📤 Publishing to GitHub Issue...")
        publish_to_issue(report, date_str, args.repo)

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
