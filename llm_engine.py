
"""
llm_engine.py — HuggingFace Router 연동
Claude 버전의 requests 직접 호출 방식 유지.
"""
from __future__ import annotations

import os
import requests
import config


def _get_token() -> str:
    return os.environ.get("HF_TOKEN") or config.HF_TOKEN


def _get_model() -> str:
    return os.environ.get("HF_MODEL_OVERRIDE") or config.HF_ROUTER_MODEL


def call_llm(prompt: str, system: str = "", max_tokens: int = 2048, temperature: float = 0.45) -> str:
    token = _get_token()
    model = _get_model()
    if not token:
        return "[오류] HF_TOKEN이 설정되지 않았습니다. 사이드바 또는 Streamlit Secrets에 입력해주세요."
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": False}
    try:
        resp = requests.post(config.HF_API_URL, headers=headers, json=payload, timeout=150)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        body = e.response.text[:800] if e.response is not None else ""
        return f"[LLM HTTP 오류 {status}] {body}"
    except requests.exceptions.Timeout:
        return "[LLM 오류] 요청 시간 초과. 모델 서버가 바쁩니다. 잠시 후 재시도해주세요."
    except Exception as e:
        return f"[LLM 오류] {type(e).__name__}: {e}"
