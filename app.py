
"""
주식 AI 브리핑 PRO
- Claude 버전 UX/pykrx 구조 반영
- URL/파일 RAG, 5가지 AI 분석자, Word/PPT 다운로드 추가
"""
from __future__ import annotations

import os
import re
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="주식 AI 브리핑 PRO", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
APP_BUILD = "2026-06-07-v5-yahoo-english-news-fix"
# v5: 해외뉴스는 Yahoo Finance 티커(005930.KS)와 영어 회사명(Samsung Electronics)을 최우선 사용하고, 모든 해외뉴스 제목/요약을 한국어 번역한다.

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&family=JetBrains+Mono:wght@400;600&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background: linear-gradient(135deg, #0a0e1a 0%, #0f1629 50%, #0a0e1a 100%); }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0d1117 0%, #161b2e 100%); border-right: 1px solid #1e3a5f; }
.page-header { background:linear-gradient(135deg,#0d1b4b,#1a237e,#0d47a1); border-radius:16px; padding:28px 32px; margin-bottom:24px; border:1px solid #1565c0; box-shadow:0 8px 32px rgba(13,71,161,.3); }
.page-header h1 { color:#fff; font-size:1.8rem; font-weight:900; margin:0; }
.page-header p { color:#90caf9; margin:6px 0 0 0; font-size:.95rem; }
.section-title { color:#64b5f6; font-size:1.0rem; font-weight:700; letter-spacing:.5px; margin:20px 0 10px 0; padding-bottom:6px; border-bottom:1px solid #1e3a5f; }
.metric-card { background: linear-gradient(135deg,#111827,#1a2540); border:1px solid #1e3a5f; border-radius:12px; padding:16px 20px; margin:6px 0; box-shadow:0 4px 16px rgba(0,0,0,.4); }
.metric-card h3 { color:#64b5f6; font-size:.8rem; font-weight:500; letter-spacing:1px; text-transform:uppercase; margin:0 0 6px 0; }
.metric-card .value { font-family:'JetBrains Mono',monospace; font-size:1.4rem; font-weight:700; color:#e2e8f0; margin:0; }
.news-item { background:#111827; border-left:3px solid #1565c0; border-radius:0 8px 8px 0; padding:10px 14px; margin:6px 0; font-size:.88rem; color:#cfd8dc; line-height:1.5; }
.news-item .news-source { font-size:.75rem; color:#546e7a; margin-top:4px; }
.news-item a { color:#90caf9; text-decoration:none; }
.report-box { background:#0d1117; border:1px solid #1e3a5f; border-radius:12px; padding:24px; font-size:.92rem; line-height:1.9; color:#cfd8dc; white-space:pre-wrap; }
.model-badge { background:rgba(21,101,192,.2); color:#64b5f6; border:1px solid #1565c0; border-radius:6px; padding:4px 10px; font-size:.78rem; font-family:'JetBrains Mono',monospace; }
</style>
""", unsafe_allow_html=True)

for k, v in {
    "stocks_data": [], "news_data": {}, "external_docs": [], "rag_chunks": [],
    "stock_briefs": {}, "portfolio_brief": "", "full_report": "",
    "data_loaded": False, "briefs_generated": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

with st.sidebar:
    st.markdown("## ⚙️ 설정")
    st.markdown("---")
    st.markdown("### 🤖 AI 엔진")
    hf_token = st.text_input("HuggingFace Token", type="password", value=os.getenv("HF_TOKEN", ""), placeholder="hf_xxxxxxxxxxxx")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
    import config as cfg
    selected_model = st.selectbox("모델 선택", options=cfg.HF_MODEL_CANDIDATES, index=0)
    os.environ["HF_MODEL_OVERRIDE"] = selected_model
    st.markdown(f'<div class="model-badge">▶ {selected_model}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🧠 AI 분석자")
    from analyst_profiles import ANALYST_PROFILES
    analyst_key = st.selectbox("분석자 선택", options=list(ANALYST_PROFILES.keys()), format_func=lambda k: ANALYST_PROFILES[k]["label"])

    st.markdown("---")
    st.markdown("### 📧 Gmail 발송")
    gmail_user = st.text_input("발신 Gmail", value=os.getenv("GMAIL_USER", ""), placeholder="your@gmail.com")
    gmail_pw = st.text_input("앱 비밀번호", type="password", value=os.getenv("GMAIL_APP_PASSWORD", ""), placeholder="xxxx xxxx xxxx xxxx")
    to_email = st.text_input("수신 이메일", placeholder="recipient@email.com")

st.markdown("""
<div class="page-header">
    <h1>📊 주식 AI 브리핑 PRO</h1>
    <p>pykrx · yfinance · 뉴스 · URL/파일 RAG · 5가지 AI 분석자 · Word/PPT 다운로드 · Gmail 발송</p>
</div>
""", unsafe_allow_html=True)
st.markdown(f"<p style='color:#546e7a;font-size:.85rem;'>📅 {date.today().strftime('%Y년 %m월 %d일')}</p>", unsafe_allow_html=True)

st.markdown('<div class="section-title">🔍 분석 종목 입력</div>', unsafe_allow_html=True)
col_in, col_hint = st.columns([3, 1])
with col_in:
    ticker_input = st.text_area("종목 입력 (쉼표·줄바꿈 구분, 최대 10개)", placeholder="삼성전자, SK하이닉스, AAPL, NVDA", height=90)
with col_hint:
    st.markdown("""
    <div style="background:#111827;border:1px solid #1e3a5f;border-radius:8px;padding:14px;font-size:.78rem;color:#90a4ae;margin-top:24px;">
    <b style="color:#64b5f6;">예시</b><br>삼성전자 · SK하이닉스<br>네이버 · 카카오<br>AAPL · NVDA · TSLA<br>MSFT · META · AMZN</div>
    """, unsafe_allow_html=True)

st.markdown('<div class="section-title">🔗 추가 분석자료 입력: URL + 파일 업로드</div>', unsafe_allow_html=True)
url_input = st.text_area("뉴스/분석 정보가 있는 URL 입력 (줄바꿈으로 여러 개)", placeholder="https://example.com/news-or-analysis", height=80)
uploaded_files = st.file_uploader(
    "분석자료 업로드: Excel, PDF, Word, PPT, TXT, HWP/HWPX, 이미지",
    type=["xlsx", "xls", "csv", "pdf", "docx", "pptx", "txt", "md", "hwp", "hwpx", "png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)


def parse_inputs(raw: str) -> list[str]:
    tokens = re.split(r"[,\n]+", raw.strip())
    seen, result = set(), []
    for t in tokens:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result[:10]

col_b1, col_b2, _ = st.columns([1.4, 1.4, 3])
with col_b1:
    btn_load = st.button("📥 데이터 수집 + RAG 구축", type="primary", use_container_width=True)
with col_b2:
    btn_report = st.button("🤖 AI 리포트 생성", use_container_width=True, disabled=not st.session_state.data_loaded)

if btn_load:
    inputs = parse_inputs(ticker_input)
    if not inputs:
        st.error("종목을 입력해주세요.")
    else:
        from stock_data import fetch_all_stocks
        from news_fetcher import fetch_all_news
        from external_sources import collect_external_sources
        from rag_engine import build_chunks
        with st.spinner(f"📡 {len(inputs)}개 종목 주가 수집 중..."):
            stocks = fetch_all_stocks(inputs)
            st.session_state.stocks_data = stocks
        progress = st.progress(0, text="📰 뉴스 수집 중...")
        news_data = {}
        for i, stock in enumerate(stocks):
            progress.progress((i + 1) / len(stocks), text=f"📰 {stock['name']} 뉴스 수집 중...")
            news_data[stock["ticker"]] = fetch_all_news(stock)
        st.session_state.news_data = news_data
        with st.spinner("🔎 URL/파일 자료 읽기 및 RAG 구축 중..."):
            urls = [u.strip() for u in url_input.splitlines() if u.strip()]
            external_docs = collect_external_sources(urls, uploaded_files or [])
            st.session_state.external_docs = external_docs
            st.session_state.rag_chunks = build_chunks(external_docs)
        st.session_state.data_loaded = True
        st.session_state.briefs_generated = False
        st.session_state.stock_briefs = {}
        st.session_state.portfolio_brief = ""
        st.session_state.full_report = ""
        success = [s for s in stocks if s.get("close") is not None]
        fail = [s for s in stocks if s.get("close") is None]
        st.success(f"✅ {len(success)}개 종목 수집 완료, RAG chunk {len(st.session_state.rag_chunks)}개 구축" + (f" / 실패 {len(fail)}개" if fail else ""))
        if fail:
            st.warning("수집 실패: " + ", ".join(f"{s['name']}({s.get('error','?')})" for s in fail))
        st.rerun()

if btn_report:
    token_check = os.environ.get("HF_TOKEN") or cfg.HF_TOKEN
    if not token_check:
        st.error("HuggingFace Token이 없습니다. 사이드바에서 입력하거나 Streamlit Secrets에 설정하세요.")
    else:
        from report_generator import generate_stock_brief, generate_portfolio_brief, build_full_report_text
        stocks = st.session_state.stocks_data
        news_data = st.session_state.news_data
        rag_chunks = st.session_state.rag_chunks
        stock_briefs = {}
        total = len(stocks) + 1
        progress = st.progress(0, text="🤖 AI 분석 시작...")
        for i, stock in enumerate(stocks):
            ticker = stock["ticker"]
            name = stock.get("name", ticker)
            progress.progress(i / total, text=f"🤖 {name} 분석 중...")
            stock_briefs[ticker] = generate_stock_brief(stock, news_data.get(ticker, {}), analyst_key, rag_chunks)
        progress.progress(len(stocks) / total, text="🤖 포트폴리오 종합 분석 중...")
        portfolio_brief = generate_portfolio_brief(stocks, news_data, analyst_key, rag_chunks)
        full_report = build_full_report_text(stocks, list(stock_briefs.values()), portfolio_brief, analyst_key, st.session_state.external_docs)
        st.session_state.stock_briefs = stock_briefs
        st.session_state.portfolio_brief = portfolio_brief
        st.session_state.full_report = full_report
        st.session_state.briefs_generated = True
        progress.progress(1.0, text="완료")
        st.success("✅ AI 리포트 생성 완료")
        st.rerun()

if st.session_state.data_loaded:
    stocks = st.session_state.stocks_data
    news_data = st.session_state.news_data
    tabs = st.tabs(["📈 주가 현황", "📰 뉴스", "📊 차트", "🔎 RAG 자료", "🤖 AI 브리핑", "📋 최종 리포트"])
    with tabs[0]:
        rows = []
        for s in stocks:
            m = s.get("metrics", {})
            rows.append({
                "종목": s.get("name"), "티커": s.get("ticker"), "시장": s.get("market"), "종가": s.get("close"),
                "등락률%": s.get("change_rate"), "거래량": s.get("volume"), "출처": s.get("data_source"),
                "이번주%": m.get("week_return_pct"), "이번달%": m.get("month_return_pct"), "6개월%": m.get("six_month_return_pct"),
                "MA5": m.get("ma5"), "MA20": m.get("ma20"), "MA60": m.get("ma60"),
                "예상방향": m.get("heuristic_direction"), "예상등락%": m.get("heuristic_expected_change_pct"),
                "비고": s.get("warning") or s.get("error") or "",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    # 중요: st.selectbox options에는 DataFrame을 포함한 dict 객체를 직접 넣지 않는다.
    # Streamlit은 widget 변경 여부를 old_value != new_value로 비교하는데,
    # dict 내부에 pandas DataFrame이 있으면 ValueError: truth value of a DataFrame is ambiguous가 발생한다.
    # 따라서 widget 값은 문자열 ticker만 사용하고, 실제 stock dict는 별도 매핑에서 조회한다.
    stock_by_ticker = {s.get("ticker"): s for s in stocks}
    ticker_options = [s.get("ticker") for s in stocks if s.get("ticker")]
    ticker_label = lambda t: f"{stock_by_ticker[t].get('name')} ({t})" if t in stock_by_ticker else str(t)

    with tabs[1]:
        selected_ticker = st.selectbox("종목 선택", options=ticker_options, format_func=ticker_label, key="news_stock_select_ticker_v5")
        selected = stock_by_ticker.get(selected_ticker, {})
        nd = news_data.get(selected_ticker, {})
        c1, c2 = st.columns(2)
        for col, title, items in [(c1, "🇰🇷 국내 뉴스", nd.get("domestic", [])), (c2, "🌐 해외 뉴스(번역)", nd.get("international", []))]:
            with col:
                st.markdown(f"### {title}")
                if not items:
                    st.warning("수집된 뉴스가 없습니다. 검색어/날짜 조건 또는 외부 뉴스 RSS 응답이 비어 있을 수 있습니다.")
                    if title.startswith("🌐") and nd.get("debug"):
                        with st.expander("해외뉴스 수집 진단 보기"):
                            st.json(nd.get("debug"))
                for item in items[:10]:
                    
                    original = item.get('original_title') or ''
                    original_html = f"<div style='font-size:.72rem;color:#78909c;margin-top:3px;'>원문: {original}</div>" if original and original != item.get('title','') else ""
                    st.markdown(f"<div class='news-item'><a href='{item.get('link','')}' target='_blank'>{item.get('title','')}</a><div class='news-source'>{item.get('source','')} · {item.get('published','')}</div>{original_html}</div>", unsafe_allow_html=True)
    with tabs[2]:
        selected_ticker = st.selectbox("차트 종목", options=ticker_options, format_func=ticker_label, key="chart_stock_select_ticker_v5")
        selected = stock_by_ticker.get(selected_ticker, {})
        period = st.radio("기간", ["week", "month", "6month"], format_func=lambda p: {"week":"이번주", "month":"이번달", "6month":"6개월"}[p], horizontal=True, key="chart_period_v5")
        df = selected.get("history", {}).get(period)
        if df is not None and not df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df["close"], mode="lines", name=selected.get("name")))
            if len(df) >= 2:
                import numpy as np
                x = np.arange(len(df)); y = df["close"].astype(float).values
                z = np.polyfit(x, y, 1); trend = np.poly1d(z)(x)
                fig.add_trace(go.Scatter(x=df.index, y=trend, mode="lines", name="추세선", line=dict(dash="dash")))
            fig.update_layout(template="plotly_dark", height=450)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("차트 데이터가 없습니다.")
    with tabs[3]:
        st.markdown("### URL/파일 RAG 자료")
        st.write(f"RAG chunk 수: {len(st.session_state.rag_chunks)}")
        for d in st.session_state.external_docs:
            with st.expander(f"{d.get('title') or d.get('source')}"):
                if d.get("error"):
                    st.warning(d.get("error"))
                st.write((d.get("text") or "")[:3000])
    with tabs[4]:
        if st.session_state.briefs_generated:
            for s in stocks:
                with st.expander(f"{s.get('name')} ({s.get('ticker')})", expanded=False):
                    st.markdown(st.session_state.stock_briefs.get(s["ticker"], ""))
            st.markdown("### 포트폴리오 종합")
            st.markdown(st.session_state.portfolio_brief)
        else:
            st.info("AI 리포트 생성 버튼을 눌러주세요.")
    with tabs[5]:
        report = st.session_state.full_report
        if report:
            st.markdown(f"<div class='report-box'>{report}</div>", unsafe_allow_html=True)
            from document_exporter import make_docx_report, make_ppt_summary
            docx_bytes = make_docx_report(report)
            pptx_bytes = make_ppt_summary(report, stocks)
            st.download_button("📄 TXT 다운로드", report.encode("utf-8"), file_name=f"stock_report_{date.today()}.txt", mime="text/plain")
            st.download_button("📝 Word 다운로드", docx_bytes, file_name=f"stock_report_{date.today()}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            st.download_button("📊 PPT 요약 다운로드", pptx_bytes, file_name=f"stock_summary_{date.today()}.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
            st.markdown("### Gmail 발송")
            attach_word = st.checkbox("Word 파일 첨부", value=True)
            attach_ppt = st.checkbox("PPT 요약 첨부", value=False)
            if st.button("📧 Gmail로 발송"):
                from email_sender import send_report_email
                attachments = []
                if attach_word:
                    attachments.append((f"stock_report_{date.today()}.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
                if attach_ppt:
                    attachments.append((f"stock_summary_{date.today()}.pptx", pptx_bytes, "application/vnd.openxmlformats-officedocument.presentationml.presentation"))
                ok, msg = send_report_email(to_email, report, gmail_user, gmail_pw, attachments)
                st.success(msg) if ok else st.error(msg)
        else:
            st.info("최종 리포트가 아직 없습니다.")
