"""RAG pipeline — orchestrates retrieval + generation."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.agent.groq_client import generate, generate_stream
from backend.features.agent.retriever import build_context

logger = logging.getLogger(__name__)


async def answer_stream(
    query: str,
    db: AsyncSession,
    history: list[dict] | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4096,
    top_p: float = 0.95,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    n_results: int = 5,
    use_rag: bool = True,
    style_preset: str = "auto",
) -> AsyncGenerator[str, None]:
    """Full RAG pipeline with streaming. Yields tokens, then a META event."""
    t0 = time.monotonic()
    logger.info(f"[RAG] Query: {query[:80]}... (temp={temperature}, rag={use_rag}, style={style_preset})")

    if use_rag:
        context, sources = await build_context(query, db, n_results=n_results)
    else:
        context = "_Mode LLM pur — aucune donnée RAG récupérée._"
        sources = []

    async for token in generate_stream(
        query, context, history,
        temperature=temperature, max_tokens=max_tokens, top_p=top_p,
        frequency_penalty=frequency_penalty, presence_penalty=presence_penalty,
        style_preset=style_preset,
    ):
        yield token

    elapsed = round((time.monotonic() - t0) * 1000)
    yield f"\x00META:{json.dumps({'sources': sources, 'time_ms': elapsed})}"


async def answer(
    query: str,
    db: AsyncSession,
    history: list[dict] | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4096,
    top_p: float = 0.95,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    n_results: int = 5,
    use_rag: bool = True,
    style_preset: str = "auto",
) -> tuple[str, list[dict], int]:
    """Full RAG pipeline — non-streaming. Returns (text, sources, time_ms)."""
    t0 = time.monotonic()
    if use_rag:
        context, sources = await build_context(query, db, n_results=n_results)
    else:
        context = "_Mode LLM pur — aucune donnée RAG récupérée._"
        sources = []

    text = await generate(
        query, context, history,
        temperature=temperature, max_tokens=max_tokens, top_p=top_p,
        frequency_penalty=frequency_penalty, presence_penalty=presence_penalty,
        style_preset=style_preset,
    )
    return text, sources, round((time.monotonic() - t0) * 1000)
