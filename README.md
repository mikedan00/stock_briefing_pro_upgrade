# 주식 AI 브리핑 PRO 업그레이드 버전

Claude 버전의 장점(실전 Streamlit UI, pykrx 함수 내부 import, HF Router provider suffix, deep-translator 번역)을 기반으로 GPT 버전의 장점(Word/PPT 다운로드, 정량 지표, 이메일 검증/첨부, RAG 구조)을 결합한 버전입니다.

## 주요 기능

1. 최대 10개 주식 입력
   - 국내 종목명/6자리 코드: pykrx 우선
   - 해외 티커: yfinance
   - pykrx 실패 시 국내 가격은 yfinance `.KS`/`.KQ` fallback 시도

2. 뉴스 수집
   - 네이버 뉴스 RSS
   - 구글 뉴스 KR/EN RSS
   - 해외 종목 yfinance 뉴스
   - 영어뉴스는 `deep-translator`로 한국어 번역

3. 추가 분석자료 입력
   - 사용자가 URL 입력 가능
   - Excel/PDF/Word/PPT/TXT/HWP/HWPX/이미지 업로드 가능
   - 읽어들인 내용을 경량 RAG chunk로 만들어 AI 분석 프롬프트에 반영

4. 5가지 AI 분석자 선택
   - A. 20년 경험 전문 투자 트레이더
   - B. 기관투자 측면 트레이더
   - C. 외인투자 트레이더
   - D. 보수적 안정성 성향 트레이더
   - E. 적극적 위험감수 트레이더

5. 최종 리포트
   - TXT 다운로드
   - Word `.docx` 다운로드
   - 요약 PPT `.pptx` 다운로드
   - Gmail 발송 및 Word/PPT 첨부 선택

## 로컬 실행

```bash
cd stock_briefing_pro_upgrade
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

macOS/Linux:

```bash
cd stock_briefing_pro_upgrade
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## Streamlit Cloud 배포

1. GitHub에 업로드
2. Streamlit Cloud에서 `app.py` 선택
3. Secrets에 아래 설정

```toml
HF_TOKEN = "hf_본인토큰"
GMAIL_USER = "yourgmail@gmail.com"
GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"
```

## 주의사항

- pykrx는 KRX/Naver 데이터를 스크래핑하므로 과도한 반복 호출을 피하세요.
- HWP 구버전은 파일 내부 `PrvText`가 있을 때만 안정적으로 텍스트 추출됩니다. HWPX/PDF/DOCX 변환 업로드가 더 정확합니다.
- 이미지 OCR은 서버에 OCR 엔진이 있을 때만 동작합니다. Streamlit Cloud에서는 이미지의 핵심 텍스트를 별도 입력란에 붙여넣는 것을 권장합니다.
- 본 앱의 리포트는 투자 참고용이며 최종 투자 판단은 사용자 책임입니다.
