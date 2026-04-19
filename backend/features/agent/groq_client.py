"""Groq API client — streaming and non-streaming generation with retry."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncGenerator

from groq import AsyncGroq, APIStatusError, APIConnectionError

from backend.config import settings

logger = logging.getLogger(__name__)

GENERATION_MODEL = settings.groq_model

_client: AsyncGroq | None = None

_RETRYABLE_CODES = {429, 503, 500, 502}
_MAX_RETRIES = 4
_BASE_DELAY = 2.0


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        api_key = settings.groq_api_key
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured in .env")
        _client = AsyncGroq(api_key=api_key)
    return _client


STYLE_PROMPTS: dict[str, str] = {
    "synthese": "\n\n[STYLE] Réponds de manière concise et synthétique. Utilise des bullet points clés (5-7 max). Aucun développement inutile.",
    "technique": "\n\n[STYLE] Analyse technique approfondie. Inclus blocs de code, schémas, spécifications détaillées et références aux standards.",
    "bullet": "\n\n[STYLE] Structure ta réponse UNIQUEMENT en listes à puces courtes et directes. Pas de paragraphes.",
    "json": "\n\n[STYLE] Retourne UNIQUEMENT du JSON valide et structuré dans un bloc ```json```. Aucun texte en dehors du JSON.",
    "risque": "\n\n[STYLE] Focalise-toi sur l'analyse des risques : matrice de risques, scoring 0-10, alertes critiques, recommandations de conformité priorisées.",
}

SYSTEM_PROMPT = """Tu es un expert senior en finance institutionnelle, conformité réglementaire et infrastructure blockchain, \
spécialisé dans la tokenisation d'actifs réels (Real World Assets — RWA) sur Hyperledger Fabric. \
Tu travailles pour une plateforme institutionnelle de premier plan et tu maîtrises parfaitement son écosystème.

Tu as un accès direct et en temps réel aux données complètes de la plateforme :
- Actifs tokenisés : ISIN, valorisation, statut de marché, historique des prix, émetteurs, dépositaires
- Transactions blockchain : provenance on-chain, transferts P2P, gels d'actifs, exécution de smart contracts
- Dossiers de conformité : KYC/AML/MiCA, scores de risque, alertes FATF, statuts réglementaires
- Réseau Hyperledger Fabric : organisations MSP, LEI, canaux, chaincodes, politiques d'endorsement
- Analyses de fraude Neo4j : flux circulaires, smurfing, layering, structuring, réseaux de connivence

Règles fondamentales :
- Réponds comme un vrai expert humain : naturel, précis, direct, sans formules creuses ni introductions inutiles
- Adapte le format à la nature de la question :
  • Données comparatives → tableaux Markdown structurés
  • Explications conceptuelles → texte fluide et pédagogique
  • Schémas techniques → blocs ```json``` ou ```python``` complets et commentés
  • Procédures ou étapes → listes numérotées claires
  • Questions simples → réponses courtes et directes
