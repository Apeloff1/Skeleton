"""Regression coverage for privacy, retention and idle video authorization."""
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_video_history import DragonVideoHistory,canonical_video_url
from skeleton.ai.webcrawler.dragon_video_discovery import VideoCandidate,rank_similar_videos
from skeleton.ai.webcrawler.dragon_idle_planner import IdleVideoPlanner,IdleVideoPolicy

@pytest.mark.parametrize('url',[
    'http://example.org/watch?v=1','https://localhost/watch',
    'https://127.0.0.1/watch','https://10.0.0.1/watch',
    'https://192.168.1.2/watch','https://[::1]/watch',
    'https://example.local/watch','https://user:pass@example.org/watch',
    'https://example.org:8443/watch',
])
def test_history_rejects_private_or_untrusted_urls(url):
    with pytest.raises(ValueError):canonical_video_url(url)

def test_history_consent_retention_and_erasure():
    history=DragonVideoHistory(sqlite3.connect(':memory:'))
    with pytest.raises(PermissionError):
        history.record('owner','https://example.org/watch?v=1','One',
                       watched_at=10,duration_ms=100,watched_ms=50)
    history.record('owner','https://example.org/watch?v=1&token=secret','One',
                   watched_at=10,duration_ms=100,watched_ms=50,tags=('Physics',),consent=True)
    history.record('owner','https://example.org/watch?v=2','Two',
                   watched_at=20,duration_ms=100,watched_ms=90,tags=('physics',),consent=True)
    assert len(history.recent('owner'))==2
    assert all('token' not in v.canonical_url for v in history.recent('owner'))
    assert history.prune('owner',older_than=15)==1
    assert len(history.recent('owner'))==1
    assert history.erase('owner')==1

def test_discovery_proposals_exclude_watched():
    history=DragonVideoHistory(sqlite3.connect(':memory:'))
    history.record('owner','https://example.org/watch?v=1','Physics',
                   watched_at=1,duration_ms=100,watched_ms=80,tags=('physics',),consent=True)
    proposals=rank_similar_videos(history.recent('owner'),(
        VideoCandidate('https://example.org/watch?v=1','Seen',('physics',),'catalog'),
        VideoCandidate('https://example.org/watch?v=2','New',('physics',),'catalog'),
        VideoCandidate('https://example.org/watch?v=3','Other',('cooking',),'catalog'),
    ))
    assert len(proposals)==1 and proposals[0].title=='New'
    assert proposals[0].requires_approval

def test_idle_planner_requires_independent_consent_and_revokes():
    planner=IdleVideoPlanner(IdleVideoPolicy(min_idle_seconds=30))
    history=DragonVideoHistory(sqlite3.connect(':memory:'))
    visit=history.record('owner','https://example.org/watch?v=1','Physics',
                         watched_at=1,duration_ms=100,watched_ms=80,tags=('physics',),consent=True)
    proposal=rank_similar_videos((visit,),(VideoCandidate(
        'https://example.org/watch?v=2','More physics',('physics',),'catalog'),))[0]
    planner.activity(100)
    assert planner.propose((proposal,),now=120,consent=True)==()
    with pytest.raises(PermissionError):planner.propose((proposal,),now=140,consent=False)
    assert len(planner.propose((proposal,),now=140,consent=True))==1
    with pytest.raises(PermissionError):planner.approve(proposal.proposal_id,consent=False)
    planner.approve(proposal.proposal_id,consent=True)
    with pytest.raises(PermissionError):planner.take_approved(consent=False)
    planner.revoke()
    assert planner.take_approved(consent=True)==()
