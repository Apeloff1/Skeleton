from skeleton.ai.knowledge_snapshots import *
def test_digest_captures_all_watermarks():assert digest(KnowledgeSnapshot(1,"i","m","s"))!=digest(KnowledgeSnapshot(2,"i","m","s"))
def test_stale_snapshot_cannot_override_newer_source():assert not restore_allowed(KnowledgeSnapshot(1,"i","m","s"),2)
