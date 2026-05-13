import logging
import os
import threading

from neo4j import AsyncGraphDatabase

from backend.core.circuit_breaker import CircuitBreakerOpenError, neo4j_breaker
from backend.features.fraud_detection.fraud_detection import FraudDetector

logger = logging.getLogger(__name__)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASS", "")

class Neo4jClient:

    def __init__(self) -> None:
        self._driver = None
        self._fraud_detector = FraudDetector()

    async def connect(self) -> None:
        if self._driver is not None:
            return
        try:
            self._driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
            await self._driver.verify_connectivity()
            self._fraud_detector._driver = self._driver
            logger.info("[GRAPH] Connexion Neo4j établie.")
        except Exception as e:
            logger.error(f"Impossible de se connecter à Neo4j Graph DB: {e}")
            self._driver = None

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def _run_query(self, cypher: str, **params) -> None:
        async with self._driver.session() as session:
            await session.run(cypher, **params)

    async def ingest_transaction(self, tx_id: str, asset_id: str, from_actor: str, to_actor: str, amount: float, timestamp: str) -> None:
        if not self._driver:
            return

        cypher_query = """
        MERGE (a1:Actor {dn: $from_actor})
        MERGE (a2:Actor {dn: $to_actor})
        CREATE (a1)-[r:TRANSFER {
            tx_id: $tx_id,
            asset_id: $asset_id,
            amount: $amount,
            timestamp: $timestamp
        }]->(a2)
        RETURN r
        """

        try:
            await neo4j_breaker.call(
                self._run_query,
                cypher_query,
                from_actor=from_actor,
                to_actor=to_actor,
                tx_id=tx_id,
                asset_id=asset_id,
                amount=amount,
                timestamp=timestamp,
            )
            logger.info(f"[GRAPH] Transaction {tx_id[:8]} synchronisée avec Neo4j.")
        except CircuitBreakerOpenError:
            logger.warning("[GRAPH] Neo4j circuit open — ingest skipped (will resync later).")
        except Exception as e:
            logger.error(f"[GRAPH] Echec de synchronisation Neo4j: {e}")

    async def ingest_freeze(self, asset_id: str, actor: str, tx_id: str) -> None:
        if not self._driver:
            return

        cypher_query = """
        MERGE (a:Actor {dn: $actor})
        CREATE (a)-[r:FROZEN {
            asset_id: $asset_id,
            tx_id: $tx_id,
            reason: 'AMF_REGULATORY_FREEZE'
        }]->(a)
        """
        try:
            await neo4j_breaker.call(
                self._run_query, cypher_query, actor=actor, asset_id=asset_id, tx_id=tx_id,
            )
        except CircuitBreakerOpenError:
            logger.warning("[GRAPH] Neo4j circuit open — freeze ingest skipped.")
        except Exception as e:
            logger.error(f"[GRAPH] Echec ingest_freeze Neo4j: {e}")

    async def run_fraud_scan(self) -> dict[str, list[dict]]:
        """Run full fraud detection scan and return all anomalies found."""
        if not self._driver:
            logger.warning("[GRAPH] Fraud scan skipped: no Neo4j connection.")
            return {
                "circular_flow": [],
                "smurfing": [],
                "layering": [],
                "transfer_concentration": [],
            }
        return await self._fraud_detector.run_full_scan()

_neo4j_singleton: Neo4jClient | None = None
_neo4j_singleton_lock = threading.Lock()


def get_neo4j_client() -> Neo4jClient:
    """Return the process-wide Neo4j client singleton.

    The first call creates the instance (not yet connected).
    Call ``await client.connect()`` before use — idempotent if already connected.
    """
    global _neo4j_singleton
    if _neo4j_singleton is None:
        with _neo4j_singleton_lock:
            if _neo4j_singleton is None:
                _neo4j_singleton = Neo4jClient()
    return _neo4j_singleton
