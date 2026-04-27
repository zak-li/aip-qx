from __future__ import annotations

import hashlib
import logging
from datetime import datetime, UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.tribunal.models import TribunalSession, TribunalVote

logger = logging.getLogger(__name__)


class TribunalError(Exception):
    """Raised for tribunal-protocol violations (closed session, double vote, etc.)."""


def compute_commit_hash(vote: str, salt: str) -> str:
    """Computes SHA-256 hash of the vote and salt."""
    return hashlib.sha256(f"{vote}:{salt}".encode()).hexdigest()


class TribunalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_active_session(self, session_id: UUID, expected_status: str) -> TribunalSession:
        sess = (
            await self.db.execute(select(TribunalSession).where(TribunalSession.id == session_id))
        ).scalar_one_or_none()
        if sess is None:
            raise TribunalError("Tribunal session does not exist")
        if sess.status != expected_status:
            raise TribunalError(
                f"Session is in status {sess.status}; expected {expected_status}"
            )
        if sess.expires_at and sess.expires_at < datetime.now(UTC):
            raise TribunalError("Session has expired")
        return sess

    async def commit_vote(self, session_id: UUID, auditor_id: UUID, commit_hash: str) -> TribunalVote:
        """Phase 1: Auditor submits a hashed vote.

        Refuses if the session is not in COMMIT phase, expired, or if the
        auditor has already cast a vote in this session.
        """
        await self._get_active_session(session_id, expected_status="COMMIT")

        existing = (
            await self.db.execute(
                select(TribunalVote).where(
                    TribunalVote.session_id == session_id,
                    TribunalVote.auditor_id == auditor_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise TribunalError("Auditor has already committed a vote for this session")

        vote = TribunalVote(
            session_id=session_id,
            auditor_id=auditor_id,
            commit_hash=commit_hash,
            reputation_staked=100.0,
        )
        self.db.add(vote)
        await self.db.commit()
        await self.db.refresh(vote)
        return vote

    async def reveal_vote(self, vote_id: UUID, vote: str, salt: str) -> bool:
        """Phase 2: Auditor reveals their vote. We verify against the commit hash."""
        stmt = select(TribunalVote).where(TribunalVote.id == vote_id)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            return False
        if record.revealed_vote is not None:
            raise TribunalError("Vote has already been revealed")

        await self._get_active_session(record.session_id, expected_status="REVEAL")

        expected_hash = compute_commit_hash(vote, salt)
        if record.commit_hash != expected_hash:
            logger.warning("Reveal hash mismatch!")
            return False

        record.revealed_vote = vote
        record.revealed_salt = salt
        await self.db.commit()
        return True

    async def tally_and_slash(self, session_id: UUID) -> str | None:
        """Phase 3: Tally votes, determine supermajority, apply Game Theory slashing."""
        stmt = select(TribunalVote).where(
            TribunalVote.session_id == session_id,
            TribunalVote.revealed_vote != None
        )
        result = await self.db.execute(stmt)
        votes = result.scalars().all()

        if not votes:
            return None

        total_votes = len(votes)
        counts = {"FRAUD": 0, "LEGITIMATE": 0}

        for v in votes:
            if v.revealed_vote in counts:
                counts[v.revealed_vote] += 1

        # Pick the option with the highest count, then check the supermajority
        # threshold against that count. Avoids the previous bug where dict
        # iteration order made the decision non-deterministic when both options
        # ended up close.
        threshold = total_votes * 2 / 3
        winning_option, winning_count = max(counts.items(), key=lambda kv: kv[1])
        decision = winning_option if winning_count >= threshold else None

        if decision:
            # Apply Slashing (Game Theory Schelling Point)
            for v in votes:
                if v.revealed_vote == decision:
                    v.rewarded = True
                    v.slashed = False
                    v.reputation_staked += 10.0  # Reward R
                else:
                    v.slashed = True
                    v.rewarded = False
                    v.reputation_staked -= 50.0  # Penalty f*S

            # Update session
            stmt_sess = select(TribunalSession).where(TribunalSession.id == session_id)
            sess = (await self.db.execute(stmt_sess)).scalar_one()
            sess.status = "RESOLVED"
            sess.final_decision = decision

        await self.db.commit()
        return decision
