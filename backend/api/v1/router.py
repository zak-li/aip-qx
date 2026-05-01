from fastapi import APIRouter

from backend.features.agent import router as agent
from backend.features.assets import router as assets
from backend.features.audit import router as audit
from backend.features.auth import organizations_router as organizations
from backend.features.auth import router as auth
from backend.features.compliance import router as compliance
from backend.features.events import router as events
from backend.features.transactions import router as transactions
from backend.features.zkp import router as zkp

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(assets.router, prefix="/assets", tags=["Assets Lifecycle"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["Ledger Transactions"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["Network Organizations"])
api_router.include_router(audit.router, prefix="/audit", tags=["Regulatory Audit"])
api_router.include_router(compliance.router, prefix="/compliance", tags=["AML / KYC Compliance"])
api_router.include_router(agent.router, prefix="/agent", tags=["RAG Agent"])
api_router.include_router(zkp.router, prefix="/zkp", tags=["ZKP zk-KYC"])
api_router.include_router(events.router, prefix="/events", tags=["Live Events"])
