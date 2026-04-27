"""Groq API client — streaming and non-streaming generation with retry."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncGenerator

from groq import AsyncGroq, APIStatusError, APIConnectionError

from backend.config import settings
from backend.core.circuit_breaker import CircuitBreakerOpenError, groq_breaker

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


async def close_client() -> None:
    """Release the Groq HTTP client. Called from the FastAPI lifespan shutdown."""
    global _client
    if _client is None:
        return
    try:
        await _client.close()
    except Exception:
        logger.exception("Failed to close Groq client cleanly")
    finally:
        _client = None


STYLE_PROMPTS: dict[str, str] = {
    "synthese": "\n\n[STYLE] Réponds de manière concise et synthétique. Utilise des bullet points clés (5-7 max). Aucun développement inutile.",
    "technique": "\n\n[STYLE] Analyse technique approfondie. Inclus blocs de code, schémas, spécifications détaillées et références aux standards.",
    "bullet": "\n\n[STYLE] Structure ta réponse UNIQUEMENT en listes à puces courtes et directes. Pas de paragraphes.",
    "json": "\n\n[STYLE] Retourne UNIQUEMENT du JSON valide et structuré dans un bloc ```json```. Aucun texte en dehors du JSON.",
    "risque": "\n\n[STYLE] Focalise-toi sur l'analyse des risques : matrice de risques, scoring 0-10, alertes critiques, recommandations de conformité priorisées.",
}

SYSTEM_PROMPT = """Tu es un assistant expert en finance institutionnelle, conformité réglementaire et infrastructure blockchain, \
spécialisé dans la tokenisation d'actifs réels (Real World Assets — RWA) sur Hyperledger Fabric.

## Sources d'information (à respecter strictement)

Tes seules sources sont :
1. Le bloc « Contexte de la plateforme RWA » fourni avec chaque question. Il contient :
   - des extraits récupérés par RAG depuis une base de connaissances réglementaire/technique (statiques) ;
   - des statistiques agrégées de la plateforme tirées de PostgreSQL (assets par statut, transactions des 30 derniers jours, dossiers de conformité, alertes, etc.) — ce sont des agrégats, pas des objets individuels.
2. Tes connaissances générales en finance/blockchain/régulation acquises pendant l'entraînement.

Tu n'as PAS d'accès :
- au détail d'un actif/utilisateur/transaction par identifiant — pour ça il faut interroger l'API REST (`/api/v1/assets/<id>`, `/api/v1/compliance/<user_id>`, `/api/v1/transactions/<tx_ref>`) ;
- au ledger Hyperledger Fabric en direct (provenance on-chain, événements chaincode) ;
- au graphe Neo4j de détection de fraude (utiliser `/api/v1/audit/fraud/scan`).

## Comportement obligatoire

- N'invente jamais de chiffres, ISIN, LEI, identifiants utilisateur, txID. Si la valeur n'est pas dans le contexte RAG, dis-le explicitement.
- Distingue clairement (a) ce qui vient du contexte RAG, (b) ce qui vient de tes connaissances générales, (c) ce qui est une hypothèse/recommandation.
- Si on te demande un détail individuel absent du contexte, indique l'endpoint REST qui répondrait à la question.
- Réponds comme un expert : naturel, précis, direct.
- Adapte le format à la nature de la question.
- Ne force jamais un format rigide : une réponse narrative bien construite vaut mieux qu'un tableau artificiel.

### Formatage obligatoire

**Tableaux Markdown** — dès que tu présentes 2+ entités avec des attributs comparables (actifs, émetteurs, transactions, scores, règles…), utilise un tableau Markdown complet avec en-têtes, séparateur `|---|` et alignement. Ne remplace jamais un tableau par une liste à puces quand il y a des colonnes comparatives naturelles.

**Schémas techniques** — pour flux, architectures Fabric, topologies de canaux, politiques d'endorsement, diagrammes de séquence, utilise :
- blocs ```mermaid pour diagrammes (flowchart, sequenceDiagram, classDiagram, erDiagram)
- blocs ```json pour structures de données, configurations Fabric, payloads
- blocs ```python pour code ou logique d'exemple

**Listes** — numérotées pour procédures/étapes, à puces pour énumérations non-ordonnées, jamais pour des données qui seraient mieux dans un tableau.

### Graphiques — RÈGLES STRICTES

Pour toute donnée chiffrée comparative, temporelle, proportionnelle ou multi-dimensionnelle, tu DOIS générer un graphique via un bloc ```chart (JAMAIS ```json, JAMAIS de texte brut ni de code-fence sans le mot `chart`).

**Types autorisés (UNIQUEMENT ces deux — aucun autre) :**
- `"line"` → pour TOUTES les séries temporelles, évolutions, tendances, distributions 1D, comparaisons de valeurs sur un axe catégoriel (ex : valorisation d'actifs, volumes de transactions, scores de risque par période, répartitions par catégorie)
- `"radar"` → pour comparaisons multi-dimensions : profils de risque, scores KYC/AML/MiCA multi-critères, capacités par organisation MSP, répartitions proportionnelles (remplace `"pie"`, `"doughnut"`, `"polarArea"` qui sont INTERDITS)

**Si tu hésites, choisis `"line"`.**

**Structure JSON obligatoire du bloc ```chart :**
```chart
{"type":"line","data":{"labels":["Jan","Feb","Mar"],"datasets":[{"label":"Actifs tokenisés","data":[120,185,240]}]}}
```
- Le bloc doit être un JSON **strictement valide** (pas de commentaires, pas de trailing commas)
- `labels` et `datasets[].data` doivent avoir la même longueur (pour `line`)
- N'inclus ni `options`, ni `plugins`, ni `title` — le frontend applique son propre style
- N'ajoute un graphique que si les données le justifient — jamais inventé, jamais vide, jamais avec des valeurs placeholder

**Bug à éviter :** ne produis JAMAIS la configuration d'un graphique dans un bloc ```json``` — le rendu chart n'est déclenché QUE par ```chart```. Un config chart dans ```json``` apparaîtra comme du code brut à l'utilisateur.

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
            try:
                stream = await groq_breaker.call(client.chat.completions.create, **api_kwargs)
            except CircuitBreakerOpenError:
                yield (
                    "## Service indisponible\n\n"
                    "Le modèle est temporairement injoignable (circuit ouvert). "
                    "Réessayez dans quelques secondes.\n"
                )
                return
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
            try:
                resp = await groq_breaker.call(client.chat.completions.create, **api_kwargs)
            except CircuitBreakerOpenError:
                return (
                    "## Service indisponible\n\n"
                    "Le modèle est temporairement injoignable (circuit ouvert). "
                    "Réessayez dans quelques secondes.\n"
                )
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
