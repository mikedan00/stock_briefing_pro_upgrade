
"""
rag_engine.py — 추가 URL/파일 정보를 LLM 프롬프트에 반영하기 위한 경량 RAG
외부 임베딩 없이 토큰 겹침 기반으로 관련 chunk를 선택한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RagChunk:
    source: str
    title: str
    text: str
    score: float = 0.0


def tokenize(text: str) -> set[str]:
    toks = re.findall(r"[가-힣A-Za-z0-9]{2,}", (text or "").lower())
    stop = {"the", "and", "for", "with", "this", "that", "from", "으로", "에서", "그리고", "대한"}
    return {t for t in toks if t not in stop}


def split_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i+size])
        i += max(1, size - overlap)
    return chunks


def build_chunks(docs: list[dict]) -> list[RagChunk]:
    chunks = []
    for doc in docs or []:
        text = doc.get("text", "") or ""
        if not text.strip():
            continue
        source = doc.get("source", "unknown")
        title = doc.get("title", source)
        for ch in split_text(text):
            chunks.append(RagChunk(source=source, title=title, text=ch))
    return chunks


def retrieve(chunks: list[RagChunk], query: str, top_k: int = 8) -> list[RagChunk]:
    q_tokens = tokenize(query)
    if not q_tokens:
        return chunks[:top_k]
    scored = []
    for ch in chunks:
        c_tokens = tokenize(ch.title + " " + ch.text)
        if not c_tokens:
            continue
        overlap = len(q_tokens & c_tokens)
        score = overlap / max(1, len(q_tokens)) + min(0.3, len(c_tokens) / 1000)
        scored.append(RagChunk(ch.source, ch.title, ch.text, score))
    scored.sort(key=lambda x: x.score, reverse=True)
    return [x for x in scored[:top_k] if x.score > 0] or scored[:top_k]


def format_rag_context(chunks: list[RagChunk], max_chars: int = 5000) -> str:
    parts = []
    total = 0
    for i, ch in enumerate(chunks, 1):
        block = f"[RAG {i}] source={ch.source}\ntitle={ch.title}\ncontent={ch.text}\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts) if parts else "추가 RAG 참고자료 없음"
