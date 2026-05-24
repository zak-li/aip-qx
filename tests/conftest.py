import json
import os

# Derive test DB URLs from the configured DATABASE_URL so the same conftest
# works locally (via .env) and in CI (via workflow env vars).
# CI overrides via TEST_DATABASE_URL / TEST_ADMIN_DB_URL take precedence.
import re as _re
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import asyncpg
import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from core.config import settings
from core.core.celery_app import celery_app
from core.core.database_base import Base
from core.core.redis_client import get_redis
from core.core.security import _TEST_SIGNING_KEY, create_access_token
from core.dependencies import get_db, get_fabric
from core.exceptions import AssetFrozenError, AssetNotFoundException
from core.fabric_client.network import FabricClient
from core.features.audit.integrity_checker import IntegrityChecker, IntegrityReport
from core.features.audit.trail import ProvenanceRecord
from core.features.auth.models import Organization, User
from core.features.compliance.models import ComplianceRecord
from core.main import app

_db_url = str(settings.database_url)
TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or _re.sub(r"/([^/?]+)(\?.*)?$", "/rwadb_test", _db_url)
)
ADMIN_DB_URL = (
    os.environ.get("TEST_ADMIN_DB_URL")
    or TEST_DATABASE_URL.replace("+asyncpg", "").replace("/rwadb_test", "/rwadb")
)

BANK01_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
REG01_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
NATWEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")

THOMAS_USER_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
SOPHIE_USER_ID = uuid.UUID("10000000-0000-0000-0000-000000000002")
JAMES_USER_ID = uuid.UUID("10000000-0000-0000-0000-000000000003")

REAL_TX_1 = "185861c04e4744c0c10f07ac82011b1534fe3a7642507db322172ab39fa2ad43"
REAL_TX_2 = "7a4508a19663ea42115d16ef010048636c3b0670c62a0706731a006a9afe4611"
REAL_TX_3 = "2b43720e638bbae75270a43f7c98992bc51dcd1ef7720ac27ce063edb23b008b"

@pytest.fixture(scope="session")
def monkeypatch_session() -> pytest.MonkeyPatch:
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()

@pytest.fixture(scope="session", autouse=True)
def set_test_environment(monkeypatch_session: pytest.MonkeyPatch) -> None:
    monkeypatch_session.setenv("ENVIRONMENT", "test")
    monkeypatch_session.setenv("FABRIC_TLS_ENABLED", "false")
    celery_app.conf.update(task_always_eager=True)

@pytest.fixture(scope="session")
def async_engine():
    """Synchronous session fixture — uses asyncio.run() so each test function
    gets its own event loop, preventing asyncpg Future loop-mismatch errors
    that occur when BaseHTTPMiddleware creates tasks in a different loop."""
    import asyncio as _asyncio

    async def _setup():
        try:
            sys_conn = await asyncpg.connect(ADMIN_DB_URL)
            try:
                await sys_conn.execute("CREATE DATABASE rwadb_test OWNER rwaadmin;")
            except (asyncpg.exceptions.DuplicateDatabaseError,
                    asyncpg.exceptions.InsufficientPrivilegeError):
                pass
            finally:
                await sys_conn.close()
        except Exception:
            pass

        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

        async with engine.begin() as conn:
            try:
                for v in ["v_asset_portfolio", "v_transaction_history",
                          "v_compliance_dashboard", "v_risk_exposure",
                          "v_valuation_latest"]:
                    await conn.execute(text(f"DROP VIEW IF EXISTS {v} CASCADE"))
                for f in ["get_asset_full_audit", "flag_high_risk_transactions",
                          "refresh_asset_current_value", "get_org_portfolio_summary"]:
                    await conn.execute(text(f"DROP FUNCTION IF EXISTS {f} CASCADE"))
            except Exception as e:
                print(f"Warning dropping views/functions: {e}")

            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

            views_file = Path("database/sql/05_views_functions.sql")
            if views_file.exists():
                sql_script = views_file.read_text(encoding="utf-8")
                raw_conn = await conn.get_raw_connection()
                await raw_conn.driver_connection.execute(sql_script)

        await engine.dispose()

    _asyncio.run(_setup())

    yield create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    # Teardown happens implicitly — NullPool makes no persistent connections

