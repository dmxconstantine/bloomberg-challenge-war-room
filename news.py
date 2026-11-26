"""24h 财经新闻雷达：抓取 Google News 多主题双语 RSS，去重排序后产出新闻列表。

来源扩充：中文 6 主题 + 英文 7 主题，每条新闻带 lang 标记，
前端按界面语言过滤展示。
"""
import datetime
import email.utils
import re
import xml.etree.ElementTree as ET

import requests

# (查询词, 主题, 语言)
TOPICS = [
    # 中文源
    ("美联储 利率 降息", "宏观利率", "zh"),
    ("AI 人工智能 芯片 英伟达", "AI科技", "zh"),
    ("中美 关税 贸易", "贸易政策", "zh"),
    ("原油 黄金 大宗商品", "大宗商品", "zh"),
    ("A股 港股 行情", "中国市场", "zh"),
    ("半导体 存储 涨价", "半导体", "zh"),
    # 英文源（国际视野）
    ("Federal Reserve interest rate decision", "宏观利率", "en"),
    ("Nvidia AI chips semiconductor", "AI科技", "en"),
    ("oil gold commodity prices OPEC", "大宗商品", "en"),
    ("China stock market economy stimulus", "中国市场", "en"),
    ("US stock market earnings Wall Street", "美股动态", "en"),
    ("ECB Europe economy inflation", "欧洲经济", "en"),
    ("Bitcoin cryptocurrency ETF", "加密资产", "en"),
]

LOCALE = {
    "zh": ("zh-CN", "CN", "CN:zh-Hans"),
    "en": ("en-US", "US", "US:en"),
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
PER_TOPIC = 8
MAX_ITEMS = 60


def fetch_topic(query, topic, lang):
    hl, gl, ceid = LOCALE.get(lang, LOCALE["zh"])
    url = (
        "https://news.google.com/rss/search?q="
        + requests.utils.quote(query)
        + f"&hl={hl}&gl={gl}&ceid={ceid}"
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
                    "lang": lang,
                }
            )
            if len(items) >= PER_TOPIC:
                break
    except Exception:  # noqa: BLE001
        pass
    return items


def run(ctx):
    all_items = []
    for query, topic, lang in TOPICS:
        all_items.extend(fetch_topic(query, topic, lang))

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
            "source": "Google News RSS · 双语源 CN+EN",
            "topics": sorted({t[1] for t in TOPICS}),
            "items": items,
        }
    }
