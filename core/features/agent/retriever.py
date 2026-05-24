"""Hybrid retriever — vector search + live SQL queries for real-time platform stats."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.agent.vector_store import semantic_search

logger = logging.getLogger(__name__)


async def get_platform_stats(db: AsyncSession) -> dict:
    """Pull real-time statistics from PostgreSQL for RAG context."""
    stats: dict = {}

    queries = {
        "assets_by_status": """
            SELECT status, COUNT(*) as count, SUM(current_value) as total_value
            FROM assets GROUP BY status ORDER BY count DESC
        """,
        "assets_by_type": """
            SELECT asset_type, COUNT(*) as count, SUM(nominal_value) as total_nominal
            FROM assets GROUP BY asset_type ORDER BY count DESC
        """,
        "recent_transactions": """
            SELECT tx_type, COUNT(*) as count, SUM(amount) as total_amount,
                   MAX(created_at) as last_tx
            FROM transactions
            WHERE created_at > now() - interval '30 days'
            GROUP BY tx_type ORDER BY count DESC
        """,
        "compliance_summary": """
            SELECT
                kyc_status, COUNT(*) as count,
                AVG(aml_score)::numeric(5,4) as avg_aml_score,
                risk_category
            FROM compliance_records
            GROUP BY kyc_status, risk_category
            ORDER BY count DESC
        """,
        "high_risk_users": """
            SELECT COUNT(*) as count FROM compliance_records
            WHERE aml_score > 0.60 OR risk_category IN ('ELEVE', 'CRITIQUE')
        """,
        "frozen_assets": """
            SELECT COUNT(*) as count, SUM(current_value) as frozen_value
            FROM assets WHERE status = 'GELE'
        """,
        "total_volume_30d": """
            SELECT COALESCE(SUM(amount), 0) as volume
            FROM transactions
            WHERE created_at > now() - interval '30 days'
              AND tx_type = 'TRANSFERT'
        """,
        "sar_count": """
            SELECT status, COUNT(*) as count FROM sar_reports GROUP BY status
        """,
        "organizations": """
            SELECT org_type, COUNT(*) as count, bool_and(is_active) as all_active
            FROM organizations GROUP BY org_type
        """,
        "top_assets_by_value": """
            SELECT asset_name, asset_type, current_value, currency, status
            FROM assets ORDER BY current_value DESC LIMIT 5
        """,
        "regulatory_flags_30d": """
            SELECT COUNT(*) as flagged_count FROM transactions
            WHERE regulatory_flag = true
              AND created_at > now() - interval '30 days'
        """,
    }

    for key, query in queries.items():
        try:
            result = await db.execute(text(query))
            rows = result.fetchall()
            if rows:
                stats[key] = [dict(zip(result.keys(), row, strict=False)) for row in rows]
            else:
                stats[key] = []
        except Exception as exc:
            logger.debug(f"[RETRIEVER] Stats query '{key}' failed: {exc}")
            stats[key] = []

    stats["timestamp"] = datetime.now(UTC).isoformat()
    return stats


def _format_stats_as_markdown(stats: dict) -> str:
    """Convert stats dict to rich markdown tables for the LLM context."""
    sections = [f"### Données en temps réel — {stats.get('timestamp', 'N/A')}\n"]

    # Assets by status
    rows = stats.get("assets_by_status", [])
    if rows:
        sections.append("**Actifs par statut :**")
        sections.append("| Statut | Nb actifs | Valeur totale (EUR) |")
        sections.append("|--------|-----------|---------------------|")
        for r in rows:
            val = f"{float(r.get('total_value') or 0):,.2f}" if r.get("total_value") else "N/A"
            sections.append(f"| {r['status']} | {r['count']} | {val} |")
        sections.append("")

    # Assets by type
    rows = stats.get("assets_by_type", [])
    if rows:
        sections.append("**Actifs par type :**")
        sections.append("| Type | Nb | Valeur nominale (EUR) |")
        sections.append("|------|----|-----------------------|")
        for r in rows:
            nom = f"{float(r.get('total_nominal') or 0):,.2f}" if r.get("total_nominal") else "N/A"
            sections.append(f"| {r['asset_type']} | {r['count']} | {nom} |")
        sections.append("")

    # Top assets
    rows = stats.get("top_assets_by_value", [])
    if rows:
        sections.append("**Top 5 actifs par valeur actuelle :**")
        sections.append("| Nom | Type | Valeur | Devise | Statut |")
        sections.append("|-----|------|--------|--------|--------|")
        for r in rows:
            val = f"{float(r.get('current_value') or 0):,.2f}" if r.get("current_value") else "N/A"
            sections.append(f"| {r['asset_name']} | {r['asset_type']} | {val} | {r['currency']} | {r['status']} |")
        sections.append("")

    # Transactions (30 days)
    rows = stats.get("recent_transactions", [])
    if rows:
        sections.append("**Transactions (30 derniers jours) :**")
        sections.append("| Type | Nb | Volume total (EUR) | Dernière |")
        sections.append("|------|----|--------------------|----------|")
        for r in rows:
            amt = f"{float(r.get('total_amount') or 0):,.2f}" if r.get("total_amount") else "N/A"
            last = str(r.get("last_tx", ""))[:10] if r.get("last_tx") else "N/A"
            sections.append(f"| {r['tx_type']} | {r['count']} | {amt} | {last} |")
        sections.append("")

    # Volume total
    vol_rows = stats.get("total_volume_30d", [])
    if vol_rows:
        vol = float(vol_rows[0].get("volume") or 0)
        sections.append(f"**Volume total transferts (30j) :** {vol:,.2f} EUR\n")

    # Compliance
    rows = stats.get("compliance_summary", [])
    if rows:
        sections.append("**Dossiers de conformité :**")
        sections.append("| Statut KYC | Catégorie risque | Nb | Score AML moyen |")
        sections.append("|------------|------------------|----|-----------------|")
        for r in rows:
            aml = f"{float(r.get('avg_aml_score') or 0):.4f}" if r.get("avg_aml_score") else "N/A"
            sections.append(f"| {r['kyc_status']} | {r['risk_category']} | {r['count']} | {aml} |")
        sections.append("")

    # High risk
    hr = stats.get("high_risk_users", [])
    if hr:
        sections.append(f"**Utilisateurs haut risque (AML > 0.60) :** {hr[0].get('count', 0)}\n")

    # Frozen
    fr = stats.get("frozen_assets", [])
    if fr and fr[0].get("count"):
        frozen_val = f"{float(fr[0].get('frozen_value') or 0):,.2f}"
        sections.append(f"**Actifs gelés :** {fr[0]['count']} (valeur totale : {frozen_val} EUR)\n")

    # SAR
    sar_rows = stats.get("sar_count", [])
    if sar_rows:
        sar_str = ", ".join(f"{r['status']}: {r['count']}" for r in sar_rows)
        sections.append(f"**Rapports SAR :** {sar_str}\n")

    # Regulatory flags
    rf = stats.get("regulatory_flags_30d", [])
    if rf:
        sections.append(f"**Transactions réglementaires flagguées (30j) :** {rf[0].get('flagged_count', 0)}\n")

    return "\n".join(sections)


async def build_context(query: str, db: AsyncSession, n_results: int = 5) -> tuple[str, list[dict]]:
    """Build the full RAG context. Returns (context_str, sources_list)."""
    context_parts: list[str] = []
    sources: list[dict] = []

    # 1. Semantic search in knowledge base
    try:
        chunks = semantic_search(query, n_results=n_results)
        if chunks:
            context_parts.append("## Base de connaissances (références réglementaires & techniques)\n")
            for chunk in chunks:
                context_parts.append(
                    f"**[{chunk['metadata'].get('title', 'Document')}]** "
                    f"(pertinence: {chunk['relevance']:.0%})\n"
                    f"{chunk['text']}\n"
                )
                sources.append({
                    "title": chunk["metadata"].get("title", "Document"),
                    "relevance": round(chunk["relevance"], 3),
                    "preview": chunk["text"][:120].strip(),
                })
    except Exception as exc:
        logger.warning(f"[RETRIEVER] Vector search failed: {exc}")

    # 2. Live platform statistics
    try:
        stats = await get_platform_stats(db)
        context_parts.append("## Statistiques plateforme (temps réel)\n")
        context_parts.append(_format_stats_as_markdown(stats))
    except Exception as exc:
        logger.warning(f"[RETRIEVER] Stats retrieval failed: {exc}")

    context = "\n\n".join(context_parts) if context_parts else "Aucun contexte disponible."
    return context, sources
