from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db, require_role
from core.features.auth.models import User
from core.features.tribunal.service import TribunalError, TribunalService

router = APIRouter()


class CommitVoteRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    session_id: UUID
    commit_hash: str = Field(..., min_length=64, max_length=64)


class RevealVoteRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    vote_id: UUID
    vote: str = Field(..., pattern="^(FRAUD|LEGITIMATE)$")
    salt: str = Field(..., min_length=8, max_length=128)


@router.post("/vote/commit", status_code=201)
async def commit_vote(
    body: CommitVoteRequest,
    current_user: User = Depends(require_role("AUDITEUR")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = TribunalService(db)
    try:
        vote = await service.commit_vote(body.session_id, current_user.id, body.commit_hash)
    except TribunalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"vote_id": str(vote.id), "session_id": str(vote.session_id)}


@router.post("/vote/reveal")
async def reveal_vote(
    body: RevealVoteRequest,
    current_user: User = Depends(require_role("AUDITEUR")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = TribunalService(db)
    try:
        ok = await service.reveal_vote(body.vote_id, body.vote, body.salt)
    except TribunalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hash mismatch — reveal rejected.")
    return {"revealed": True}


@router.post("/session/{session_id}/tally")
async def tally_session(
    session_id: UUID,
    current_user: User = Depends(require_role("COMPLIANCE_OFFICER", "REGULATEUR")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = TribunalService(db)
    try:
        decision = await service.tally_and_slash(session_id)
    except TribunalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"session_id": str(session_id), "decision": decision}
