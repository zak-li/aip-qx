"""Gemini API client — generation with retry and thinking budget (google-genai SDK)."""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from google import genai
from google.genai import types

from backend.config import settings

logger = logging.getLogger(__name__)

GENERATION_MODEL = settings.gemini_model

_client: genai.Client | None = None

# Errors worth retrying
_RETRYABLE_CODES = {429, 503, 500}
_MAX_RETRIES = 4
_BASE_DELAY = 2.0


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured in .env")
        _client = genai.Client(api_key=api_key)
    return _client


SYSTEM_PROMPT = """Tu es un expert analyste financier et officier de conformité blockchain \
spécialisé dans la tokenisation d'actifs réels (RWA) sur Hyperledger Fabric.

Tu as accès en temps réel aux données de la plateforme :
- Actifs tokenisés (ISIN, valeur, statut, historique)
- Transactions blockchain (provenance, transferts, gels)
- Dossiers de conformité (KYC/AML/MiCA, scores de risque)
- Organisations du réseau Fabric (MSP, LEI)
- Alertes fraude Neo4j (flux circulaires, smurfing, layering)

**Format de réponse OBLIGATOIRE — applique TOUJOURS ces règles :**
1. Commence TOUJOURS par un titre `## ` qui résume l'analyse
2. Utilise des tableaux Markdown pour toutes les données structurées (minimum 3 colonnes)
3. Inclus des statistiques chiffrées avec pourcentages relatifs
4. Pour les structures de données, fournis des blocs ```json avec les schémas complets
5. Délimite chaque section avec `### ` et une ligne vide
6. Pour les analyses de risque, inclus un tableau de scoring (Score | Niveau | Action)
7. Pour les flux de transactions, utilise une timeline numérotée
8. Termine TOUJOURS par `### Recommandations` avec une liste à puces

Ne génère jamais de réponse vide. Si les données sont manquantes, dis-le explicitement dans un tableau.
Réponds en français sauf si la question est posée en anglais.
Sois exhaustif, précis et professionnel."""


def _build_contents(
    user_message: str,
    context: str,
    history: list[dict] | None,
) -> list[types.Content]:
    """Build the contents list for the Gemini API."""
    contents: list[types.Content] = []
    for msg in (history or []):
        role = "user" if msg["role"] == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part(text=msg["content"])])
        )

    full_prompt = (
        "## Contexte de la plateforme RWA (données en temps réel)\n\n"
        f"{context}\n\n"
        "---\n\n"
        "## Question\n\n"
        f"{user_message}"
    )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=full_prompt)])
    )
    return contents


def _make_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.2,
        top_p=0.95,
        max_output_tokens=16384,
        thinking_config=types.ThinkingConfig(thinking_budget=2048),
    )


def _is_retryable(exc: Exception) -> tuple[bool, float]:
    """Return (should_retry, suggested_delay_seconds).

    Daily quota exhaustion (PerDay/PerProject with limit exceeded) is NOT
    retryable — we'd just burn through retries for nothing.
    """
    import re
    msg = str(exc)

    # Daily quota — not retryable regardless of HTTP code
    if re.search(r"PerDay|Per.*Day|quota.*day|daily.*quota", msg, re.I):
        return False, 0.0

    for code in _RETRYABLE_CODES:
        if str(code) in msg:
            m = re.search(r"retryDelay.*?(\d+)s", msg)
            # If retryDelay is 0 or absent, use base delay; cap at 60s
            raw = float(m.group(1)) if m else 0.0
            delay = raw if raw > 0 else _BASE_DELAY
            return True, min(delay, 60.0)
    return False, 0.0


async def generate_stream(
    user_message: str,
    context: str,
    history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream Gemini response tokens with automatic retry on transient errors."""
    client = _get_client()
    contents = _build_contents(user_message, context, history)
    config = _make_config()

    for attempt in range(_MAX_RETRIES + 1):
        try:
            collected = ""
            async for chunk in await client.aio.models.generate_content_stream(
                model=GENERATION_MODEL,
                contents=contents,
                config=config,
            ):
                try:
                    text = chunk.text  # raises ValueError on blocked/empty chunk
                    if text:
                        collected += text
                        yield text
                except (ValueError, AttributeError):
                    # thinking chunk or filtered chunk — skip silently
                    continue

            # If we completed but got nothing, yield an explicit message
            if not collected:
                yield (
                    "## Réponse indisponible\n\n"
                    "Le modèle n'a pas produit de contenu textuel pour cette requête.\n\n"
                    "### Recommandations\n"
                    "- Reformulez la question avec plus de détails\n"
                    "- Vérifiez que la base de connaissances est indexée (`Réindexer la KB`)\n"
                    "- Réessayez dans quelques secondes\n"
                )
            return  # success

        except Exception as exc:
            should_retry, delay = _is_retryable(exc)
            if should_retry and attempt < _MAX_RETRIES:
                wait = delay * (2 ** attempt)
                logger.warning(
                    f"[GEMINI] Attempt {attempt + 1}/{_MAX_RETRIES} failed "
                    f"({type(exc).__name__}), retrying in {wait:.1f}s"
                )
                yield f"\n\n*⏳ Modèle surchargé — nouvelle tentative dans {wait:.0f}s...*\n\n"
                await asyncio.sleep(wait)
            else:
                raise


async def generate(
    user_message: str,
    context: str,
    history: list[dict] | None = None,
) -> str:
    """Non-streaming generation with retry."""
    client = _get_client()
    contents = _build_contents(user_message, context, history)
    config = _make_config()

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.aio.models.generate_content(
                model=GENERATION_MODEL,
                contents=contents,
                config=config,
            )
            try:
                text = resp.text
            except (ValueError, AttributeError):
                text = ""

            if not text:
                # try extracting from candidates manually
                try:
                    parts = resp.candidates[0].content.parts
                    text = "".join(
                        p.text for p in parts if hasattr(p, "text") and p.text
                    )
                except Exception:
                    pass

            return text or (
                "## Réponse indisponible\n\n"
                "Le modèle n'a pas produit de contenu pour cette requête.\n\n"
                "### Recommandations\n"
                "- Reformulez la question\n"
                "- Réessayez dans quelques instants\n"
            )

        except Exception as exc:
            should_retry, delay = _is_retryable(exc)
            if should_retry and attempt < _MAX_RETRIES:
                wait = delay * (2 ** attempt)
                logger.warning(
                    f"[GEMINI] Sync attempt {attempt + 1}/{_MAX_RETRIES} failed, "
                    f"retrying in {wait:.1f}s"
                )
                await asyncio.sleep(wait)
            else:
                raise
