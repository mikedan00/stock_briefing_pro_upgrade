"""
config.py — 환경변수, Streamlit secrets, HF Router/Gmail 설정
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def get_secret(name: str, default: str = "") -> str:
    try:
        import streamlit as st
        value = st.secrets.get(name, None)
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


HF_TOKEN = get_secret("HF_TOKEN", "")
HF_API_URL = "https://router.huggingface.co/v1/chat/completions"
HF_ROUTER_MODEL = "google/gemma-4-26B-A4B-it:deepinfra"
HF_MODEL_CANDIDATES = [
    "google/gemma-4-26B-A4B-it:deepinfra",
    "google/gemma-4-26B-A4B-it:novita",
    "google/gemma-4-31B-it:deepinfra",
    "google/gemma-4-31B-it:together",
    "Qwen/Qwen3.5-9B:together",
    "Qwen/Qwen2.5-7B-Instruct:together",
]

GMAIL_USER = get_secret("GMAIL_USER", "")
GMAIL_APP_PASSWORD = get_secret("GMAIL_APP_PASSWORD", "")

MAX_STOCKS = 10
MAX_NEWS_PER_BUCKET = 10
MAX_RAG_CHUNKS = 10
