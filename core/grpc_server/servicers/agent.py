"""gRPC servicer for the Agent (RAG) service."""
from __future__ import annotations

import json
import logging

import grpc
import grpc.aio

from core.config import settings
from core.core.database import AsyncSessionLocal
from core.features.agent.rag_pipeline import answer, answer_stream
from core.features.agent.vector_store import (
    _get_collection,
    index_knowledge_base,
    semantic_search,
)
from core.grpc_generated import agent_pb2, agent_pb2_grpc

logger = logging.getLogger(__name__)


def _gen_kwargs(req: agent_pb2.ChatRequest) -> dict:
    return dict(
        temperature=req.temperature or 0.4,
        max_tokens=req.max_tokens or 4096,
        top_p=req.top_p or 0.95,
        frequency_penalty=req.frequency_penalty or 0.0,
        presence_penalty=req.presence_penalty or 0.0,
        n_results=req.n_results or 5,
        use_rag=req.use_rag if req.HasField("use_rag") else True,  # type: ignore[attr-defined]
        style_preset=req.style_preset or "auto",
    )


class AgentServicer(agent_pb2_grpc.AgentServiceServicer):

    async def Chat(
        self,
        request: agent_pb2.ChatRequest,
        context: grpc.aio.ServicerContext,
    ) -> agent_pb2.ChatResponse:
        history = [{"role": m.role, "content": m.content} for m in request.history]
        async with AsyncSessionLocal() as db:
            try:
                result, sources, time_ms = await answer(
                    request.message, db, history, **_gen_kwargs(request)
                )
            except Exception as exc:
                logger.error(f"[AGENT] Chat error: {exc}")
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

        proto_sources = [
            agent_pb2.SourceDocument(
                content=s.get("content", ""),
                source=s.get("source", ""),
                relevance=float(s.get("relevance", 0)),
            )
            for s in sources
        ]
        return agent_pb2.ChatResponse(
            answer=result,
            sources_used=len(sources),
            sources=proto_sources,
            time_ms=time_ms,
        )

    async def ChatStream(
        self,
        request: agent_pb2.ChatRequest,
        context: grpc.aio.ServicerContext,
    ):
        """Server-streaming: yield ChatChunk messages as the LLM generates tokens."""
        history = [{"role": m.role, "content": m.content} for m in request.history]
        async with AsyncSessionLocal() as db:
            try:
                async for raw in answer_stream(
                    request.message, db, history, **_gen_kwargs(request)
                ):
                    if raw.startswith("\x00META:"):
                        yield agent_pb2.ChatChunk(
                            is_final=True, meta=raw[6:]
                        )
                    else:
                        yield agent_pb2.ChatChunk(token=raw, is_final=False)
            except Exception as exc:
                logger.error(f"[AGENT] Stream error: {exc}")
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def TriggerIndexing(
        self,
        request: agent_pb2.IndexRequest,
        context: grpc.aio.ServicerContext,
    ) -> agent_pb2.IndexResponse:
        role = context.user_payload.get("role", "")
        if role not in ("SUPER_ADMIN", "COMPLIANCE_OFFICER", "AUDITEUR"):
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient role")
        try:
            index_knowledge_base()
            return agent_pb2.IndexResponse(
                status="indexed",
                message="Knowledge base re-indexed successfully.",
            )
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def SemanticSearch(
        self,
        request: agent_pb2.SearchRequest,
        context: grpc.aio.ServicerContext,
    ) -> agent_pb2.SearchResponse:
        try:
            results = semantic_search(request.query, n_results=request.n or 5)
            return agent_pb2.SearchResponse(results_json=json.dumps(results))
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def GetAgentStatus(
        self,
        request: agent_pb2.StatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> agent_pb2.AgentStatusResponse:
        try:
            doc_count = _get_collection().count()
        except Exception:
            doc_count = -1
        has_key = bool(settings.groq_api_key)
        return agent_pb2.AgentStatusResponse(
            groq_configured=has_key,
            model=settings.groq_model,
            knowledge_base_docs=doc_count,
            status="ready" if has_key else "missing_api_key",
        )
