"""
news_fetcher.py — 네이버/구글/yfinance 뉴스 수집 + 영→한 번역
v5 개선:
- 해외뉴스는 국내 종목도 반드시 Yahoo Finance 티커(.KS/.KQ)와 영어 회사명으로 수집
- 삼성전자 → Samsung Electronics, 005930.KS 같은 도메인 지식 기반 alias 적용
- Yahoo/yfinance 뉴스 1차, Google News EN 다중 query 2차, 최신 fallback 3차
- 해외뉴스는 원문 제목/요약을 보존하고 한국어 번역 제목/요약을 별도 제공
- 해외뉴스 수집 진단(debug)에 시도한 Yahoo ticker, Google query, source count를 표시
"""
from __future__ import annotations

import re
import time
from datetime import datetime, date, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import feedparser
import requests
from deep_translator import GoogleTranslator

# 국내 주요 종목의 영어명/야후티커/해외뉴스 키워드 매핑.
# 해외뉴스 수집에서는 한국어 종목명만으로 검색하지 않고, 이 값을 최우선 사용한다.
_KR_COMPANY_ALIASES = {
    "005930": {
        "english": "Samsung Electronics",
        "yahoo": ["005930.KS", "SSNLF", "SSUN.F"],
        "keywords": ["Samsung Electronics", "Samsung Electronics Co", "Samsung chip", "Samsung semiconductor", "Samsung HBM", "Samsung memory chip"],
    },
    "000660": {
        "english": "SK Hynix",
        "yahoo": ["000660.KS", "HXSCF"],
        "keywords": ["SK Hynix", "SK hynix HBM", "SK Hynix memory chip", "SK Hynix semiconductor"],
    },
    "005380": {"english": "Hyundai Motor", "yahoo": ["005380.KS", "HYMTF"], "keywords": ["Hyundai Motor", "Hyundai Motor Company", "Hyundai EV"]},
    "000270": {"english": "Kia", "yahoo": ["000270.KS", "KIMTF"], "keywords": ["Kia", "Kia Corp", "Kia Motors"]},
    "035420": {"english": "NAVER Corporation", "yahoo": ["035420.KS"], "keywords": ["NAVER Corporation", "Naver AI", "Naver Cloud"]},
    "035720": {"english": "Kakao Corp", "yahoo": ["035720.KS"], "keywords": ["Kakao Corp", "KakaoTalk", "Kakao Mobility"]},
    "373220": {"english": "LG Energy Solution", "yahoo": ["373220.KS"], "keywords": ["LG Energy Solution", "LGES battery"]},
    "207940": {"english": "Samsung Biologics", "yahoo": ["207940.KS"], "keywords": ["Samsung Biologics", "Samsung BioLogics"]},
    "068270": {"english": "Celltrion", "yahoo": ["068270.KS"], "keywords": ["Celltrion", "Celltrion biosimilar"]},
    "051910": {"english": "LG Chem", "yahoo": ["051910.KS"], "keywords": ["LG Chem", "LG Chemical battery"]},
    "006400": {"english": "Samsung SDI", "yahoo": ["006400.KS"], "keywords": ["Samsung SDI", "Samsung SDI battery"]},
    "005490": {"english": "POSCO Holdings", "yahoo": ["005490.KS"], "keywords": ["POSCO Holdings", "POSCO steel"]},
    "105560": {"english": "KB Financial Group", "yahoo": ["105560.KS"], "keywords": ["KB Financial Group", "KB Kookmin Bank"]},
    "055550": {"english": "Shinhan Financial Group", "yahoo": ["055550.KS"], "keywords": ["Shinhan Financial Group", "Shinhan Bank"]},
    "066570": {"english": "LG Electronics", "yahoo": ["066570.KS", "LGEAF"], "keywords": ["LG Electronics", "LG Electronics appliance", "LG OLED"]},
    "017670": {"english": "SK Telecom", "yahoo": ["017670.KS"], "keywords": ["SK Telecom", "SKT AI", "SK Telecom Korea"]},
}

# 한글명으로 들어온 경우에도 영어명 검색이 되도록 보조 매핑
_KR_NAME_TO_ENGLISH = {
    "삼성전자": "Samsung Electronics",
    "sk하이닉스": "SK Hynix",
    "하이닉스": "SK Hynix",
    "현대차": "Hyundai Motor",
    "현대자동차": "Hyundai Motor",
    "기아": "Kia",
    "네이버": "NAVER Corporation",
    "naver": "NAVER Corporation",
    "카카오": "Kakao Corp",
    "lg에너지솔루션": "LG Energy Solution",
    "삼성바이오로직스": "Samsung Biologics",
    "셀트리온": "Celltrion",
    "lg화학": "LG Chem",
    "삼성sdi": "Samsung SDI",
    "포스코홀딩스": "POSCO Holdings",
    "포스코": "POSCO Holdings",
    "lg전자": "LG Electronics",
    "sk텔레콤": "SK Telecom",
}


