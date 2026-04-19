from dataclasses import dataclass
from datetime import datetime
from dateutil.parser import isoparse
from backend.fabric_client.network import FabricClient

@dataclass
class ProvenanceRecord:
    tx_id: str
    timestamp: datetime
    actor_msp: str
    actor_dn: str
    action: str
    from_owner: str
    to_owner: str
    amount: float
    justification: str
    block_number: int

@dataclass
class HistoryEntry:
    tx_id: str
    is_delete: bool
    value: dict
    timestamp: datetime | None

class AuditTrail:
    def __init__(self, fabric_client: FabricClient, identity_label: str = "Admin@bnpparibas") -> None:
        self.fabric_client = fabric_client
        self.identity_label = identity_label

    async def get_provenance(self, asset_id: str) -> list[ProvenanceRecord]:
        raw_data = await self.fabric_client.evaluate_transaction(
            "GetProvenanceTrail", asset_id, identity_label=self.identity_label
        )
        if not isinstance(raw_data, list):
            raise ValueError("Invalid format received from Fabric chaincode.")
            
        records: list[ProvenanceRecord] = []
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            
            tx_id = item.get("tx_id", "")
            actor_msp = item.get("actor_msp", "")
            action = item.get("action", "")
            
            if not tx_id or not actor_msp or not action:
                raise ValueError("Incomplete provenance record detected (missing tx_id, actor_msp or action).")
                
            ts_str = item.get("timestamp")
            dt = isoparse(ts_str) if ts_str else datetime.min
            
            records.append(ProvenanceRecord(
                tx_id=tx_id,
                timestamp=dt,
                actor_msp=actor_msp,
                actor_dn=item.get("actor_dn", ""),
                action=action,
                from_owner=item.get("from_owner", ""),
                to_owner=item.get("to_owner", ""),
                amount=float(item.get("amount", 0.0)),
                justification=item.get("justification", ""),
                block_number=int(item.get("block_number", 0))
            ))
        return records

    async def get_full_history(self, asset_id: str) -> list[HistoryEntry]:
        raw_data = await self.fabric_client.evaluate_transaction(
            "GetAssetHistory", asset_id, identity_label=self.identity_label
        )
        if not isinstance(raw_data, list):
            raise ValueError("Invalid format received from Fabric chaincode.")
            
        entries: list[HistoryEntry] = []
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            ts_str = item.get("timestamp")
            dt = isoparse(ts_str) if ts_str else None
            entries.append(HistoryEntry(
                tx_id=item.get("tx_id", ""),
                is_delete=bool(item.get("is_delete", False)),
                value=item.get("value", {}) if isinstance(item.get("value"), dict) else {},
                timestamp=dt
            ))
        return entries

    async def get_asset_state(self, asset_id: str) -> dict:
        raw_data = await self.fabric_client.evaluate_transaction(
            "GetAsset", asset_id, identity_label=self.identity_label
        )
        if not isinstance(raw_data, dict):
            raise ValueError("Invalid format received from Fabric chaincode.")
        return raw_data
