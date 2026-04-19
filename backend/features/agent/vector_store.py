"""ChromaDB vector store — index and retrieve knowledge chunks."""
from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

from backend.features.agent.knowledge_base import KNOWLEDGE_CHUNKS

logger = logging.getLogger(__name__)

CHROMA_PATH = Path("data/chromadb")
COLLECTION_NAME = "rwa_knowledge"

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None
_ef: ONNXMiniLM_L6_V2 | None = None


def _get_embedding_function() -> ONNXMiniLM_L6_V2:
    global _ef
    if _ef is None:
        _ef = ONNXMiniLM_L6_V2()
    return _ef


def _get_collection() -> chromadb.Collection:
    global _client, _collection
    if _collection is not None:
        return _collection

    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def index_knowledge_base() -> None:
    """Embed and store all static knowledge chunks into ChromaDB."""
    collection = _get_collection()

    existing = collection.get(include=[])
    existing_ids = set(existing["ids"])

    to_add_ids, to_add_docs, to_add_meta = [], [], []

    for chunk in KNOWLEDGE_CHUNKS:
        if chunk["id"] in existing_ids:
            continue
        text = f"{chunk['title']}\n\n{chunk['content']}"
        to_add_ids.append(chunk["id"])
        to_add_docs.append(text)
        to_add_meta.append({"category": chunk["category"], "title": chunk["title"]})

    if to_add_ids:
        collection.add(
            ids=to_add_ids,
            documents=to_add_docs,
            metadatas=to_add_meta,
        )
        logger.info(f"[VECTOR] Indexed {len(to_add_ids)} knowledge chunks into ChromaDB.")
    else:
        logger.info("[VECTOR] Knowledge base already up to date.")


def add_document(doc_id: str, text: str, metadata: dict | None = None) -> None:
    """Add or update a single document in the vector store."""
    collection = _get_collection()

    existing = collection.get(ids=[doc_id], include=[])
    if existing["ids"]:
        collection.update(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )
    else:
        collection.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )


def semantic_search(query: str, n_results: int = 5, category: str | None = None) -> list[dict]:
    """Search the vector store for the most relevant chunks."""
    collection = _get_collection()

    if collection.count() == 0:
        return []

    where_filter = {"category": category} if category else None

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
        where=where_filter,
    )

    chunks = []
    for i, doc in enumerate(results["documents"][0]):
        distance = results["distances"][0][i]
        relevance = round(1 - distance, 3)
        if relevance < 0.3:
            continue
        chunks.append({
            "text": doc,
            "metadata": results["metadatas"][0][i],
            "relevance": relevance,
        })

    return sorted(chunks, key=lambda x: x["relevance"], reverse=True)
