
"""
report_generator.py — 주식 브리핑 리포트 생성 + RAG/분석자 페르소나 반영
"""
from __future__ import annotations

from datetime import date
from llm_engine import call_llm
from analyst_profiles import get_analyst_system, get_analyst_label
from rag_engine import retrieve, format_rag_context, RagChunk


def _format_investor(investor: dict) -> str:
    if not investor:
        return "수급 데이터 없음"
    label_map = {"외국인합계": "외국인", "기관합계": "기관", "개인": "개인"}
    lines = []
    for k, label in label_map.items():
        if k in investor:
            val = investor[k]
            sign = "+" if val >= 0 else ""
            lines.append(f"{label}: {sign}{val:,}원")
    return " | ".join(lines) if lines else "수급 데이터 없음"


def _news_summary(news_list: list[dict], max_items: int = 5) -> str:
    if not news_list:
        return "뉴스 없음"
    return "\n".join(f"- [{i+1}] {n.get('title','')} ({n.get('source','')})" for i, n in enumerate(news_list[:max_items]))


def _history_summary(history: dict) -> str:
    lines = []
    for period, label in [("week", "이번주"), ("month", "이번달"), ("6month", "6개월")]:
        df = history.get(period)
        if df is not None and not df.empty and "close" in df.columns:
            start_p = float(df["close"].iloc[0])
            end_p = float(df["close"].iloc[-1])
            change = ((end_p - start_p) / start_p * 100) if start_p else 0
            sign = "+" if change >= 0 else ""
            lines.append(f"{label}: {start_p:,.0f}→{end_p:,.0f} ({sign}{change:.1f}%)")
        else:
            lines.append(f"{label}: 데이터 없음")
    return " | ".join(lines)


def _metrics_summary(metrics: dict) -> str:
    if not metrics:
        return "정량 지표 없음"
    def f(x):
        return "N/A" if x is None else f"{x:,.2f}"
    return (
        f"MA5={f(metrics.get('ma5'))}, MA20={f(metrics.get('ma20'))}, MA60={f(metrics.get('ma60'))}, "
        f"20일 변동성={f(metrics.get('vol20_annual_pct'))}%, "
        f"휴리스틱 방향={metrics.get('heuristic_direction','N/A')}, "
        f"예상등락={f(metrics.get('heuristic_expected_change_pct'))}%"
    )


def generate_stock_brief(stock: dict, news: dict, analyst_key: str, rag_chunks: list[RagChunk] | None = None) -> str:
    name = stock.get("name", stock.get("ticker", ""))
    ticker = stock.get("ticker", "")
    close = stock.get("close")
    change = stock.get("change_rate")
    volume = stock.get("volume")
    market = stock.get("market", "")
    today = stock.get("date", date.today().isoformat())
    close_str = f"{close:,.0f}" if close is not None else "N/A"
    change_str = f"{change:+.2f}%" if change is not None else "N/A"
    volume_str = f"{volume:,}" if volume else "N/A"
    investor_str = _format_investor(stock.get("investor", {}))
    history_str = _history_summary(stock.get("history", {}))
    metrics_str = _metrics_summary(stock.get("metrics", {}))
    domestic_news = _news_summary(news.get("domestic", []))
    intl_news = _news_summary(news.get("international", []))
    query = f"{name} {ticker} 주가 뉴스 수급 투자전략"
    rag_context = format_rag_context(retrieve(rag_chunks or [], query, top_k=8), max_chars=5000)
    analyst_label = get_analyst_label(analyst_key)
    system = get_analyst_system(analyst_key) + "\n항상 한국어로 응답하고, 투자 참고용 면책을 포함한다."

    prompt = f"""
당신의 분석자 역할: {analyst_label}
아래 데이터를 바탕으로 {name}({ticker}) 종목에 대한 전문 투자 브리핑을 작성하세요.

## 기본 데이터 ({today} 기준)
- 시장: {market}
- 데이터 출처: {stock.get('data_source','')}
- 종가: {close_str}
- 등락률: {change_str}
- 거래량: {volume_str}
- 수급: {investor_str}
- 경고/비고: {stock.get('warning','') or stock.get('error','') or '없음'}

## 주가 추이
{history_str}

## 정량 지표
{metrics_str}

## 국내 뉴스
{domestic_news}

## 해외 뉴스
{intl_news}

## 사용자가 입력한 URL/파일 기반 RAG 참고자료
{rag_context}

필수 항목:
1. 종목 현황 요약
2. 주가 추이와 이동평균/변동성 해석
3. 외인·기관·개인 수급 분석. 데이터 없으면 한계 명시
4. 뉴스와 사용자가 제공한 URL/파일 정보의 투자 시사점
5. 내일 예상 방향: UP/DOWN/NEUTRAL
6. 예상 등락률 범위
7. 매매전략: 진입, 분할매수, 익절, 손절, 관망 기준
8. 리스크 요인
9. 투자 참고용 면책
"""
    return call_llm(prompt, system=system, max_tokens=1800)


