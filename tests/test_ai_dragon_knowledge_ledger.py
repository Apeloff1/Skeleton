"""Knowledge-ledger identity and schema migration regressions."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_knowledge_ledger import DragonKnowledgeLedger
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import EvidencePass


def ev(claim:str, *, pass_id:str="p1", supports:bool=True)->EvidencePass:
    return EvidencePass(
        "source-1","rev-1",pass_id,claim,supports,.8,.9,
        "lineage-1","loc://1",f"observation for {claim}",
    )


def test_same_source_pass_can_support_multiple_distinct_claims():
    ledger=DragonKnowledgeLedger(sqlite3.connect(":memory:"))
    ledger.add("u",ev("claim-a"),authorized=True)
    ledger.add("u",ev("claim-b"),authorized=True)
    assert ledger.readings("u","claim-a",authorized=True)==(ev("claim-a"),)
    assert ledger.readings("u","claim-b",authorized=True)==(ev("claim-b"),)


def test_exact_replay_is_idempotent_but_same_claim_mutation_conflicts():
    ledger=DragonKnowledgeLedger(sqlite3.connect(":memory:"))
    item=ev("claim-a")
    ledger.add("u",item,authorized=True)
    ledger.add("u",item,authorized=True)
    with pytest.raises(ValueError,match="immutable evidence identity conflict"):
        ledger.add("u",ev("claim-a",supports=False),authorized=True)


def test_legacy_primary_key_migrates_without_losing_evidence():
    db=sqlite3.connect(":memory:")
    db.execute("""CREATE TABLE dragon_evidence_passes(
        owner TEXT NOT NULL,claim_id TEXT NOT NULL,source_id TEXT NOT NULL,
        source_revision TEXT NOT NULL,pass_id TEXT NOT NULL,supports INTEGER NOT NULL,
        confidence REAL NOT NULL,reliability REAL NOT NULL,
        independence_group TEXT NOT NULL,evidence_locator TEXT NOT NULL,
        observation TEXT NOT NULL,
        PRIMARY KEY(owner,source_id,source_revision,pass_id))""")
    x=ev("claim-a")
    db.execute("INSERT INTO dragon_evidence_passes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ("u",x.claim_id,x.source_id,x.source_revision,x.pass_id,int(x.supports),
         x.confidence,x.reliability,x.independence_group,x.evidence_locator,x.observation))
    db.commit()
    ledger=DragonKnowledgeLedger(db)
    assert ledger.readings("u","claim-a",authorized=True)==(x,)
    ledger.add("u",ev("claim-b"),authorized=True)
    pk=[r[1] for r in sorted((r for r in db.execute(
        "PRAGMA table_info(dragon_evidence_passes)") if r[5]),key=lambda r:r[5])]
    assert pk==["owner","claim_id","source_id","source_revision","pass_id"]
    assert len(ledger.readings("u","claim-b",authorized=True))==1


def test_reread_budget_is_claim_scoped_not_cross_claim():
    ledger=DragonKnowledgeLedger(sqlite3.connect(":memory:"))
    for i in range(12):
        ledger.add("u",ev("claim-a",pass_id=f"p{i}"),authorized=True)
        ledger.add("u",ev("claim-b",pass_id=f"p{i}"),authorized=True)
    assert len(ledger.readings("u","claim-a",authorized=True))==12
    assert len(ledger.readings("u","claim-b",authorized=True))==12