@pytest.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator:
    connection = await async_engine.connect()
    transaction = await connection.begin()
    session_maker = async_sessionmaker(bind=connection, class_=AsyncSession, expire_on_commit=False)
    session = session_maker()
    
    yield session
    
    await session.close()
    await transaction.rollback()
    await connection.close()

@pytest.fixture(scope="function")
async def fake_redis() -> AsyncGenerator:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()

@pytest.fixture(scope="function")
def mock_fabric_client() -> AsyncMock:
    client = AsyncMock(spec=FabricClient)

    async def mock_evaluate(function: str, *args: str, **kwargs) -> dict | list:
        if function == "GetAsset":
            target_id = args[0] if args else "UNKNOWN"
            if target_id == "RWA-INEXISTANT-001":
                raise AssetNotFoundException("RWA-INEXISTANT-001")
            
            return {
                "asset_id": target_id,
                "isin": "FR0014004L86",
                "asset_type": "OBLIGATION",
                "asset_name": "Mocked Asset",
                "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
                "issuer_org_id": str(BANK01_ORG_ID),
                "current_owner_id": str(THOMAS_USER_ID),
                "nominal_value": 50000000,
                "current_value": 50000000,
                "currency": "EUR",
                "status": "ACTIF" if target_id != "RWA-OBL-BANK01-2025-001" else "GELE",
                "issuance_date": "2025-01-15",
                "regulatory_ref": "REG01-INV-2026-001",
                "fabric_tx_id": REAL_TX_1,
            }
        if function == "GetProvenanceTrail" and args and args[0] == "RWA-OBL-BANK01-2025-001":
            return [
                {
                    "txID": REAL_TX_1,
                    "timestamp": "2026-03-19T22:49:06.865611553Z",
                    "actorMSP": "BANK01MSP",
                    "actorDN": "CN=admin@bank01.finance-trust.com,OU=admin",
                    "action": "TOKENISE",
                    "fromOwner": "",
                    "toOwner": "CN=admin@bank01.finance-trust.com,OU=admin",
                    "amount": 50000000,
                    "justification": "Tokenisation OAT emission primaire",
                    "blockNumber": 0,
                },
                {
                    "txID": REAL_TX_2,
                    "timestamp": "2026-03-20T11:43:21.503584666Z",
                    "actorMSP": "BANK01MSP",
                    "actorDN": "CN=admin@bank01.finance-trust.com,OU=admin",
                    "action": "TRANSFERE",
                    "fromOwner": "CN=admin@bank01.finance-trust.com,OU=admin",
                    "toOwner": "CN=pierre.moreau,OU=Cust 01",
                    "amount": 24739375,
                    "justification": "Cession bloc Inv01 portefeuille ESG",
                    "blockNumber": 0,
                },
                {
                    "txID": REAL_TX_3,
                    "timestamp": "2026-03-20T11:43:28.950803855Z",
                    "actorMSP": "REG01MSP",
                    "actorDN": "CN=admin@reg01-regulateur.finance-trust.com,OU=admin",
                    "action": "GELE",
                    "fromOwner": "",
                    "toOwner": "",
                    "amount": 0,
                    "justification": "Investigation MIFID II art.69",
                    "blockNumber": 0,
                },
            ]
        if function == "QueryAssets":
            return []
        return {}

    async def mock_submit(function: str, *args: str, **kwargs) -> dict:
        if function == "TokenizeAsset":
            return {
                "txID": "abc123def456",
                "blockNumber": 1,
                "status": "ACTIF",
            }
        if function == "FreezeAsset":
            return {
                "txID": "MOCK_FREEZE_TX",
                "blockNumber": 2,
                "status": "GELE",
                "regulatory_ref": "REG01-INV-2026-001",
            }
        if function == "TransferAsset" and args and args[0] == "RWA-OBL-BANK01-2025-001":
            raise AssetFrozenError("RWA-OBL-BANK01-2025-001", "REG01-INV-2026-001")
        return {}

    client.evaluate_transaction.side_effect = mock_evaluate
    client.submit_transaction.side_effect = mock_submit
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    
    with patch("core.fabric_client.network.FabricClient", return_value=client):
        with patch("core.dependencies._fabric_client_instance", client):
            yield client

