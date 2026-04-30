import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable

import grpc
import redis.asyncio as redis

from backend.config import FabricSettings

logger = logging.getLogger(__name__)

PayloadDict = dict[str, str | int | float | bool | dict[str, str | int | float | bool] | list[str | int | float | bool] | None]

VALID_CHAINCODE_ACTIONS = {"AssetCreated", "AssetTransferred", "AssetFrozen", "AssetUnfrozen"}
ASSET_ID_PATTERN = re.compile(r"^RWA-[A-Z]{2,12}-[A-Z]{2,6}-\d{4}-\d{3}$")

class FabricEventListener:
    def __init__(self, settings: FabricSettings) -> None:
        self.settings = settings
        self.channel_name = self.settings.fabric_channel
        self.chaincode_id = self.settings.fabric_chaincode

        self._target_events = set(self.settings.fabric_events_targets.split(","))
        self._required_fields = self.settings.fabric_events_required_payload_fields.split(",")

        self._redis: redis.Redis | None = None
        self._callbacks: list[Callable[[PayloadDict], Awaitable[None]]] = []
        self._listener_task: asyncio.Task[None] | None = None
        self._running = False

        self._rate_limit = self.settings.fabric_events_rate_limit
        self._tokens = self._rate_limit
        self._last_token_update = time.monotonic()
        self._redis_channel = self.settings.fabric_events_redis_channel

    def _acquire_rate_limit_token(self) -> bool:
        now = time.monotonic()
        elapsed = now - self._last_token_update

        self._tokens += elapsed * self._rate_limit
        if self._tokens > self._rate_limit:
            self._tokens = self._rate_limit

        self._last_token_update = now

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    def _validate_payload(self, payload: PayloadDict) -> bool:
        for required_field in self._required_fields:
            val = payload.get(required_field)
            if val is None or val == "":
                return False

        action = payload.get("action", "")
        if action not in VALID_CHAINCODE_ACTIONS:
            logger.warning(f"Action chaincode non reconnue: {action}")
            return False

        tx_id = payload.get("txID", "")
        if not tx_id or not isinstance(tx_id, str):
            logger.warning("txID manquant ou vide dans le payload chaincode")
            return False

        asset_id = str(payload.get("assetID", ""))
        if asset_id and not ASSET_ID_PATTERN.match(asset_id):
            logger.warning(f"assetID non conforme au pattern RWA: {asset_id}")
            return False

        return True

    def on_event(self, callback: Callable[[PayloadDict], Awaitable[None]]) -> None:
        self._callbacks.append(callback)

    async def start(self) -> None:
        self._running = True
        self._redis = redis.from_url(self.settings.redis_url)
        self._listener_task = asyncio.create_task(self._listening_daemon())
        logger.info("Fabric event listener démarré")

    async def stop(self) -> None:
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def _handle_incoming_event(self, event_name: str, payload_bytes: bytes) -> None:
        if event_name not in self._target_events:
            return

        try:
            payload_str = payload_bytes.decode("utf-8")
            payload_data = json.loads(payload_str) if payload_str else {}
            if not isinstance(payload_data, dict):
                payload_data = {}

            if not self._validate_payload(payload_data):
                logger.warning(
                    json.dumps({
                        "warning": "Payload chaincode rejeté par validation",
                        "event_name": event_name,
                    })
                )
                return

            if not self._acquire_rate_limit_token():
                logger.warning(
                    json.dumps({
                        "warning": "Rate limit dépassé, événement abandonné",
                    })
                )
                return

            structured_event: PayloadDict = {
                "event": event_name,
                "chaincode": self.chaincode_id,
                "channel": self.channel_name,
                "payload": payload_data,
            }

            if self._redis:
                await self._redis.publish(
                    self._redis_channel,
                    json.dumps(structured_event),
                )

            for cb in self._callbacks:
                await cb(structured_event)

        except Exception as exc:
            logger.error(
                json.dumps({
                    "error": "Erreur traitement événement chaincode",
                    "details": str(exc),
                    "event_name": event_name,
                })
            )

    async def _listening_daemon(self) -> None:
        """Subscribe to the Redis pub/sub channel populated by asset_service on every
        Fabric operation.  Messages follow the format  ``ACTION:asset_id``.

        The architecture uses Redis as the event bus because the Fabric peer
        delivers chaincode events via gRPC (deliver service), which requires the
        Fabric Go/Java SDK.  Our CLI-based client publishes synthetic events to
        the same Redis channel so the listener remains decoupled from the
        transport mechanism and can be swapped for a real gRPC stream in future.
        """
        while self._running:
            pubsub = None
            try:
                if not self._redis:
                    await asyncio.sleep(self.settings.fabric_events_grpc_reconnect_delay)
                    continue

                pubsub = self._redis.pubsub()
                await pubsub.subscribe("asset:events")
                logger.info("[EVENT] Subscribed to Redis channel 'asset:events'")

                async for raw_message in pubsub.listen():
                    if not self._running:
                        break

                    if raw_message.get("type") != "message":
                        continue

                    data = raw_message.get("data", b"")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    # Format published by asset_service: "TOKENIZE:asset_id"
                    parts = data.split(":", 1)
                    if len(parts) != 2:
                        continue

                    action_raw, asset_id = parts[0].strip(), parts[1].strip()

                    action_map = {
                        "TOKENIZE": "AssetCreated",
                        "TRANSFER": "AssetTransferred",
                        "FREEZE": "AssetFrozen",
                        "UNFREEZE": "AssetUnfrozen",
                    }
                    chaincode_action = action_map.get(action_raw)
                    if not chaincode_action:
                        continue

                    payload: PayloadDict = {
                        "action": chaincode_action,
                        "assetID": asset_id,
                        "txID": f"redis-event-{action_raw}-{asset_id}",
                        "channel": self.channel_name,
                        "chaincode": self.chaincode_id,
                    }

                    if not self._acquire_rate_limit_token():
                        logger.warning("[EVENT] Rate limit atteint, événement ignoré.")
                        continue

                    structured: PayloadDict = {
                        "event": chaincode_action,
                        "chaincode": self.chaincode_id,
                        "channel": self.channel_name,
                        "payload": payload,
                    }

                    for cb in self._callbacks:
                        try:
                            await cb(structured)
                        except Exception as cb_exc:
                            logger.error(f"[EVENT] Callback error: {cb_exc}")

            except grpc.RpcError as exc:
                logger.warning(json.dumps({"warning": "gRPC error in event listener", "details": str(exc)}))
                await asyncio.sleep(self.settings.fabric_events_grpc_reconnect_delay)
            except Exception as exc:
                logger.error(json.dumps({"error": "Event listener crashed", "details": str(exc)}))
                await asyncio.sleep(self.settings.fabric_events_grpc_reconnect_delay)
            finally:
                if pubsub:
                    try:
                        await pubsub.unsubscribe("asset:events")
                        await pubsub.aclose()
                    except Exception:  # noqa: S110
                        pass
