"""Tests for multiplayer authority starter."""
import time
import pytest
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority, MultiplayerError

def test_issue_and_verify():
    auth = SessionAuthority(session_id="s1")
    grant = auth.issue_grant("p1")
    assert auth.verify_grant("p1", grant.digest)
    assert not auth.verify_grant("p1", "bad")

def test_full_session():
    auth = SessionAuthority(session_id="s2", max_players=1)
    auth.issue_grant("p1")
    with pytest.raises(MultiplayerError):
        auth.issue_grant("p2")

def test_expiry():
    auth = SessionAuthority(session_id="s3")
    grant = auth.issue_grant("p1")
    grant.expires_at = time.time() - 1
    assert not auth.verify_grant("p1", grant.digest)
