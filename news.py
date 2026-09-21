"""24h 财经新闻雷达：抓取 Google News 多主题 RSS，去重排序后产出新闻列表。"""
import datetime
import email.utils
import re
import xml.etree.ElementTree as ET

import requests

TOPICS = [
    ("美联储 利率 降息", "宏观利率"),
    ("AI 人工智能 芯片 英伟达", "AI科技"),
    ("中美 关税 贸易", "贸易政策"),
    ("原油 黄金 大宗商品", "大宗商品"),
    ("A股 港股 今日 行情", "中国市场"),
    ("stock market earnings Fed", "美股动态"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
PER_TOPIC = 8
MAX_ITEMS = 40


def fetch_topic(query, topic):
    url = (
        "https://news.google.com/rss/search?q="
        + requests.utils.quote(query)
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    )
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            src = ""
            src_el = it.find("source")
            if src_el is not None and src_el.text:
                src = src_el.text.strip()
            if not title or not pub:
                continue
            try:
                dt = email.utils.parsedate_to_datetime(pub)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                iso = dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
            except Exception:  # noqa: BLE001
                continue
            items.append(
                {
                    "title": title,
                    "sourceName": src,
                    "publishedAt": iso,
                    "link": link,
                    "topic": topic,
                }
            )
            if len(items) >= PER_TOPIC:
                break
    except Exception:  # noqa: BLE001
        pass
    return items


def run(ctx):
    all_items = []
    for query, topic in TOPICS:
        all_items.extend(fetch_topic(query, topic))

    # 按标题去重（保留最新一条）
    best = {}
    for it in all_items:
        key = re.sub(r"\W+", "", it["title"])[:60]
        if key not in best or it["publishedAt"] > best[key]["publishedAt"]:
            best[key] = it
    items = sorted(best.values(), key=lambda x: x["publishedAt"], reverse=True)[:MAX_ITEMS]

    fetched_at = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    return {
        "artifact": {
            "fetchedAt": fetched_at,
            "source": "Google News RSS",
            "topics": [t[1] for t in TOPICS],
            "items": items,
        }
    }
