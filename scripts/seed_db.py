"""
Seed script: applies Moroccan SQL migration and loads KYC/AML fixture data.
Usage: python scripts/seed_db.py
"""
import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
DATABASE_URL = os.environ["DATABASE_URL"]  # Set via .env or environment — no hardcoded fallback
# asyncpg uses plain postgres:// scheme
PG_DSN = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace(
    "postgresql://", "postgresql://"
)

SQL_FILE = ROOT / "db" / "sql" / "06_seed_morocco.sql"
FIXTURE_FILE = ROOT / "db" / "fixtures" / "json" / "compliance_kyc_aml.json"

# ── Risk category normalisation ───────────────────────────────────────────────
RISK_MAP = {
    "TRES_FAIBLE": "TRES_FAIBLE",
    "FAIBLE": "FAIBLE",
    "MOYEN": "MOYEN",
    "ELEVE": "ELEVE",
    "CRITIQUE": "CRITIQUE",
}


async def apply_sql(conn: asyncpg.Connection) -> None:
    sql = SQL_FILE.read_text(encoding="utf-8")
    # asyncpg cannot handle multiple statements in one execute(); split on ";"
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        await conn.execute(stmt)
    print(f"[SQL]  Applied {len(statements)} statement(s) from {SQL_FILE.name}")


async def seed_compliance(conn: asyncpg.Connection, data: dict) -> None:
    inserted = 0
    skipped = 0

    for screening in data.get("aml_screenings", []):
        participant_id = screening["participant_ref"]
        score = Decimal(str(screening["final_risk_score"]))
        risk_category = RISK_MAP.get(screening["risk_category"], "FAIBLE")
        sanctions_hit = any(
            lst.get("hit", False) for lst in screening.get("lists_checked", [])
        )
        pep_status = screening.get("risk_indicators", {}).get(
            "politically_exposed_person", False
        )
        next_review = screening.get("next_review_date")
        expires_at = (
            datetime.fromisoformat(next_review).replace(tzinfo=UTC)
            if next_review
            else None
        )

        # Derive KYC info from the matching submission
        kyc_submission = next(
            (
                s
                for s in data.get("kyc_submissions", [])
                if s["participant_ref"] == participant_id
            ),
            None,
        )
        kyc_level = kyc_submission["kyc_level"] if kyc_submission else 2
        kyc_status = "APPROUVE" if kyc_submission else "VERIFIE"

        # Skip if user doesn't exist in DB
        user_exists = await conn.fetchval(
            "SELECT id FROM users WHERE id = $1::uuid", participant_id
        )
        if not user_exists:
            print(f"  [WARN]  user {participant_id} not in DB — skipping")
            skipped += 1
            continue

        # Check existing
        existing = await conn.fetchval(
            "SELECT id FROM compliance_records WHERE participant_id = $1::uuid",
            participant_id,
        )
        if existing:
            skipped += 1
            continue

        await conn.execute(
            """
            INSERT INTO compliance_records
              (participant_id, kyc_status, kyc_level, aml_score, risk_category,
               sanctions_hit, pep_status, expires_at, check_date)
            VALUES
              ($1::uuid, $2, $3, $4, $5, $6, $7, $8, now())
            """,
            participant_id,
            kyc_status,
            kyc_level,
            score,
            risk_category,
            sanctions_hit,
            pep_status,
            expires_at,
        )
        inserted += 1

    print(
        f"[KYC/AML]  compliance_records — inserted: {inserted}, skipped (already exist): {skipped}"
    )


async def seed_kyc_documents(conn: asyncpg.Connection, data: dict) -> None:
    inserted = 0
    skipped = 0

    for submission in data.get("kyc_submissions", []):
        participant_id = submission["participant_ref"]
        user_exists = await conn.fetchval(
            "SELECT id FROM users WHERE id = $1::uuid", participant_id
        )
        if not user_exists:
            print(f"  [WARN]  user {participant_id} not in DB — skipping docs")
            continue
        for doc in submission.get("documents", []):
            doc_type = doc.get("type", "UNKNOWN")
            doc_number = doc.get("number")
            issuing_country = submission.get("identity", {}).get("nationality")
            issue_date_raw = doc.get("issue_date")
            expiry_date_raw = doc.get("expiry_date")
            issue_date = (
                datetime.fromisoformat(issue_date_raw).date() if issue_date_raw else None
            )
            expiry_date = (
                datetime.fromisoformat(expiry_date_raw).date() if expiry_date_raw else None
            )
            verified = doc.get("verified", False)
            file_hash = f"fixture-{participant_id}-{doc_type}".replace(" ", "-").lower()

            existing = await conn.fetchval(
                "SELECT id FROM kyc_documents WHERE user_id = $1::uuid AND document_type = $2",
                participant_id,
                doc_type,
            )
            if existing:
                skipped += 1
                continue

            await conn.execute(
                """
                INSERT INTO kyc_documents
                  (user_id, document_type, file_hash, document_number,
                   issuing_country, issued_date, expiry_date, verified)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
                """,
                participant_id,
                doc_type,
                file_hash,
                doc_number,
                issuing_country,
                issue_date,
                expiry_date,
                verified,
            )
            inserted += 1

    print(
        f"[KYC/AML]  kyc_documents — inserted: {inserted}, skipped (already exist): {skipped}"
    )


async def verify(conn: asyncpg.Connection) -> None:
    orgs = await conn.fetchval(
        "SELECT COUNT(*) FROM organizations WHERE country_code = 'MA'"
    )
    users = await conn.fetchval(
        "SELECT COUNT(*) FROM users WHERE org_id IN "
        "(SELECT id FROM organizations WHERE country_code = 'MA')"
    )
    records = await conn.fetchval("SELECT COUNT(*) FROM compliance_records")
    docs = await conn.fetchval("SELECT COUNT(*) FROM kyc_documents")
    print(f"\n[VERIFY]  MA orgs: {orgs} | MA users: {users} | compliance_records: {records} | kyc_documents: {docs}")


async def main() -> None:
    # Strip asyncpg prefix from URL
    dsn = PG_DSN
    print(f"Connecting to {dsn.split('@')[1]}...")

    conn = await asyncpg.connect(dsn)
    try:
        await apply_sql(conn)

        fixture = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
        await seed_compliance(conn, fixture)
        await seed_kyc_documents(conn, fixture)
        await verify(conn)
        print("\n[DONE]  Seed completed successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
