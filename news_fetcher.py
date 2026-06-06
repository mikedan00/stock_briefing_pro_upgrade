
"""
news_fetcher.py — 네이버/구글/yfinance 뉴스 수집 + 영→한 번역
Claude 버전의 RSS 중심 구조 유지, 오늘 날짜 우선 필터 보강.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, date, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
from deep_translator import GoogleTranslator


def translate_to_korean(text: str) -> str:
    if not text:
        return text
    try:
        if re.search(r"[\uAC00-\uD7A3]", text):
            return text
        return GoogleTranslator(source="auto", target="ko").translate(text[:500])
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


def _parse_rss(url: str, max_items: int = 10, translate: bool = False, today_first: bool = True) -> list[dict]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; StockBriefBot/2.0)"}
        resp = requests.get(url, headers=headers, timeout=8)
        feed = feedparser.parse(resp.text)
    except Exception:
        return []

    all_items, today_items = [], []
    for entry in feed.entries[:max_items * 3]:
        title = re.sub(r"<[^>]+>", "", entry.get("title", "")).strip()
        link = entry.get("link", "")
        published = entry.get("published", "") or entry.get("updated", "")
        summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()[:250]
        if translate:
            title = translate_to_korean(title)
            summary = translate_to_korean(summary)
        item = {"title": title, "link": link, "published": published, "summary": summary}
        all_items.append(item)
        if _parse_date(published) == date.today():
            today_items.append(item)
        time.sleep(0.03)
    selected = today_items if today_first and today_items else all_items
    return selected[:max_items]


def fetch_naver_news(query: str, max_items: int = 10) -> list[dict]:
    url = f"https://search.naver.com/rss?where=news&query={requests.utils.quote(query)}"
    results = _parse_rss(url, max_items)
    for r in results:
        r["source"] = "네이버뉴스"
    return results


def fetch_google_news_kr(query: str, max_items: int = 10) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query + ' when:1d')}&hl=ko&gl=KR&ceid=KR:ko"
    results = _parse_rss(url, max_items)
    for r in results:
        r["source"] = "구글뉴스(KR)"
    return results


def fetch_google_news_en(query: str, max_items: int = 10) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query + ' stock when:1d')}&hl=en&gl=US&ceid=US:en"
    results = _parse_rss(url, max_items, translate=True)
    for r in results:
        r["source"] = "구글뉴스(EN→KR)"
    return results


def fetch_yfinance_news(ticker: str, max_items: int = 10) -> list[dict]:
    try:
        import yfinance as yf
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return []
    items = []
    for n in raw[:max_items]:
        content = n.get("content", n)
        title = content.get("title") or n.get("title") or ""
        summary = content.get("summary") or n.get("summary") or ""
        link = ""
        if isinstance(content.get("canonicalUrl"), dict):
            link = content.get("canonicalUrl", {}).get("url", "")
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
        items.append({
            "title": translate_to_korean(title),
            "link": link,
            "published": published,
            "summary": translate_to_korean(summary[:250]) if summary else "",
            "source": "yfinance",
        })
    return items


def fetch_all_news(stock: dict, kr_per_source: int = 10, en_per_source: int = 10) -> dict:
    name = stock.get("name", stock.get("ticker", ""))
    ticker = stock.get("ticker", "")
    market = stock.get("market", "KR")
    if market == "KR":
        kr_query = f"{name} 주식"
        en_query = f"{name} {ticker} stock"
    else:
        kr_query = f"{name} {ticker} 주식"
        en_query = f"{ticker} stock"

    domestic = fetch_naver_news(kr_query, kr_per_source) + fetch_google_news_kr(kr_query, kr_per_source)
    seen, domestic_unique = set(), []
    for item in domestic:
        key = item.get("title", "")
        if key and key not in seen:
            seen.add(key)
            domestic_unique.append(item)
        if len(domestic_unique) >= 10:
            break

    international = fetch_google_news_en(en_query, en_per_source)
    if market == "US":
        international += fetch_yfinance_news(ticker, en_per_source)
    seen_en, international_unique = set(), []
    for item in international:
        key = item.get("title", "")
        if key and key not in seen_en:
            seen_en.add(key)
            international_unique.append(item)
        if len(international_unique) >= 10:
            break

    return {"domestic": domestic_unique, "international": international_unique}
