"""重点关注股票池：动量 + 量能 + 新闻热度综合打分，选出 Top 关注标的。"""
import datetime
import email.utils
import re
import warnings
import xml.etree.ElementTree as ET

warnings.filterwarnings("ignore")

import requests
import yfinance as yf

# (ticker, 名称, 市场, 主题, 新闻关键词)
UNIVERSE = [
    ("688981.SS", "中芯国际", "A股", "半导体", ["中芯", "芯片", "半导体"]),
    ("688256.SS", "寒武纪", "A股", "AI算力", ["寒武纪", "AI", "算力"]),
    ("601138.SS", "工业富联", "A股", "AI算力", ["工业富联", "AI", "服务器"]),
    ("300308.SZ", "中际旭创", "A股", "光模块", ["中际旭创", "光模块", "CPO"]),
    ("002475.SZ", "立讯精密", "A股", "消费电子", ["立讯", "苹果", "消费电子"]),
    ("300750.SZ", "宁德时代", "A股", "新能源", ["宁德", "电池", "新能源"]),
    ("002594.SZ", "比亚迪", "A股", "新能源车", ["比亚迪", "电动车", "新能源车"]),
    ("300274.SZ", "阳光电源", "A股", "新能源", ["阳光电源", "储能", "光伏"]),
    ("601899.SS", "紫金矿业", "A股", "有色金属", ["紫金", "铜", "金"]),
    ("600519.SS", "贵州茅台", "A股", "消费", ["茅台", "白酒", "消费"]),
    ("600036.SS", "招商银行", "A股", "银行", ["招商银行", "银行"]),
    ("601857.SS", "中国石油", "A股", "能源", ["中国石油", "油"]),
    ("0700.HK", "腾讯控股", "港股", "互联网", ["腾讯", "游戏"]),
    ("9988.HK", "阿里巴巴", "港股", "互联网", ["阿里", "云"]),
    ("3690.HK", "美团", "港股", "互联网", ["美团"]),
    ("1810.HK", "小米集团", "港股", "消费电子", ["小米", "汽车"]),
    ("0981.HK", "中芯国际H", "港股", "半导体", ["中芯", "芯片", "半导体"]),
    ("1211.HK", "比亚迪股份", "港股", "新能源车", ["比亚迪", "电动车"]),
    ("NVDA", "英伟达", "美股", "AI算力", ["Nvidia", "英伟达", "AI", "GPU"]),
    ("AMD", "AMD", "美股", "半导体", ["AMD", "芯片"]),
    ("AVGO", "博通", "美股", "半导体", ["Broadcom", "博通"]),
    ("MSFT", "微软", "美股", "互联网", ["Microsoft", "微软"]),
    ("AAPL", "苹果", "美股", "消费电子", ["Apple", "苹果"]),
    ("TSLA", "特斯拉", "美股", "新能源车", ["Tesla", "特斯拉"]),
    ("AMZN", "亚马逊", "美股", "互联网", ["Amazon", "亚马逊"]),
    ("META", "Meta", "美股", "互联网", ["Meta"]),
    ("GOOGL", "谷歌", "美股", "互联网", ["Google", "谷歌"]),
    ("PLTR", "Palantir", "美股", "AI软件", ["Palantir", "AI"]),
    ("LLY", "礼来", "美股", "医药", ["Eli Lilly", "减肥药"]),
    ("JPM", "摩根大通", "美股", "银行", ["JPMorgan", "银行"]),
]

