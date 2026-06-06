
"""
stock_data.py — pykrx + yfinance 주가 데이터 수집
Claude 버전의 장점 반영:
- pykrx는 함수 내부에서 import하여 Streamlit 앱 시작 안정성 확보
- 자주 쓰는 국내 종목명 fallback map 유지
- 국내 종목은 pykrx 우선, 해외 종목은 yfinance
추가 개선:
- MA5/20/60, 변동성, 휴리스틱 예상 방향/등락률 추가
- pykrx 실패 시 국내 가격은 yfinance .KS/.KQ fallback 시도
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd


def last_trading_day(d: Optional[date] = None) -> date:
    d = d or date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def date_range_for_period(period: str) -> tuple[date, date]:
    end = last_trading_day()
    if period == "week":
        start = end - timedelta(days=7)
    elif period == "month":
        start = end - timedelta(days=30)
    else:
        start = end - timedelta(days=183)
    return start, end


_KR_NAME_MAP = {
    "삼성전자": "005930", "sk하이닉스": "000660", "하이닉스": "000660",
    "lg에너지솔루션": "373220", "삼성바이오로직스": "207940", "삼성바이오": "207940",
    "현대차": "005380", "현대자동차": "005380", "기아": "000270", "기아차": "000270",
    "셀트리온": "068270", "naver": "035420", "네이버": "035420", "카카오": "035720",
    "lg화학": "051910", "삼성sdi": "006400", "포스코홀딩스": "005490", "포스코": "005490",
    "kb금융": "105560", "신한지주": "055550", "하나금융지주": "086790", "우리금융지주": "316140",
    "카카오뱅크": "323410", "크래프톤": "259960", "넷마블": "251270", "엔씨소프트": "036570",
    "한국전력": "015760", "한전": "015760", "두산에너빌리티": "034020", "삼성물산": "028260",
    "현대모비스": "012330", "lg전자": "066570", "sk텔레콤": "017670", "kt": "030200",
    "lg유플러스": "032640", "카카오페이": "377300", "kakao": "035720",
}


def get_pykrx_stock():
    """pykrx lazy import. 국내 주식 기능이 필요할 때만 import한다."""
    try:
        from pykrx import stock as px
        return px
    except ModuleNotFoundError as e:
        if "pkg_resources" in str(e):
            raise RuntimeError(
                "pykrx가 pkg_resources를 찾지 못했습니다. Streamlit Cloud 환경에서 pykrx import가 실패했습니다. "
                "requirements와 Python 버전을 확인하세요."
            ) from e
        raise


def name_to_ticker(name: str) -> Optional[str]:
    key = name.strip().lower().replace(" ", "")
    if key in _KR_NAME_MAP:
        return _KR_NAME_MAP[key]
    try:
        px = get_pykrx_stock()
        for market in ("KOSPI", "KOSDAQ", "KONEX"):
            tickers = px.get_market_ticker_list(market=market)
            for t in tickers:
                try:
                    n = px.get_market_ticker_name(t)
                    if n and n.strip().replace(" ", "") == name.strip().replace(" ", ""):
                        return t
                except Exception:
                    continue
    except Exception:
        pass
    return None


def normalize_ticker(raw: str) -> tuple[str, str]:
    raw = raw.strip()
    if re.fullmatch(r"\d{6}", raw):
        return raw, raw
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,14}", raw):
        return raw.upper(), raw.upper()
    code = name_to_ticker(raw)
    if code:
        return code, raw
    return raw, raw


def is_kr_code(ticker: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", ticker.strip()))


def _history_metrics_from_close(close_series: pd.Series) -> dict:
    s = close_series.dropna().astype(float)
    if s.empty:
        return {}
    last = float(s.iloc[-1])
    ret = s.pct_change().dropna()
    ma5 = float(s.tail(5).mean()) if len(s) >= 5 else None
    ma20 = float(s.tail(20).mean()) if len(s) >= 20 else None
    ma60 = float(s.tail(60).mean()) if len(s) >= 60 else None
    vol20 = float(ret.tail(20).std() * np.sqrt(252) * 100) if len(ret) >= 5 else None

    def pct_n(n: int):
        if len(s) <= n:
            return None
        prev = float(s.iloc[-n-1])
        return (last / prev - 1) * 100 if prev else None

    week = pct_n(5)
    month = pct_n(21)
    six = pct_n(126)
    score = 0.0
    for value, weight in [(week, 0.35), (month, 0.25), (six, 0.15)]:
        if value is not None:
            score += max(-1, min(1, value / 10)) * weight
    if ma5 and ma20:
        score += 0.15 if ma5 > ma20 else -0.15
    if ma20 and ma60:
        score += 0.10 if ma20 > ma60 else -0.10
    expected = max(-4.5, min(4.5, score * 2.2))
    direction = "NEUTRAL" if abs(expected) < 0.25 else ("UP" if expected > 0 else "DOWN")
    return {
        "ma5": ma5, "ma20": ma20, "ma60": ma60,
        "vol20_annual_pct": vol20,
        "week_return_pct": week,
        "month_return_pct": month,
        "six_month_return_pct": six,
        "heuristic_direction": direction,
        "heuristic_expected_change_pct": round(expected, 2),
    }


def _history_dict_from_df(df: pd.DataFrame) -> dict:
    history = {}
    for period in ("week", "month", "6month"):
        start, _ = date_range_for_period(period)
        if df is not None and not df.empty:
            sub = df[df.index.date >= start]
            history[period] = sub[["close"]] if "close" in sub.columns else pd.DataFrame()
        else:
            history[period] = pd.DataFrame()
    return history


def _market_suffix_guess(ticker: str) -> list[str]:
    # KOSPI/KOSDAQ 구분을 모를 때 KS, KQ 순서로 시도한다.
    return [f"{ticker}.KS", f"{ticker}.KQ"]


def fetch_kr_stock_yfinance_fallback(ticker: str, display_name: str = "", warning: str = "") -> dict:
    import yfinance as yf
    last_error = ""
    for yf_ticker in _market_suffix_guess(ticker):
        try:
            obj = yf.Ticker(yf_ticker)
            hist = obj.history(period="7mo")
            if hist is None or hist.empty:
                continue
            hist = hist.dropna(subset=["Close"]).copy()
            hist = hist.rename(columns={"Close": "close"})
            row = hist.iloc[-1]
            close = float(row["close"])
            prev = float(hist.iloc[-2]["close"]) if len(hist) > 1 else None
            change_rate = (close / prev - 1) * 100 if prev else None
            metrics = _history_metrics_from_close(hist["close"])
            history = _history_dict_from_df(hist)
            return {
                "ticker": ticker,
                "yf_ticker": yf_ticker,
                "name": display_name or ticker,
                "market": "KR",
                "close": close,
                "change_rate": change_rate,
                "volume": int(row.get("Volume", 0)) if "Volume" in row else None,
                "date": str(hist.index[-1].date()),
                "investor": {},
                "history": history,
                "metrics": metrics,
                "data_source": "yfinance fallback",
                "warning": warning or "pykrx 실패로 yfinance fallback 사용",
            }
        except Exception as e:
            last_error = str(e)
    raise RuntimeError(f"pykrx 실패 후 yfinance fallback도 실패: {last_error}")


def fetch_kr_stock(ticker: str, display_name: str = "") -> dict:
    try:
        px = get_pykrx_stock()
        td = last_trading_day()
        td_str = td.strftime("%Y%m%d")
        try:
            name = px.get_market_ticker_name(ticker) or display_name or ticker
        except Exception:
            name = display_name or ticker

        try:
            ohlcv = px.get_market_ohlcv(td_str, td_str, ticker)
            if ohlcv.empty:
                w_start = (td - timedelta(days=14)).strftime("%Y%m%d")
                ohlcv = px.get_market_ohlcv(w_start, td_str, ticker)
            row = ohlcv.iloc[-1] if not ohlcv.empty else None
        except Exception:
            row = None

        close = float(row["종가"]) if row is not None and "종가" in row else None
        change_rate = float(row["등락률"]) if row is not None and "등락률" in row else None
        volume = int(row["거래량"]) if row is not None and "거래량" in row else None

        investor = {}
        try:
            inv_df = px.get_market_trading_value_by_investor(td_str, td_str, ticker)
            if not inv_df.empty:
                for label in ["외국인합계", "기관합계", "개인"]:
                    if label in inv_df.index:
                        investor[label] = int(inv_df.loc[label, "순매수"])
        except Exception:
            pass

        # 7개월 전체 히스토리로 metrics 계산, period별 history 생성
        start_7m = (td - timedelta(days=215)).strftime("%Y%m%d")
        hist_df = px.get_market_ohlcv(start_7m, td_str, ticker)
        if hist_df is None or hist_df.empty:
            hist_close = pd.Series(dtype=float)
            hist_for_period = pd.DataFrame()
        else:
            hist_for_period = hist_df.rename(columns={"종가": "close"})
            hist_for_period.index = pd.to_datetime(hist_for_period.index)
            hist_close = hist_for_period["close"]
        history = _history_dict_from_df(hist_for_period)
        metrics = _history_metrics_from_close(hist_close)

        return {
            "ticker": ticker,
            "name": name,
            "market": "KR",
            "close": close,
            "change_rate": change_rate,
            "volume": volume,
            "date": td.isoformat(),
            "investor": investor,
            "history": history,
            "metrics": metrics,
            "data_source": "pykrx",
        }
    except Exception as e:
        return fetch_kr_stock_yfinance_fallback(ticker, display_name, warning=str(e))


def fetch_us_stock(ticker: str) -> dict:
    import yfinance as yf
    yf_ticker = ticker.strip().upper()
    obj = yf.Ticker(yf_ticker)
    try:
        info = obj.info
        name = info.get("longName") or info.get("shortName") or yf_ticker
    except Exception:
        name = yf_ticker
    hist = obj.history(period="7mo")
    row = hist.iloc[-1] if hist is not None and not hist.empty else None
    close = float(row["Close"]) if row is not None else None
    prev_close = float(hist.iloc[-2]["Close"]) if row is not None and len(hist) > 1 else None
    change_rate = (close - prev_close) / prev_close * 100 if close and prev_close else None
    volume = int(row["Volume"]) if row is not None and "Volume" in row else None
    hist_for_period = hist[["Close"]].rename(columns={"Close": "close"}) if hist is not None and not hist.empty else pd.DataFrame()
    history = _history_dict_from_df(hist_for_period)
    metrics = _history_metrics_from_close(hist_for_period["close"]) if not hist_for_period.empty else {}
    return {
        "ticker": yf_ticker,
        "name": name,
        "market": "US",
        "close": close,
        "change_rate": change_rate,
        "volume": volume,
        "date": str(hist.index[-1].date()) if hist is not None and not hist.empty else last_trading_day().isoformat(),
        "investor": {},
        "history": history,
        "metrics": metrics,
        "data_source": "yfinance",
    }


def fetch_stock(raw_input: str) -> dict:
    ticker, display = normalize_ticker(raw_input)
    if is_kr_code(ticker):
        return fetch_kr_stock(ticker, display_name=display)
    return fetch_us_stock(ticker)


def fetch_all_stocks(raw_inputs: list[str]) -> list[dict]:
    results = []
    for raw in raw_inputs[:10]:
        try:
            results.append(fetch_stock(raw))
        except Exception as e:
            results.append({
                "ticker": raw, "name": raw, "market": "?",
                "close": None, "change_rate": None, "volume": None,
                "date": last_trading_day().isoformat(),
                "investor": {}, "history": {}, "metrics": {},
                "data_source": "error", "error": str(e),
            })
    return results