def _hangul_ratio(text: str) -> float:
    if not text:
        return 0.0
    chars = [c for c in text if c.isalpha() or ('가' <= c <= '힣')]
    if not chars:
        return 0.0
    ko = sum(1 for c in chars if '가' <= c <= '힣')
    return ko / len(chars)


def translate_to_korean(text: str, force: bool = False) -> str:
    """해외뉴스는 force=True로 번역한다. 원문은 original_title/original_summary에 보존한다."""
    if not text:
        return text
    try:
        # 이미 거의 한국어면 그대로 둔다. 혼합 제목은 번역 시도한다.
        if not force and _hangul_ratio(text) > 0.55:
            return text
        if force and _hangul_ratio(text) > 0.75:
            return text
        translated = GoogleTranslator(source="auto", target="ko").translate(text[:900])
        return translated or text
    except Exception:
        return text


def _parse_date(s: str):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.date()
    except Exception:
        return None


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _parse_rss(url: str, max_items: int = 10, translate: bool = False, today_first: bool = True, query_label: str = "") -> list[dict]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 StockBriefBot/5.0"
        }
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code >= 400 or not resp.text:
            return []
        feed = feedparser.parse(resp.text)
    except Exception:
        return []

    all_items, today_items = [], []
    for entry in feed.entries[: max_items * 5]:
        original_title = _strip_html(entry.get("title", ""))
        link = entry.get("link", "")
        published = entry.get("published", "") or entry.get("updated", "")
        original_summary = _strip_html(entry.get("summary", ""))[:500]
        if not original_title:
            continue
        title = translate_to_korean(original_title, force=translate) if translate else original_title
        summary = translate_to_korean(original_summary, force=translate) if translate else original_summary
        item = {
            "title": title,
            "link": link,
            "published": published,
            "summary": summary,
            "original_title": original_title,
            "original_summary": original_summary,
            "query": query_label,
        }
        all_items.append(item)
        if _parse_date(published) == date.today():
            today_items.append(item)
        time.sleep(0.02)
    selected = today_items if today_first and today_items else all_items
    return selected[:max_items]


def _dedupe(items: list[dict], max_items: int = 10) -> list[dict]:
    seen, out = set(), []
    for item in items:
        title = (item.get("original_title") or item.get("title") or "").strip()
        link = item.get("link") or ""
        key = (title.lower(), link.split("?")[0])
        if title and key not in seen:
            seen.add(key)
            out.append(item)
        if len(out) >= max_items:
            break
    return out


def fetch_naver_news(query: str, max_items: int = 10) -> list[dict]:
    url = f"https://search.naver.com/rss?where=news&query={quote(query)}"
    results = _parse_rss(url, max_items, translate=False)
    for r in results:
        r["source"] = "네이버뉴스"
    return results


def fetch_google_news_kr(query: str, max_items: int = 10) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={quote(query + ' when:1d')}&hl=ko&gl=KR&ceid=KR:ko"
    results = _parse_rss(url, max_items, translate=False, query_label=query)
    for r in results:
        r["source"] = "구글뉴스(KR)"
    return results


def fetch_google_news_en_query(query: str, max_items: int = 10) -> list[dict]:
    """English Google News search with staged fallback.
    엄격한 1일 조건에서 비면 7일, 30일, 무날짜 최신 조건으로 넓힌다.
    """
    queries = [
        f'"{query}" stock when:1d',
        f'"{query}" shares when:7d',
        f'"{query}" earnings OR semiconductor OR AI when:30d',
        f'"{query}" stock market',
    ]
    collected = []
    for q in queries:
        url = f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"
        rows = _parse_rss(url, max_items, translate=True, today_first=True, query_label=q)
        for r in rows:
            r["source"] = f"구글뉴스(EN→KR)"
        collected.extend(rows)
        if len(_dedupe(collected, max_items)) >= max_items:
            break
    return _dedupe(collected, max_items)


def fetch_google_news_en(query: str, max_items: int = 10) -> list[dict]:
    return fetch_google_news_en_query(query, max_items)


def _yfinance_news_once(yf_ticker: str, max_items: int = 10) -> list[dict]:
    try:
        import yfinance as yf
        raw = yf.Ticker(yf_ticker).news or []
    except Exception:
        return []
    items = []
    for n in raw[: max_items * 2]:
        if not isinstance(n, dict):
            continue
        content = n.get("content", n)
        if not isinstance(content, dict):
            content = {}
        original_title = content.get("title") or n.get("title") or ""
        original_summary = content.get("summary") or n.get("summary") or ""
        link = ""
        if isinstance(content.get("canonicalUrl"), dict):
            link = content.get("canonicalUrl", {}).get("url", "")
        if isinstance(content.get("clickThroughUrl"), dict):
            link = link or content.get("clickThroughUrl", {}).get("url", "")
        link = link or n.get("link", "")
        pub_ts = content.get("pubDate") or n.get("providerPublishTime")
        published = ""
        try:
            if isinstance(pub_ts, int):
                published = datetime.fromtimestamp(pub_ts).strftime("%Y-%m-%d %H:%M")
            elif isinstance(pub_ts, str):
                published = pub_ts
        except Exception:
            published = ""
        if original_title:
            items.append({
                "title": translate_to_korean(original_title, force=True),
                "link": link,
                "published": published,
                "summary": translate_to_korean((original_summary or "")[:500], force=True) if original_summary else "",
                "original_title": original_title,
                "original_summary": original_summary,
                "source": f"Yahoo Finance/yfinance · {yf_ticker}",
                "query": yf_ticker,
            })
        if len(items) >= max_items:
            break
    return items


