from skeleton.agents.swarm_dedupe import CompletionCache
from skeleton.agents.swarm_sharding import distribution,owners

def test_rendezvous_owners_are_deterministic(): assert owners("task",["c","a","b"],2)==owners("task",["b","c","a"],2)
def test_rendezvous_never_duplicates_nodes(): assert len(owners("x",["a","a","b"],5))==2
def test_distribution_accounts_for_each_replica():
 d=distribution([str(i) for i in range(50)],["a","b","c"],2); assert sum(d.values())==100

def test_completion_cache_detects_duplicate_completion():
 c=CompletionCache(); assert c.record("t","token") is True; assert c.record("t","token") is False

def test_completion_cache_expires_old_records():
 now=[0.0]; c=CompletionCache(ttl_seconds=5,clock=lambda:now[0]); c.record("t","x"); now[0]=6; assert c.contains("t","x") is False

def test_completion_cache_evicts_oldest_when_bounded():
 c=CompletionCache(max_entries=2); c.record("a","1"); c.record("b","1"); c.record("c","1"); assert c.contains("a","1") is False