@pytest.fixture(scope="function")
async def test_client(
    async_session: AsyncSession,
    mock_fabric_client: AsyncMock,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> AsyncGenerator:
    async def override_get_db() -> AsyncGenerator:
        yield async_session

    async def override_get_redis() -> AsyncGenerator:
        yield fake_redis

    def override_get_fabric() -> AsyncMock:
        return mock_fabric_client

    async def fake_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_fabric] = override_get_fabric

    from jose import jwt as _jose_jwt
    from jose.exceptions import ExpiredSignatureError, JWTError

    async def fake_validate_token(token: str) -> dict:
        try:
            return _jose_jwt.decode(token, _TEST_SIGNING_KEY, algorithms=["HS256"])
        except ExpiredSignatureError as exc:
            raise exc
        except JWTError as exc:
            raise exc

    transport = ASGITransport(app=app)
    with patch("core.api.middleware.rate_limiter.get_redis", fake_get_redis):
        with patch("core.api.middleware.auth_middleware.validate_token", fake_validate_token):
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                yield client

    app.dependency_overrides.clear()

@pytest.fixture
async def test_org(async_session: AsyncSession) -> Organization:
    org = Organization(
        id=BANK01_ORG_ID,
        org_code="BANK01",
        legal_name="Bank01 SA",
        short_name="Bank01",
        org_type="BANQUE",
        lei="R0MUWSFPU8MPRO8K5P83",
        bic_swift="BANK01FRPP",
        msp_id="BANK01MSP",
        country_code="FR",
        jurisdiction="EU",
        is_active=True,
    )
    await async_session.merge(org)
    await async_session.flush()
    return org

@pytest.fixture
async def test_amf_org(async_session: AsyncSession) -> Organization:
    org = Organization(
        id=REG01_ORG_ID,
        org_code="REG01",
        legal_name="Autorité des Marchés Financiers",
        short_name="REG01",
        org_type="REGULATEUR",
        lei="96950066U5XAAIRCPA78",
        msp_id="REG01MSP",
        country_code="FR",
        jurisdiction="EU",
        is_active=True,
    )
    await async_session.merge(org)
    await async_session.flush()
    return org

@pytest.fixture
async def test_user_thomas(async_session: AsyncSession, test_org: Organization) -> User:
    user = User(
        id=THOMAS_USER_ID,
        org_id=BANK01_ORG_ID,
        email="thomas.martin@bank01.fr",
        keycloak_sub="kc-sub-thomas-martin",
        first_name="Thomas",
        last_name="Martin",
        role="EMETTEUR",
        msp_id="BANK01MSP",
        is_active=True,
    )
    await async_session.merge(user)
    # Seed KYC
    from decimal import Decimal
    kyc = ComplianceRecord(
        participant_id=THOMAS_USER_ID,
        kyc_status="VERIFIE",
        kyc_level=3,
        aml_score=Decimal("0.0"),
        risk_category="FAIBLE",
        expires_at=datetime.now(UTC) + timedelta(days=365),
    )
    await async_session.merge(kyc)
    await async_session.flush()
    return user

@pytest.fixture
async def test_user_sophie(async_session: AsyncSession, test_amf_org: Organization) -> User:
    user = User(
        id=SOPHIE_USER_ID,
        org_id=REG01_ORG_ID,
        email="sophie.lambert@amf.fr",
        keycloak_sub="kc-sub-sophie-lambert",
        first_name="Sophie",
        last_name="Lambert",
        role="REGULATEUR",
        msp_id="REG01MSP",
        is_active=True,
    )
    await async_session.merge(user)
    # Seed KYC
    from decimal import Decimal
    kyc = ComplianceRecord(
        participant_id=SOPHIE_USER_ID,
        kyc_status="VERIFIE",
        kyc_level=3,
        aml_score=Decimal("0.0"),
        risk_category="FAIBLE",
        expires_at=datetime.now(UTC) + timedelta(days=365),
    )
    await async_session.merge(kyc)
    await async_session.flush()
    return user

