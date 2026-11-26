"""Disjoint-lane same-owner reservations with escrowed quota deltas.

An owner may have several plans only when their node/edge write lanes and
logical resources do not overlap. Bootstrap keeps an exclusive owner lock.
No optimistic merge of conflicting before-images, no quota overbooking.
"""
from __future__ import annotations

from pathlib import Path
from core import dragon_graph_authority as a
from core.dragon_game_corpus import CatalogueHeld

SCHEMA=(
    """CREATE TABLE structural_same_owner(singleton INTEGER PRIMARY KEY CHECK(singleton=1),epoch TEXT NOT NULL)""",
    """CREATE TABLE structural_owner_lanes(owner TEXT NOT NULL,lane INTEGER NOT NULL CHECK(lane BETWEEN 0 AND 9),
       sequence INTEGER NOT NULL REFERENCES structural_batches(sequence) ON DELETE CASCADE,
       nodes INTEGER NOT NULL CHECK(nodes>=0),edges INTEGER NOT NULL CHECK(edges>=0),
       PRIMARY KEY(owner,lane)) WITHOUT ROWID""",
    """CREATE INDEX structural_owner_lane_seq ON structural_owner_lanes(sequence)""",
    """CREATE TABLE structural_resource_locks(owner TEXT NOT NULL,kind TEXT NOT NULL,identity TEXT NOT NULL,
       sequence INTEGER NOT NULL REFERENCES structural_batches(sequence) ON DELETE CASCADE,
       PRIMARY KEY(owner,kind,identity)) WITHOUT ROWID""",
    """CREATE INDEX structural_resource_seq ON structural_resource_locks(sequence)""",
)


class ReservationBusy(CatalogueHeld):
    """Transient conflict; preserve queued work instead of marking it held."""


def enabled(db):
    if not a._table(db,"structural_same_owner"):
        if any(a._table(db,t) for t in ("structural_owner_lanes","structural_resource_locks")):
            raise a.GraphHeld("partial same-owner topology")
        return False
    marker=db.execute("SELECT epoch FROM main.structural_same_owner WHERE singleton=1").fetchone()
    root=db.execute("SELECT epoch FROM main.structural_multi_identity WHERE singleton=1").fetchone()
    if not marker or not root or marker[0]!=root[0] or not all(a._table(db,t) for t in ("structural_owner_lanes","structural_resource_locks")):
        raise a.GraphHeld("same-owner epoch or registry differs")
    return True


def install(root,*,offline_acknowledged=False):
    if offline_acknowledged is not True:raise a.GraphHeld("stop all graph writers")
    from core import dragon_graph_multi_batch as multi
    with a._probe_connection(Path(root)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            if not multi.enabled(db):raise a.GraphHeld("enable multi-batch first")
            multi.assert_fence(db)
            if enabled(db):
                db.execute("COMMIT");return {"installed":True,"replayed":True}
            multi.verify(db)
            # Registry is empty following the full idle audit. Change only
            # owner membership PK; all sequence and terminal receipts remain.
            db.execute("DROP TABLE main.structural_batch_owners")
            db.execute("""CREATE TABLE structural_batch_owners(owner TEXT NOT NULL,
                sequence INTEGER NOT NULL REFERENCES structural_batches(sequence) ON DELETE CASCADE,
                PRIMARY KEY(owner,sequence)) WITHOUT ROWID""")
            db.execute("CREATE INDEX structural_batch_owner_seq ON structural_batch_owners(sequence)")
            for sql in SCHEMA:db.execute(sql)
            epoch=db.execute("SELECT epoch FROM main.structural_multi_identity WHERE singleton=1").fetchone()[0]
            db.execute("INSERT INTO main.structural_same_owner VALUES(1,?)",(epoch,))
            a._fence(db)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"installed":True,"replayed":False,"owner_lane_exclusivity":True,"quota_escrow":True}


def check_owner(db,owner):
    if db.execute("SELECT 1 FROM main.structural_resource_locks WHERE owner=? AND kind='bootstrap'",(owner,)).fetchone():
        raise ReservationBusy("owner bootstrap reservation pending")


def check_lane(db,owner,index):
    if not enabled(db):return
    check_owner(db,owner)
    if db.execute("SELECT 1 FROM main.structural_owner_lanes WHERE owner=? AND lane=?",(owner,index)).fetchone():
        raise ReservationBusy("owner graph lane already reserved")


def check_resource(db,owner,kind,identity):
    if not enabled(db):return
    check_owner(db,owner)
    if db.execute("SELECT 1 FROM main.structural_resource_locks WHERE owner=? AND kind=? AND identity=?",(owner,kind,identity)).fetchone():
        raise ReservationBusy("structural resource already reserved")


