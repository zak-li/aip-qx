"""gRPC servicer for the Organizations service."""
from __future__ import annotations

from uuid import UUID

import grpc
import grpc.aio
from sqlalchemy import func, select

from backend.core.database import AsyncSessionLocal
from backend.features.assets.models import Asset
from backend.features.auth.models import Organization, User
from backend.grpc_generated import organizations_pb2, organizations_pb2_grpc

_VALID_ROLES = {
    "EMETTEUR", "TRADER", "CUSTODIAN", "REGULATEUR",
    "AUDITEUR", "COMPLIANCE_OFFICER", "SUPER_ADMIN",
}
_VALID_COUNTRIES = {"FR", "GB", "MA", "DE", "US", "LU", "BE", "CH", "SG", "AE"}


class OrganizationsServicer(organizations_pb2_grpc.OrganizationsServiceServicer):

    async def ListOrganizations(
        self,
        request: organizations_pb2.ListOrgsRequest,
        context: grpc.aio.ServicerContext,
    ) -> organizations_pb2.OrgList:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(Organization)
                .limit(request.limit or 50)
                .offset(request.offset or 0)
            )
            orgs = (await db.execute(stmt)).scalars().all()

        return organizations_pb2.OrgList(
            organizations=[
                organizations_pb2.OrgResponse(
                    id=str(o.id),
                    name=o.name or "",
                    msp_id=o.msp_id or "",
                    status=o.status or "",
                )
                for o in orgs
            ]
        )

    async def ListUsers(
        self,
        request: organizations_pb2.ListUsersRequest,
        context: grpc.aio.ServicerContext,
    ) -> organizations_pb2.UserList:
        role = context.user_payload.get("role", "")
        if role not in ("REGULATEUR", "COMPLIANCE_OFFICER", "SUPER_ADMIN", "AUDITEUR"):
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient role")

        if request.role and request.role.upper() not in _VALID_ROLES:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Invalid role. Must be one of: {', '.join(sorted(_VALID_ROLES))}",
            )
        if request.country and request.country.upper() not in _VALID_COUNTRIES:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid country code")

        async with AsyncSessionLocal() as db:
            stmt = select(User, Organization).join(Organization, User.org_id == Organization.id)
            if request.role:
                stmt = stmt.where(User.role == request.role.upper())
            if request.country:
                stmt = stmt.where(Organization.country_code == request.country.upper())
            stmt = stmt.limit(request.limit or 100).offset(request.offset or 0)
            rows = (await db.execute(stmt)).all()

        users = [
            organizations_pb2.UserSummary(
                id=str(u.id),
                email=u.email or "",
                first_name=u.first_name or "",
                last_name=u.last_name or "",
                role=u.role or "",
                department=u.department or "",
                employee_id=u.employee_id or "",
                phone=u.phone or "",
                msp_id=u.msp_id or "",
                mfa_enabled=bool(u.mfa_enabled),
                is_active=bool(u.is_active),
                org_id=str(u.org_id),
                org_name=org.legal_name or "",
                org_country=org.country_code or "",
            )
            for u, org in rows
        ]
        return organizations_pb2.UserList(users=users)

    async def GetPortfolio(
        self,
        request: organizations_pb2.PortfolioRequest,
        context: grpc.aio.ServicerContext,
    ) -> organizations_pb2.PortfolioResponse:
        org_uuid = UUID(request.org_id)
        async with AsyncSessionLocal() as db:
            active_count = (await db.execute(
                select(func.count(Asset.id)).where(
                    Asset.issuer_org_id == org_uuid,
                    Asset.status == "ACTIF",
                )
            )).scalar() or 0

            total_value = float((await db.execute(
                select(func.coalesce(func.sum(Asset.current_value), 0)).where(
                    Asset.issuer_org_id == org_uuid,
                    Asset.status != "REMBOURSE",
                )
            )).scalar() or 0)

        return organizations_pb2.PortfolioResponse(
            org_id=request.org_id,
            total_assets_value=total_value,
            active_assets_count=active_count,
        )