@pytest.fixture
def token_thomas_martin() -> str:
    payload = {"sub": "kc-sub-thomas-martin", "email": "thomas.martin@bank01.fr", "rwa_role": "EMETTEUR"}
    return create_access_token(payload, expires_delta=timedelta(hours=24))

@pytest.fixture
def token_sophie_lambert() -> str:
    payload = {"sub": "kc-sub-sophie-lambert", "email": "sophie.lambert@amf.fr", "rwa_role": "REGULATEUR"}
    return create_access_token(payload, expires_delta=timedelta(hours=24))

@pytest.fixture
def token_james_wilson() -> str:
    payload = {"sub": "kc-sub-james-wilson", "email": "james.wilson@natwest.com", "rwa_role": "TRADER"}
    return create_access_token(payload, expires_delta=timedelta(hours=24))

@pytest.fixture
def token_expired() -> str:
    payload = {"sub": "kc-sub-thomas-martin", "email": "thomas.martin@bank01.fr", "rwa_role": "EMETTEUR"}
    return create_access_token(payload, expires_delta=timedelta(hours=-1))

@pytest.fixture
def sample_provenance() -> list[ProvenanceRecord]:
    _base_ts = datetime.now(UTC)
    return [
        ProvenanceRecord(
            tx_id=REAL_TX_1,
            timestamp=_base_ts,
            actor_msp="BANK01MSP",
            actor_dn="CN=admin@bank01.finance-trust.com,OU=admin",
            action="TOKENISE",
            from_owner="",
            to_owner="CN=admin@bank01.finance-trust.com,OU=admin",
            amount=50000000.0,
            justification="Tokenisation OAT emission primaire",
            block_number=0,
        ),
        ProvenanceRecord(
            tx_id=REAL_TX_2,
            timestamp=_base_ts + timedelta(hours=12),
            actor_msp="BANK01MSP",
            actor_dn="CN=admin@bank01.finance-trust.com,OU=admin",
            action="TRANSFERE",
            from_owner="CN=admin@bank01.finance-trust.com,OU=admin",
            to_owner="CN=pierre.moreau,OU=Cust 01",
            amount=24739375.0,
            justification="Cession bloc Inv01 portefeuille ESG",
            block_number=0,
        ),
        ProvenanceRecord(
            tx_id=REAL_TX_3,
            timestamp=_base_ts + timedelta(hours=13),
            actor_msp="REG01MSP",
            actor_dn="CN=admin@reg01-regulateur.finance-trust.com,OU=admin",
            action="GELE",
            from_owner="",
            to_owner="",
            amount=0.0,
            justification="Investigation MIFID II art.69",
            block_number=0,
        ),
    ]

@pytest.fixture
def sample_integrity_report(sample_provenance: list[ProvenanceRecord]) -> IntegrityReport:
    checker = IntegrityChecker()
    return checker.check("RWA-OBL-BANK01-2025-001", sample_provenance)

@pytest.fixture(scope="session", autouse=True)
def sample_compliance_data() -> None:
    path = Path("database/fixtures/json/compliance_kyc_aml.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        data = {
            "participants": [
                {
                    "user_id": str(THOMAS_USER_ID),
                    "full_name": "Thomas Martin",
                    "aml_indicators": {"jurisdiction_risk": 0.03, "cross_border_activity": 0.05, "unusual_volume": 0.04},
                },
                {
                    "user_id": str(JAMES_USER_ID),
                    "full_name": "James Wilson",
                    "aml_indicators": {"jurisdiction_risk": 0.08, "cross_border_activity": 0.10, "unusual_volume": 0.07},
                },
            ],
            "sanctions_lists": {
                "OFAC_SDN": ["Jamez Wilzon"],
                "UN_CONSOLIDATED": [],
                "EU_CONSOLIDATED": [],
                "UK_HMT": [],
                "PEP_LEVEL_1": [],
                "PEP_LEVEL_2": [],
                "PEP_LEVEL_3": [],
            },
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
