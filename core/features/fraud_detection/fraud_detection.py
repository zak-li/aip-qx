import logging
import os

from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASS", "")

MAX_CYCLE_DEPTH = 6

class FraudDetector:

    def __init__(self) -> None:
        self._driver = None

    async def connect(self) -> None:
        if self._driver is not None:
            return
        try:
            self._driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
            await self._driver.verify_connectivity()
        except Exception as e:
            logger.error(f"[FRAUD_ENGINE] Connexion Neo4j échouée: {e}")
            self._driver = None

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def detect_circular_flow(self, depth: int = 4) -> list[dict[str, str | int | float]]:
        if not self._driver:
            return []

        safe_depth = min(max(depth, 2), MAX_CYCLE_DEPTH)

        query = """
        MATCH path = (a:Actor)-[r:TRANSFER*2..$depth]->(a)
        WITH a, path, [rel in relationships(path) | rel.amount] as amounts
        RETURN a.dn AS SuspiciousActor,
               length(path) AS CycleLength,
               reduce(s = 0, x in amounts | s + x) AS TotalVolume
        ORDER BY TotalVolume DESC
        LIMIT 10
        """

        results: list[dict[str, str | int | float]] = []
        async with self._driver.session() as session:
            try:
                records = await session.run(query, depth=safe_depth)
                async for record in records:
                    results.append({
                        "actor_dn": record["SuspiciousActor"],
                        "cycle_length": record["CycleLength"],
                        "total_volume": record["TotalVolume"],
                        "pattern": "CIRCULAR_FLOW",
                    })
            except Exception as e:
                logger.error(f"[FRAUD_ENGINE] Erreur Cypher Circular Flow: {e}")

        return results

    async def detect_smurfing(self) -> list[dict[str, str | int | float]]:
        if not self._driver:
            return []

        query = """
        MATCH (sender:Actor)-[r:TRANSFER]->(receiver:Actor)
        WITH sender, count(r) as num_transfers, avg(r.amount) as avg_amount
        WHERE num_transfers > 5 AND avg_amount < 50000
        RETURN sender.dn AS SmurfCore, num_transfers, avg_amount
        """

        results: list[dict[str, str | int | float]] = []
        async with self._driver.session() as session:
            try:
                records = await session.run(query)
                async for record in records:
                    results.append({
                        "actor_dn": record["SmurfCore"],
                        "transfer_count": record["num_transfers"],
                        "average_amount": record["avg_amount"],
                        "pattern": "SMURFING",
                    })
            except Exception as e:
                logger.error(f"[FRAUD_ENGINE] Erreur Cypher Smurfing: {e}")

        return results

    async def detect_layering(self, min_hops: int = 3) -> list[dict[str, str | int | float]]:
        """Detect layering: funds passing through min_hops+ intermediaries."""
        if not self._driver:
            return []

        safe_min_hops = max(2, min(min_hops, 6))
        query = f"""
        MATCH path = (source:Actor)-[r:TRANSFER*{safe_min_hops}..6]->(sink:Actor)
        WHERE source <> sink
        WITH source, sink, path,
             [rel in relationships(path) | rel.amount] as amounts,
             [rel in relationships(path) | rel.timestamp] as timestamps
        WHERE size(amounts) >= {safe_min_hops}
        WITH source, sink, path, amounts, timestamps,
             reduce(diff = 0, i in range(0, size(amounts)-2) |
                 diff + (amounts[i] - amounts[i+1])) AS amountDrift
        WHERE amountDrift > 0
        RETURN source.dn AS OriginalSender,
               sink.dn AS FinalRecipient,
               length(path) AS LayerCount,
               amounts[0] AS InitialAmount,
               amounts[-1] AS FinalAmount,
               (amounts[0] - amounts[-1]) AS TotalDrift
        ORDER BY TotalDrift DESC
        LIMIT 10
        """

        results: list[dict[str, str | int | float]] = []
        async with self._driver.session() as session:
            try:
                records = await session.run(query, min_hops=min_hops)
                async for record in records:
                    results.append({
                        "original_sender": record["OriginalSender"],
                        "final_recipient": record["FinalRecipient"],
                        "layer_count": record["LayerCount"],
                        "initial_amount": record["InitialAmount"],
                        "final_amount": record["FinalAmount"],
                        "total_drift": record["TotalDrift"],
                        "pattern": "LAYERING",
                    })
            except Exception as e:
                logger.error(f"[FRAUD_ENGINE] Erreur Cypher Layering: {e}")

        return results

    async def detect_transfer_concentration(self, top_n: int = 10) -> list[dict[str, str | int | float]]:
        """
        Detect transfer concentration: actors receiving disproportionately large
        volumes from many distinct senders — typical of fund aggregation schemes.
        """
        if not self._driver:
            return []

        query = """
        MATCH (sender:Actor)-[r:TRANSFER]->(receiver:Actor)
        WITH receiver,
             count(DISTINCT sender) AS unique_senders,
             count(r) AS total_transfers,
             sum(r.amount) AS total_received
        WHERE unique_senders >= 3
        RETURN receiver.dn AS Aggregator,
               unique_senders,
               total_transfers,
               total_received,
               total_received / unique_senders AS avg_per_sender
        ORDER BY total_received DESC
        LIMIT $top_n
        """

        results: list[dict[str, str | int | float]] = []
        async with self._driver.session() as session:
            try:
                records = await session.run(query, top_n=top_n)
                async for record in records:
                    results.append({
                        "actor_dn": record["Aggregator"],
                        "unique_senders": record["unique_senders"],
                        "total_transfers": record["total_transfers"],
                        "total_received": record["total_received"],
                        "avg_per_sender": record["avg_per_sender"],
                        "pattern": "TRANSFER_CONCENTRATION",
                    })
            except Exception as e:
                logger.error(f"[FRAUD_ENGINE] Erreur Cypher Concentration: {e}")

        return results

    async def run_full_scan(self) -> dict[str, list[dict]]:
        """Run all fraud detection patterns and return combined results."""
        circular = await self.detect_circular_flow()
        smurfing = await self.detect_smurfing()
        layering = await self.detect_layering()
        concentration = await self.detect_transfer_concentration()

        total = len(circular) + len(smurfing) + len(layering) + len(concentration)
        if total > 0:
            logger.warning(f"[FRAUD_ENGINE] Scan terminé: {total} anomalie(s) détectée(s)")

        return {
            "circular_flow": circular,
            "smurfing": smurfing,
            "layering": layering,
            "transfer_concentration": concentration,
        }
