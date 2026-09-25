"""全球市场脉搏：拉取主要指数与大宗资产最新报价，产出结构化 artifact。"""
import datetime
import warnings

warnings.filterwarnings("ignore")

import yfinance as yf

# (ticker, 名称, 区域, 货币)
UNIVERSE = [
    # A股
    ("000001.SS", "上证指数", "A股", "CNY"),
    ("399001.SZ", "深证成指", "A股", "CNY"),
    ("399006.SZ", "创业板指", "A股", "CNY"),
    ("000300.SS", "沪深300", "A股", "CNY"),
    ("000905.SS", "中证500", "A股", "CNY"),
    ("000852.SS", "中证1000", "A股", "CNY"),
    # 港股
    ("^HSI", "恒生指数", "港股", "HKD"),
    ("^HSCE", "恒生国企指数", "港股", "HKD"),
    ("^HSTECH", "恒生科技指数", "港股", "HKD"),
    # 美股
    ("^GSPC", "标普500", "美股", "USD"),
    ("^IXIC", "纳斯达克", "美股", "USD"),
    ("^DJI", "道琼斯", "美股", "USD"),
    ("^RUT", "罗素2000", "美股", "USD"),
    ("^NDX", "纳斯达克100", "美股", "USD"),
    # 亚太
    ("^N225", "日经225", "亚太", "JPY"),
    ("^KS11", "韩国KOSPI", "亚太", "KRW"),
    ("^TWII", "台湾加权指数", "亚太", "TWD"),
    ("^AXJO", "澳洲ASX200", "亚太", "AUD"),
    ("^STI", "新加坡海峡时报", "亚太", "SGD"),
    ("^BSESN", "印度SENSEX", "亚太", "INR"),
    # 欧洲
    ("^GDAXI", "德国DAX", "欧洲", "EUR"),
    ("^FTSE", "英国FTSE100", "欧洲", "GBP"),
    ("^FCHI", "法国CAC40", "欧洲", "EUR"),
    ("^STOXX50E", "欧洲STOXX50", "欧洲", "EUR"),
    # 美洲其他
    ("^GSPTSE", "加拿大TSX", "美洲", "CAD"),
    ("^BVSP", "巴西BOVESPA", "美洲", "BRL"),
    # 大宗
    ("GC=F", "COMEX黄金", "大宗", "USD"),
    ("SI=F", "COMEX白银", "大宗", "USD"),
    ("HG=F", "COMEX铜", "大宗", "USD"),
    ("CL=F", "WTI原油", "大宗", "USD"),
    ("BZ=F", "布伦特原油", "大宗", "USD"),
    ("NG=F", "天然气", "大宗", "USD"),
    ("ZC=F", "玉米", "大宗", "USD"),
    ("ZS=F", "大豆", "大宗", "USD"),
    ("ZW=F", "小麦", "大宗", "USD"),
    # 汇率
    ("DX-Y.NYB", "美元指数", "汇率", "USD"),
    ("CNH=X", "美元/离岸人民币", "汇率", "CNH"),
    ("JPY=X", "美元/日元", "汇率", "JPY"),
    ("EURUSD=X", "欧元/美元", "汇率", "EUR"),
    ("GBPUSD=X", "英镑/美元", "汇率", "GBP"),
    # 债券
    ("^TNX", "美债10Y收益率", "债券", "%"),
    ("^FVX", "美债5Y收益率", "债券", "%"),
    ("^TYX", "美债30Y收益率", "债券", "%"),
    ("^VIX", "VIX波动率", "债券", "USD"),
    # 加密
    ("BTC-USD", "比特币", "加密", "USD"),
    ("ETH-USD", "以太坊", "加密", "USD"),
    ("SOL-USD", "Solana", "加密", "USD"),
]

# ^TNX/^FVX/^TYX 报价为收益率的 10 倍（41.50 => 4.15%）
SCALE = {"^TNX": 0.1, "^FVX": 0.1, "^TYX": 0.1}


def run(ctx):
    tickers = [u[0] for u in UNIVERSE]
    try:
        data = yf.download(
            tickers,
            period="5d",
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
        )
    except Exception as exc:  # noqa: BLE001
        data = None
        bulk_error = repr(exc)
    else:
        bulk_error = None

    indices = []
    errors = []
    last_bar = None

    # 小时线用于趋势曲线（spark），随每次刷新更新
    try:
        hdata = yf.download(
            tickers,
            period="1mo",
            interval="1h",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
        )
    except Exception:  # noqa: BLE001
        hdata = None

    def spark_of(ticker, scale, daily_closes):
        try:
            if hdata is not None and ticker in hdata.columns.levels[0]:
                hdf = hdata[ticker].dropna(subset=["Close"])
                s = [float(v) * scale for v in hdf["Close"].tail(48)]
                if len(s) >= 6:
                    return [round(v, 4) for v in s]
        except Exception:  # noqa: BLE001
            pass
        s = [float(v) * scale for v in daily_closes.tail(22)]
        return [round(v, 4) for v in s] if len(s) >= 2 else []

    for ticker, name, region, ccy in UNIVERSE:
        try:
            if data is not None and ticker in data.columns.levels[0]:
                df = data[ticker].dropna(subset=["Close"])
            else:
                df = yf.Ticker(ticker).history(period="5d", interval="1d")
                df = df.dropna(subset=["Close"]) if len(df) else df
            approx = False
            if df is None or len(df) < 2:
                # 部分指数日线缺失，退化为 5 日小时线，用最近两根小时收盘近似日涨跌
                df = yf.Ticker(ticker).history(period="5d", interval="1h")
                df = df.dropna(subset=["Close"]) if len(df) else df
                approx = True
            if df is None or len(df) < 2:
                raise ValueError("insufficient history")
            closes = df["Close"].astype(float)
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            scale = SCALE.get(ticker, 1.0)
            last, prev = last * scale, prev * scale
            chg = (last - prev) / prev * 100.0 if prev else 0.0
            ts = df.index[-1]
            try:
                ts_epoch = ts.timestamp()
            except Exception:  # noqa: BLE001
                ts_epoch = None
            if ts_epoch is not None and (last_bar is None or ts_epoch > last_bar):
                last_bar = ts_epoch
            spark = spark_of(ticker, scale, closes)
            indices.append(
                {
                    "name": name,
                    "ticker": ticker,
                    "price": round(last, 2),
                    "changePct": round(chg, 2),
                    "region": region,
                    "currency": ccy,
                    "stale": False,
                    "approx": approx,
                    "spark": spark,
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"ticker": ticker, "name": name, "error": repr(exc)[:160]})

    fetched_at = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    as_of = (
        datetime.datetime.fromtimestamp(last_bar, datetime.timezone.utc).isoformat()
        if last_bar is not None
        else fetched_at
    )
    return {
        "artifact": {
            "asOf": as_of,
            "fetchedAt": fetched_at,
            "source": "Yahoo Finance（延迟行情，仅供参考）",
            "bulkError": bulk_error,
            "indices": indices,
            "errors": errors,
        }
    }