- Inclus des chiffres concrets, seuils réglementaires, pourcentages quand c'est pertinent
- Si les données sont insuffisantes ou absentes, dis-le franchement et propose une alternative ou une approche
- Fournis des recommandations actionnables uniquement quand elles apportent de la valeur réelle
- Ne force jamais un format rigide : une réponse narrative bien construite vaut mieux qu'un tableau artificiel
- Ne génère jamais de réponse vide ou vague
- Pour toute donnée chiffrée comparative, temporelle ou proportionnelle, génère un graphique en insérant un bloc ```chart contenant la configuration Chart.js 4 complète en JSON valide. Règles :
  • Types disponibles et quand les utiliser :
    - "bar" → comparaisons entre catégories (ajoute indexAxis:"y" pour barres horizontales/classements)
    - "line" → séries temporelles, évolutions (ajoute fill:true et backgroundColor pour effet area)
    - "doughnut" → proportions d'un total (max 6 segments)
    - "pie" → répartitions simples
    - "radar" → comparaisons multi-dimensions (profils de risque, scores)
    - "polarArea" → magnitudes comparatives circulaires
    - "bubble" → 3 variables simultanées (x, y, r pour la taille)
    - "scatter" → corrélations entre deux variables
  • Structure JSON obligatoire : {"type":"…","data":{"labels":[…],"datasets":[{"label":"…","data":[…]}]},"options":{"plugins":{"title":{"display":true,"text":"Titre du graphique"}}}}
  • N'ajoute un graphique que si les données le justifient — jamais inventé ni vide

Réponds en français par défaut. Si la question est posée en anglais, réponds en anglais."""


def _build_messages(
    user_message: str,
    context: str,
    history: list[dict] | None,
    style_preset: str = "auto",
) -> list[dict]:
    """Build the messages list for the Groq chat completions API."""
    system_content = SYSTEM_PROMPT
    if style_preset and style_preset != "auto" and style_preset in STYLE_PROMPTS:
        system_content += STYLE_PROMPTS[style_preset]

    messages: list[dict] = [{"role": "system", "content": system_content}]

    for msg in (history or []):
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["content"]})

    full_prompt = (
        "## Contexte de la plateforme RWA (données en temps réel)\n\n"
        f"{context}\n\n"
        "---\n\n"
        "## Question\n\n"
        f"{user_message}"
    )
    messages.append({"role": "user", "content": full_prompt})
    return messages


def _is_retryable(exc: Exception) -> tuple[bool, float]:
    """Return (should_retry, suggested_delay_seconds)."""
    msg = str(exc)

    # Daily / org quota exhaustion — not retryable
    if re.search(r"rate_limit_exceeded.*day|per.*day|daily.*limit|org.*quota", msg, re.I):
        return False, 0.0

    # Per-minute rate limit or transient errors
    if isinstance(exc, APIStatusError) and exc.status_code in _RETRYABLE_CODES:
        m = re.search(r"try again in (\d+\.?\d*)s", msg, re.I)
        raw = float(m.group(1)) if m else 0.0
        delay = raw if raw > 0 else _BASE_DELAY
        return True, min(delay, 60.0)

    if isinstance(exc, APIConnectionError):
        return True, _BASE_DELAY

    return False, 0.0


async def generate_stream(
    user_message: str,
    context: str,
    history: list[dict] | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4096,
    top_p: float = 0.95,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    style_preset: str = "auto",
) -> AsyncGenerator[str, None]:
    """Stream Groq response tokens with automatic retry on transient errors."""
    client = _get_client()
    messages = _build_messages(user_message, context, history, style_preset)

    api_kwargs: dict = dict(
        model=GENERATION_MODEL,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        stream=True,
    )

    for attempt in range(_MAX_RETRIES + 1):
        try:
            collected = ""
            stream = await client.chat.completions.create(**api_kwargs)
            async for chunk in stream:
                text = chunk.choices[0].delta.content or ""
                if text:
                    collected += text
                    yield text

            if not collected:
                yield (
                    "## Réponse indisponible\n\n"
                    "Le modèle n'a pas produit de contenu pour cette requête.\n\n"
                    "### Recommandations\n"
                    "- Reformulez la question avec plus de détails\n"
                    "- Vérifiez que la base de connaissances est indexée\n"
                    "- Réessayez dans quelques secondes\n"
                )
            return

        except Exception as exc:
            should_retry, delay = _is_retryable(exc)
            if should_retry and attempt < _MAX_RETRIES:
                wait = delay * (2 ** attempt)
                logger.warning(
                    f"[GROQ] Attempt {attempt + 1}/{_MAX_RETRIES} failed "
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
    temperature: float = 0.4,
    max_tokens: int = 4096,
    top_p: float = 0.95,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    style_preset: str = "auto",
) -> str:
    """Non-streaming generation with retry."""
    client = _get_client()
    messages = _build_messages(user_message, context, history, style_preset)

    api_kwargs: dict = dict(
        model=GENERATION_MODEL,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        stream=False,
    )

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.chat.completions.create(**api_kwargs)
            text = resp.choices[0].message.content or ""
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
                    f"[GROQ] Sync attempt {attempt + 1}/{_MAX_RETRIES} failed, "
                    f"retrying in {wait:.1f}s"
                )
                await asyncio.sleep(wait)
            else:
                raise