def quota(db,owner):
    if not enabled(db):return 0,0
    return tuple(db.execute("SELECT COALESCE(SUM(nodes),0),COALESCE(SUM(edges),0) FROM main.structural_owner_lanes WHERE owner=?",(owner,)).fetchone())


def keys(plan):
    mode=plan["mode"]
    locks={(j["owner"],mode,j["id"]) for j in plan["jobs"]}
    locks.update((g["owner"],"snapshot",g["snapshot"]) for g in plan.get("grants",[]))
    return locks


def lanes(plan):
    result={}
    for key,part in plan["lanes"].items():
        for kind in ("nodes","edges"):
            for before,after in part[kind]:
                pair=(after[0],int(key))
                count=result.setdefault(pair,[0,0])
                if before is None:count[0 if kind=="nodes" else 1]+=1
    # All changed lanes, including timestamp-only and replay changes, locked.
    claimed={(owner,index):[nodes,edges] for owner,index,nodes,edges in plan["deltas"]}
    if len(claimed)!=len(plan["deltas"]) or result!=claimed:raise a.GraphHeld("lane quota witness differs")
    return result


def reserve(db,plan):
    from core.dragon_lead_graph import MAX_NODES,MAX_EDGES,NODES_PER_LANE,EDGES_PER_LANE
    seq=plan["sequence"];owners={j["owner"] for j in plan["jobs"]}
    lane_rows=lanes(plan);resources=keys(plan)
    totals={owner:[0,0] for owner in owners}
    for owner in owners:
        check_owner(db,owner)
        if plan["mode"]=="bootstrap" and db.execute("SELECT 1 FROM main.structural_batch_owners WHERE owner=? AND sequence<>?",(owner,seq)).fetchone():
            raise ReservationBusy("bootstrap requires exclusive owner")
    for owner,kind,identity in resources:check_resource(db,owner,kind,identity)
    for (owner,index),delta in lane_rows.items():
        if owner not in owners:raise a.GraphHeld("quota reservation owner differs")
        check_lane(db,owner,index)
        row=db.execute("SELECT nodes,edges FROM main.lead_lane_counts WHERE owner=? AND lane=?",(owner,index)).fetchone()
        if row is None or row[0]+delta[0]>NODES_PER_LANE or row[1]+delta[1]>EDGES_PER_LANE:
            raise a.GraphHeld("lane quota reservation differs")
        totals[owner][0]+=delta[0];totals[owner][1]+=delta[1]
    for owner,total in totals.items():
        row=db.execute("SELECT nodes,edges,enabled FROM main.lead_owner WHERE owner=?",(owner,)).fetchone()
        pending=quota(db,owner)
        if row is None or not row[2]:raise a.GraphHeld("owner reservation unavailable")
        if row[0]+pending[0]+total[0]>MAX_NODES or row[1]+pending[1]+total[1]>MAX_EDGES:
            raise ReservationBusy("owner quota escrow exhausted")
    db.executemany("INSERT INTO main.structural_owner_lanes VALUES(?,?,?,?,?)",
                   [(owner,index,seq,*delta) for (owner,index),delta in sorted(lane_rows.items())])
    db.executemany("INSERT INTO main.structural_resource_locks VALUES(?,?,?,?)",
                   [(owner,kind,identity,seq) for owner,kind,identity in sorted(resources)])


def validate(db,plan):
    seq=plan["sequence"]
    actual={(r[0],r[1]):[r[2],r[3]] for r in db.execute(
        "SELECT owner,lane,nodes,edges FROM main.structural_owner_lanes WHERE sequence=?",(seq,))}
    resources={tuple(r) for r in db.execute(
        "SELECT owner,kind,identity FROM main.structural_resource_locks WHERE sequence=?",(seq,))}
    if actual!=lanes(plan) or resources!=keys(plan):raise a.GraphHeld("same-owner reservation witness differs")


def release(db,plan):
    validate(db,plan)
    seq=plan["sequence"]
    db.execute("DELETE FROM main.structural_owner_lanes WHERE sequence=?",(seq,))
    db.execute("DELETE FROM main.structural_resource_locks WHERE sequence=?",(seq,))


def verify(db):
    if enabled(db) and any(db.execute("SELECT 1 FROM main."+table+" LIMIT 1").fetchone()
                           for table in ("structural_owner_lanes","structural_resource_locks")):
        raise a.GraphHeld("orphan same-owner quota or resource lock")
