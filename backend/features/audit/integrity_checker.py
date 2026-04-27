import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, UTC

from .trail import ProvenanceRecord

@dataclass
class RecordIntegrity:
    record_index: int
    tx_id: str
    computed_hash: str
    valid: bool
    tampered_fields: list[str]

@dataclass
class IntegrityReport:
    asset_id: str
    total_records: int
    valid: bool
    tampered_count: int
    records: list[RecordIntegrity]
    checked_at: datetime

class IntegrityChecker:
    def check(self, asset_id: str, provenance: list[ProvenanceRecord]) -> IntegrityReport:
        records: list[RecordIntegrity] = []
        global_valid = True
        tampered_count = 0

        seen_tokenise = False
        allowed_actions = {"TOKENISE", "TRANSFERE", "GELE", "DEGELE"}

        for idx, rec in enumerate(provenance):
            tampered_fields: list[str] = []

            if idx == 0 and rec.action != "TOKENISE":
                tampered_fields.append("action (TOKENISE missing)")
            if rec.action == "TOKENISE":
                seen_tokenise = True

            if rec.action == "GELE" and not seen_tokenise:
                tampered_fields.append("action (GELE before TOKENISE)")

            if rec.action not in allowed_actions:
                tampered_fields.append(f"action ({rec.action} unknown)")

            rec_dict = {
                "action": rec.action,
                "actor_dn": rec.actor_dn,
                "actor_msp": rec.actor_msp,
                "amount": rec.amount,
                "block_number": rec.block_number,
                "from_owner": rec.from_owner,
                "justification": rec.justification,
                "timestamp": rec.timestamp.isoformat(),
                "to_owner": rec.to_owner,
                "tx_id": rec.tx_id
            }

            serial = json.dumps(rec_dict, sort_keys=True, ensure_ascii=True).encode("utf-8")
            hsh = hashlib.sha256(serial).hexdigest()

            is_valid = len(tampered_fields) == 0
            if not is_valid:
                global_valid = False
                tampered_count += 1

            records.append(RecordIntegrity(
                record_index=idx,
                tx_id=rec.tx_id,
                computed_hash=hsh,
                valid=is_valid,
                tampered_fields=tampered_fields
            ))

        return IntegrityReport(
            asset_id=asset_id,
            total_records=len(provenance),
            valid=global_valid,
            tampered_count=tampered_count,
            records=records,
            checked_at=datetime.now(UTC)
        )
