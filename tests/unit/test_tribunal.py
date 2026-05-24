import uuid

import pytest

from core.features.tribunal.service import TribunalService, compute_commit_hash


# Mock DB Session for testing logic
class MockAsyncSession:
    def __init__(self):
        self.storage = {}
        self.storage["TribunalVote"] = []
        self.storage["TribunalSession"] = []
        
    def add(self, obj):
        class_name = obj.__class__.__name__
        if not hasattr(obj, 'id') or obj.id is None:
            obj.id = uuid.uuid4()
        self.storage[class_name].append(obj)
        
    async def commit(self):
        pass
        
    async def refresh(self, obj):
        pass
        
    async def execute(self, stmt):
        # Extremely simplified mock for the specific tests
        class MockResult:
            def __init__(self, data):
                self.data = data
            def scalar_one_or_none(self):
                return self.data[0] if self.data else None
            def scalar_one(self):
                return self.data[0]
            def scalars(self):
                class MockScalars:
                    def __init__(self, d): self.d = d
                    def all(self): return self.d
                return MockScalars(self.data)
                
        stmt_str = str(stmt)
        params = stmt.compile().params

        if "tribunal_votes" in stmt_str:
            votes = self.storage["TribunalVote"]

            # Filter by vote id (reveal_vote lookup)
            if "vote_id" in params or any(k.startswith("id") for k in params):
                vid = params.get("id_1") or params.get("id")
                if vid:
                    return MockResult([v for v in votes if v.id == vid])

            # Filter by session_id + auditor_id (double-vote guard in commit_vote)
            sid = params.get("session_id_1") or params.get("session_id")
            aid = params.get("auditor_id_1") or params.get("auditor_id")
            if sid and aid:
                return MockResult([v for v in votes if v.session_id == sid and v.auditor_id == aid])

            # Filter by session_id only (tally_and_slash)
            if sid:
                return MockResult([v for v in votes if v.session_id == sid])

            return MockResult(votes)

        elif "tribunal_sessions" in stmt_str:
            sid = params.get("id_1") or params.get("id")
            sessions = self.storage["TribunalSession"]
            if sid:
                return MockResult([s for s in sessions if s.id == sid])
            return MockResult(sessions)

        return MockResult([])

@pytest.mark.asyncio
async def test_tribunal_game_theory_slashing():
    """Simulate a Tribunal where the majority is honest and one deviates.
    Verifies that the Nash Equilibrium holds (the deviator is slashed).
    """
    db = MockAsyncSession()
    service = TribunalService(db)
    
    # Create Session
    import datetime as _dt

    from core.features.tribunal.models import TribunalSession
    session = TribunalSession(
        id=uuid.uuid4(),
        asset_id=uuid.uuid4(),
        reason="Suspicious AML Volume",
        expires_at=_dt.datetime.now(_dt.UTC) + _dt.timedelta(hours=1),
    )
    db.add(session)
    
    # 5 Auditors (4 Honest, 1 Malicious/Deviating)
    auditors = [uuid.uuid4() for _ in range(5)]
    votes = []
    
    ground_truth = "FRAUD"
    deviator_vote = "LEGITIMATE"
    
    # PHASE 1: COMMIT
    for i, a_id in enumerate(auditors):
        v = ground_truth if i < 4 else deviator_vote
        salt = f"salt_{i}"
        h = compute_commit_hash(v, salt)
        vote_obj = await service.commit_vote(session.id, a_id, h)
        votes.append((vote_obj, v, salt))
        
    # PHASE 2: REVEAL
    for vote_obj, v, salt in votes:
        success = await service.reveal_vote(vote_obj.id, v, salt)
        assert success is True
        
    # PHASE 3: TALLY AND SLASH
    decision = await service.tally_and_slash(session.id)
    
    # Verify Supermajority Outcome
    assert decision == "FRAUD"
    
    # Verify Game Theory Incentives
    db_votes = db.storage["TribunalVote"]
    
    # Honest auditors should be rewarded
    honest_votes = [v for v in db_votes if v.revealed_vote == "FRAUD"]
    assert len(honest_votes) == 4
    for hv in honest_votes:
        assert hv.rewarded is True
        assert hv.slashed is False
        assert hv.reputation_staked == 110.0 # 100 base + 10 reward
        
    # The deviating auditor should be slashed
    malicious_votes = [v for v in db_votes if v.revealed_vote == "LEGITIMATE"]
    assert len(malicious_votes) == 1
    mv = malicious_votes[0]
    assert mv.rewarded is False
    assert mv.slashed is True
    assert mv.reputation_staked == 50.0 # 100 base - 50 slash penalty

@pytest.mark.asyncio
async def test_tribunal_invalid_reveal():
    """Test that a malicious auditor cannot change their vote during reveal."""
    import datetime as _dt

    from core.features.tribunal.models import TribunalSession

    db = MockAsyncSession()
    service = TribunalService(db)

    session_id = uuid.uuid4()
    session = TribunalSession(
        id=session_id,
        asset_id=uuid.uuid4(),
        reason="Test invalid reveal",
        expires_at=_dt.datetime.now(_dt.UTC) + _dt.timedelta(hours=1),
    )
    db.add(session)

    a_id = uuid.uuid4()
    
    original_vote = "FRAUD"
    salt = "secret_salt"
    h = compute_commit_hash(original_vote, salt)
    
    vote_obj = await service.commit_vote(session_id, a_id, h)
    
    # Try to reveal a DIFFERENT vote than committed
    success = await service.reveal_vote(vote_obj.id, "LEGITIMATE", salt)
    assert success is False
    
    # Try to reveal correct vote with WRONG salt
    success = await service.reveal_vote(vote_obj.id, "FRAUD", "wrong_salt")
    assert success is False
    
    # Try correct reveal
    success = await service.reveal_vote(vote_obj.id, "FRAUD", salt)
    assert success is True
