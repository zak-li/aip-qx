from datetime import datetime, UTC

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

class AssetNotFoundException(Exception):
    def __init__(self, asset_id: str) -> None:
        self.asset_id = asset_id
        self.message = f"Actif {asset_id} introuvable sur le ledger"
        super().__init__(self.message)

class AssetFrozenError(Exception):
    def __init__(self, asset_id: str, regulatory_ref: str) -> None:
        self.asset_id = asset_id
        self.regulatory_ref = regulatory_ref
        self.message = f"Actif {asset_id} gelé — transfert impossible (réf: {regulatory_ref})"
        super().__init__(self.message)

class AssetAlreadyExistsError(Exception):
    def __init__(self, asset_id: str) -> None:
        self.asset_id = asset_id
        self.message = f"Actif {asset_id} existe déjà sur le ledger."
        super().__init__(self.message)

class FabricEndorsementError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        self.message = f"Rejet du consensus Fabric: {detail}"
        super().__init__(self.message)

class ComplianceBlockedError(Exception):
    def __init__(self, reason: str, blocked_by: str) -> None:
        self.reason = reason
        self.blocked_by = blocked_by
        self.message = f"Opération bloquée en raison de {reason} par {blocked_by}"
        super().__init__(self.message)

class InsufficientPermissionsError(HTTPException):
    def __init__(self, required_role: str) -> None:
        self.required_role = required_role
        self.message = f"Privilèges insuffisants. Rôle minimum requis: {required_role}"
        super().__init__(status_code=403, detail=self.message)

def _format_error(error_type: str, message: str) -> dict[str, str]:
    return {
        "error": error_type,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }

def setup_global_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AssetNotFoundException)
    async def asset_not_found_handler(request: Request, exc: AssetNotFoundException) -> JSONResponse:
        return JSONResponse(status_code=404, content=_format_error("AssetNotFoundException", exc.message))

    @app.exception_handler(AssetFrozenError)
    async def asset_frozen_handler(request: Request, exc: AssetFrozenError) -> JSONResponse:
        return JSONResponse(status_code=409, content=_format_error("AssetFrozenError", exc.message))

    @app.exception_handler(AssetAlreadyExistsError)
    async def asset_exists_handler(request: Request, exc: AssetAlreadyExistsError) -> JSONResponse:
        return JSONResponse(status_code=409, content=_format_error("AssetAlreadyExistsError", exc.message))

    @app.exception_handler(FabricEndorsementError)
    async def fabric_endorsement_handler(request: Request, exc: FabricEndorsementError) -> JSONResponse:
        return JSONResponse(status_code=502, content=_format_error("FabricEndorsementError", exc.message))

    @app.exception_handler(ComplianceBlockedError)
    async def compliance_blocked_handler(request: Request, exc: ComplianceBlockedError) -> JSONResponse:
        return JSONResponse(status_code=403, content=_format_error("ComplianceBlockedError", exc.message))