NEWS_QUERIES = [
    ("AI 芯片 算力", "AI科技"),
    ("半导体 中芯 台积电", "半导体"),
    ("新能源 电池 储能", "新能源"),
    ("黄金 铜 原油 大宗", "大宗"),
    ("央行 降息 美联储", "宏观"),
    ("earnings Nvidia Tesla Apple", "美股业绩"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
SIGNAL_EN = {
    "放量上攻": "Breakout w/ volume",
    "短线强势": "Short-term strength",
    "趋势走强": "Uptrend intact",
    "接近新高": "Near 20d high",
    "短线回调": "Pullback",
    "震荡观察": "Watchlist",
}

DISCLAIMER = (
    "机器打分仅供参考，不构成投资建议；Bloomberg Challenge 模拟交易请结合团队独立判断。"
    " | Model scores for reference only, not investment advice; make independent team decisions."
)

TOP_N = 10


def fetch_news_titles():
    titles = []
    for query, _tag in NEWS_QUERIES:
        url = (
            "https://news.google.com/rss/search?q="
            + requests.utils.quote(query)
            + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            root = ET.fromstring(resp.content)
            for it in list(root.iter("item"))[:10]:
                t = (it.findtext("title") or "").strip()
                if t:
                    titles.append(t)
        except Exception:  # noqa: BLE001
            continue
    return titles


def news_heat(keywords, titles):
    if not titles:
        return 0
    hits = 0
    for title in titles:
        low = title.lower()
        if any(k.lower() in low for k in keywords):
            hits += 1
    return hits


def run(ctx):
    tickers = [u[0] for u in UNIVERSE]
    data = yf.download(
        tickers, period="1mo", interval="1d",
        group_by="ticker", threads=True, progress=False, auto_adjust=False,
    )

    titles = fetch_news_titles()

    rows = []
    for ticker, name, market, theme, keywords in UNIVERSE:
        try:
            if ticker in data.columns.levels[0]:
                df = data[ticker].dropna(subset=["Close"])
            else:
                df = yf.Ticker(ticker).history(period="1mo", interval="1d")
                df = df.dropna(subset=["Close"]) if len(df) else df
            if df is None or len(df) < 6:
                raise ValueError("insufficient history")
            closes = df["Close"].astype(float)
            vols = df["Volume"].astype(float)
            price = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            change_pct = (price - prev) / prev * 100 if prev else 0.0
            ret5 = (price / float(closes.iloc[-6]) - 1) * 100 if len(closes) >= 6 else 0.0
            ref = closes.iloc[-21] if len(closes) >= 21 else closes.iloc[0]
            ret20 = (price / float(ref) - 1) * 100
            avg_vol = float(vols.iloc[-21:-1].mean()) if len(vols) >= 2 else float(vols.mean())
            vol_ratio = float(vols.iloc[-1]) / avg_vol if avg_vol else 1.0
            near_high = price / float(closes.tail(20).max()) * 100
            heat = news_heat(keywords, titles)

            if ret5 > 3 and vol_ratio > 1.5 and change_pct > 0:
                signal = "放量上攻"
            elif ret5 > 3 and change_pct > 0:
                signal = "短线强势"
            elif ret20 > 8 and change_pct > 0:
                signal = "趋势走强"
            elif ret5 < -3:
                signal = "短线回调"
            elif near_high > 97 and change_pct > 0:
                signal = "接近新高"
            else:
                signal = "震荡观察"

            rationale = (
                f"5日{ret5:+.1f}% / 20日{ret20:+.1f}%，"
                f"量能 {vol_ratio:.1f} 倍，距20日高点 {near_high:.0f}%"
            )
            rationale_en = (
                f"5d {ret5:+.1f}% / 20d {ret20:+.1f}%, "
                f"vol {vol_ratio:.1f}x, {near_high:.0f}% of 20d high"
            )
            if heat:
                rationale += f"，相关新闻 {heat} 条"
                rationale_en += f", {heat} related news"

            rows.append(
                {
                    "name": name,
                    "ticker": ticker,
                    "market": market,
                    "theme": theme,
                    "price": round(price, 2),
                    "changePct": round(change_pct, 2),
                    "ret5d": round(ret5, 2),
                    "ret20d": round(ret20, 2),
                    "volRatio": round(vol_ratio, 2),
                    "newsHeat": heat,
                    "signal": signal,
                    "signalEn": SIGNAL_EN.get(signal, signal),
                    "rationale": rationale,
                    "rationaleEn": rationale_en,
                    "score": 0.0,
                }
            )
        except Exception:  # noqa: BLE001
            continue

    # 打分：动量/量能横截面排名 + 新闻热度
    def ranks(key):
        vals = sorted((r[key], i) for i, r in enumerate(rows))
        n = max(1, len(vals) - 1)
        out = [0.0] * len(rows)
        for pos, (_v, i) in enumerate(vals):
            out[i] = pos / n
        return out

    if rows:
        r5, r20, rv = ranks("ret5d"), ranks("ret20d"), ranks("volRatio")
        max_heat = max(r["newsHeat"] for r in rows) or 1
        for i, r in enumerate(rows):
            r["score"] = round(
                0.30 * r5[i] + 0.30 * r20[i] + 0.20 * rv[i] + 0.20 * (r["newsHeat"] / max_heat),
                3,
            )
        rows.sort(key=lambda x: x["score"], reverse=True)

    fetched_at = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    return {
        "artifact": {
            "asOf": fetched_at,
            "fetchedAt": fetched_at,
            "source": "Yahoo Finance + Google News RSS（延迟数据，仅供竞赛研究）",
            "picks": rows[:TOP_N],
            "scanned": len(rows),
            "disclaimer": DISCLAIMER,
        }
    }