def fetch_yfinance_news(ticker: str, max_items: int = 10) -> list[dict]:
    return _yfinance_news_once(ticker, max_items)


def _company_alias(stock: dict) -> dict:
    ticker = str(stock.get("ticker", "")).strip()
    name = str(stock.get("name", "")).strip()
    alias = dict(_KR_COMPANY_ALIASES.get(ticker, {}))
    if not alias:
        key = name.lower().replace(" ", "")
        en = _KR_NAME_TO_ENGLISH.get(key)
        if en:
            alias = {"english": en, "keywords": [en], "yahoo": []}
    if ticker and re.fullmatch(r"\d{6}", ticker):
        yahoo = alias.get("yahoo", [])[:]
        # Yahoo Finance 한국 종목 기본 규칙. 시장이 모호하면 KS→KQ 순서.
        for t in [f"{ticker}.KS", f"{ticker}.KQ"]:
            if t not in yahoo:
                yahoo.append(t)
        alias["yahoo"] = yahoo
    if not alias.get("english"):
        alias["english"] = name or ticker
    return alias


def _international_queries_for_stock(stock: dict) -> list[str]:
    ticker = str(stock.get("ticker", "")).strip()
    name = str(stock.get("name", ticker)).strip()
    market = stock.get("market", "KR")
    alias = _company_alias(stock)
    queries: list[str] = []
    if market == "KR":
        english = alias.get("english") or name
        keywords = alias.get("keywords") or [english]
        queries.extend(keywords)
        queries.extend([
            f"{english} Korea",
            f"{english} earnings",
            f"{english} stock",
            f"{ticker}.KS",
            f"{ticker}.KQ",
            f"{name} {ticker}",
        ])
    else:
        queries.extend([ticker, f"{name} {ticker}", f"{ticker} earnings", f"{ticker} stock"])
    out = []
    for q in queries:
        q = str(q).strip()
        if q and q not in out:
            out.append(q)
    return out


def _yfinance_tickers_for_stock(stock: dict) -> list[str]:
    ticker = str(stock.get("ticker", "")).strip()
    market = stock.get("market", "KR")
    if market == "KR" and re.fullmatch(r"\d{6}", ticker):
        alias = _company_alias(stock)
        return alias.get("yahoo", [f"{ticker}.KS", f"{ticker}.KQ"])
    return [ticker]


def fetch_all_news(stock: dict, kr_per_source: int = 10, en_per_source: int = 10) -> dict:
    name = stock.get("name", stock.get("ticker", ""))
    ticker = stock.get("ticker", "")
    market = stock.get("market", "KR")
    kr_query = f"{name} 주식" if market == "KR" else f"{name} {ticker} 주식"

    domestic = fetch_naver_news(kr_query, kr_per_source) + fetch_google_news_kr(kr_query, kr_per_source)
    domestic_unique = _dedupe(domestic, 10)

    debug = {
        "reason": "해외뉴스는 Yahoo Finance 티커와 영어 회사명 query를 모두 사용합니다.",
        "english_name": _company_alias(stock).get("english"),
        "international_queries": [],
        "yfinance_tickers": [],
        "international_source_counts": {},
    }
    international: list[dict] = []

    # 1) Yahoo Finance/yfinance를 먼저 시도한다. 국내 종목은 005930.KS 같은 Yahoo 티커가 핵심이다.
    for yf_ticker in _yfinance_tickers_for_stock(stock):
        debug["yfinance_tickers"].append(yf_ticker)
        rows = fetch_yfinance_news(yf_ticker, en_per_source)
        debug["international_source_counts"][f"yfinance:{yf_ticker}"] = len(rows)
        international.extend(rows)
        if len(_dedupe(international, 10)) >= 10:
            break

    # 2) Google News EN은 영어 회사명과 관련 키워드를 다중 query로 시도한다.
    if len(_dedupe(international, 10)) < 10:
        for q in _international_queries_for_stock(stock):
            debug["international_queries"].append(q)
            rows = fetch_google_news_en_query(q, en_per_source)
            debug["international_source_counts"][f"google:{q}"] = len(rows)
            international.extend(rows)
            if len(_dedupe(international, 10)) >= 10:
                break

    international_unique = _dedupe(international, 10)
    debug["final_international_count"] = len(international_unique)
    return {"domestic": domestic_unique, "international": international_unique, "debug": debug}
