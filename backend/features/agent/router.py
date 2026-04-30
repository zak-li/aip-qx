"""Agent API — RAG-powered question answering over RWA platform data."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.dependencies import get_current_user, get_db
from backend.features.agent.rag_pipeline import answer, answer_stream
from backend.features.agent.vector_store import _get_collection, index_knowledge_base, semantic_search
from backend.features.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    stream: bool = Field(default=True)
    # Generation params
    temperature: float = Field(default=0.4, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=256, le=8192)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    # Retrieval params
    n_results: int = Field(default=5, ge=1, le=20)
    use_rag: bool = Field(default=True)
    # Style params
    style_preset: str = Field(default="auto")


class ChatResponse(BaseModel):
    answer: str
    sources_used: int
    sources: list[dict] = []
    time_ms: int = 0


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RAG-powered chat endpoint. Supports streaming (SSE) and synchronous modes."""
    history = [{"role": m.role, "content": m.content} for m in request.history]

    gen_kwargs = dict(
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        frequency_penalty=request.frequency_penalty,
        presence_penalty=request.presence_penalty,
        n_results=request.n_results,
        use_rag=request.use_rag,
        style_preset=request.style_preset,
    )

    if request.stream:
        async def event_stream():
            try:
                async for raw in answer_stream(request.message, db, history, **gen_kwargs):
                    if raw.startswith("\x00META:"):
                        payload = json.dumps({"meta": json.loads(raw[6:])}, ensure_ascii=False)
                    else:
                        payload = json.dumps({"token": raw}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as exc:
                logger.error(f"[AGENT] Stream error: {exc}")
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        try:
            result, sources, time_ms = await answer(request.message, db, history, **gen_kwargs)
            return ChatResponse(answer=result, sources_used=len(sources), sources=sources, time_ms=time_ms)
        except Exception as exc:
            logger.error(f"[AGENT] Chat error: {exc}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erreur agent: {exc}") from exc


@router.post("/index", status_code=202)
async def trigger_indexing(current_user: User = Depends(get_current_user)) -> dict:
    """Trigger re-indexing of the knowledge base into ChromaDB."""
    if current_user.role not in ("SUPER_ADMIN", "COMPLIANCE_OFFICER", "AUDITEUR"):
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    try:
        index_knowledge_base()
        return {"status": "indexed", "message": "Base de connaissances réindexée avec succès."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur d'indexation: {exc}") from exc


@router.get("/search")
async def semantic_search_endpoint(
    query: str, n: int = 5,
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    try:
        return semantic_search(query, n_results=n)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/status")
async def agent_status(current_user: User = Depends(get_current_user)) -> dict:
    has_key = bool(settings.groq_api_key)
    try:
        doc_count = _get_collection().count()
    except Exception:
        doc_count = -1
    return {
        "groq_configured": has_key,
        "model": settings.groq_model,
        "knowledge_base_docs": doc_count,
        "status": "ready" if has_key else "missing_api_key",
    }