def generate_portfolio_brief(stocks: list[dict], news_data: dict, analyst_key: str, rag_chunks: list[RagChunk] | None = None) -> str:
    today = date.today().isoformat()
    stock_lines = []
    for s in stocks:
        name = s.get("name", s.get("ticker", ""))
        close = s.get("close")
        change = s.get("change_rate")
        close_str = f"{close:,.0f}" if close is not None else "N/A"
        change_str = f"{change:+.2f}%" if change is not None else "N/A"
        metrics = s.get("metrics", {})
        stock_lines.append(
            f"- {name}({s.get('ticker','')}): {close_str} / {change_str} / "
            f"방향={metrics.get('heuristic_direction','N/A')} / 예상={metrics.get('heuristic_expected_change_pct','N/A')}%"
        )
    stocks_text = "\n".join(stock_lines)
    query = " ".join([s.get("name", "") + " " + s.get("ticker", "") for s in stocks]) + " 포트폴리오 투자전략 리스크"
    rag_context = format_rag_context(retrieve(rag_chunks or [], query, top_k=10), max_chars=7000)
    analyst_label = get_analyst_label(analyst_key)
    system = get_analyst_system(analyst_key) + "\n포트폴리오 전체 관점의 실행 가능한 전략을 한국어로 작성한다."
    prompt = f"""
분석자 역할: {analyst_label}
오늘({today}) 아래 종목들에 대한 종합 투자전략 리포트를 작성하세요.

## 종목 현황
{stocks_text}

## 사용자가 제공한 URL/파일 기반 RAG 참고자료
{rag_context}

필수 항목:
1. 오늘 시장/포트폴리오 핵심 요약
2. 가장 강한 종목과 가장 주의할 종목
3. 단기 트레이딩 전략
4. 스윙/중기 전략
5. 외인·기관·개인 수급과 글로벌 뉴스 반영
6. 내일 전체 대응전략
7. 종목별 예상 UP/DOWN/NEUTRAL 요약
8. 리스크 관리 체크리스트
9. 투자 참고용 면책
"""
    return call_llm(prompt, system=system, max_tokens=2600)


def build_full_report_text(stocks: list[dict], stock_briefs: list[str], portfolio_brief: str, analyst_key: str, external_docs: list[dict] | None = None) -> str:
    today = date.today().isoformat()
    sep = "=" * 70
    external_summary = "\n".join(
        f"- {d.get('title') or d.get('source')} ({d.get('source')})" + (f" [오류: {d.get('error')}]" if d.get('error') else "")
        for d in (external_docs or [])
    ) or "추가 URL/파일 없음"
    sections = [
        "📊 주식 AI 브리핑 최종 리포트",
        f"기준일: {today}",
        f"분석자: {get_analyst_label(analyst_key)}",
        sep,
        "【 추가 입력자료 / RAG 소스 】",
        external_summary,
        sep,
        "【 포트폴리오 종합 전략 】",
        portfolio_brief,
        sep,
    ]
    for stock, brief in zip(stocks, stock_briefs):
        name = stock.get("name", stock.get("ticker", ""))
        sections += [f"【 {name}({stock.get('ticker','')}) 개별 분석 】", brief, "-" * 50]
    sections += [sep, "본 리포트는 AI 분석 기반의 투자 참고자료이며, 최종 투자 결정과 책임은 사용자에게 있습니다."]
    return "\n\n".join(sections)
