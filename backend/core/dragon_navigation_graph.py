"""Grant-scoped discovery topology and scalable semantic candidate lanes.

The federation remains metadata-only. Every edge is witnessed by a real
retained checkpoint; every query checks current grants at read time. The
indexed lane is incrementally populated by the same publication transaction,
not by an independent eventually-consistent crawler.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from skeleton.ai.webcrawler.navigation_semantics import (
    words, concepts, CONCEPTS, semantic_features,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS navigation_edges(
 owner TEXT NOT NULL, grant_id TEXT NOT NULL, parent TEXT NOT NULL,
 child TEXT NOT NULL, relation TEXT NOT NULL,
 PRIMARY KEY(owner,grant_id,parent,child,relation),
 FOREIGN KEY(owner,grant_id,parent) REFERENCES navigation_witnesses(owner,grant_id,target) ON DELETE CASCADE,
 FOREIGN KEY(owner,grant_id,child) REFERENCES navigation_witnesses(owner,grant_id,target) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS navigation_edges_parent ON navigation_edges(owner,parent,child,grant_id);
CREATE INDEX IF NOT EXISTS navigation_edges_child ON navigation_edges(owner,child,parent,grant_id);
CREATE TABLE IF NOT EXISTS navigation_postings(
 owner TEXT NOT NULL, term TEXT NOT NULL, target TEXT NOT NULL,
 PRIMARY KEY(owner,term,target),
 FOREIGN KEY(owner,target) REFERENCES navigation_nodes(owner,id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS navigation_postings_target ON navigation_postings(owner,target,term);
CREATE TABLE IF NOT EXISTS navigation_indexed(
 owner TEXT NOT NULL, target TEXT NOT NULL, revision TEXT NOT NULL,
 PRIMARY KEY(owner,target),
 FOREIGN KEY(owner,target) REFERENCES navigation_nodes(owner,id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS navigation_outcomes(
 owner TEXT NOT NULL, grant_id TEXT NOT NULL, target TEXT NOT NULL,
 phase TEXT NOT NULL CHECK(phase IN ('captured','duplicate','discovered','rejected','retry','error',
 'restricted','visited_unclassified','pending','observed')),
 observed_at INTEGER NOT NULL,
 PRIMARY KEY(owner,grant_id,target),
 FOREIGN KEY(owner,grant_id,target) REFERENCES navigation_witnesses(owner,grant_id,target) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS navigation_outcomes_target ON navigation_outcomes(owner,target,grant_id);
CREATE TABLE IF NOT EXISTS navigation_reviews(
 owner TEXT NOT NULL,target TEXT NOT NULL,revision INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('candidate','held','retired')),
 next_review INTEGER NOT NULL,reason TEXT NOT NULL,
 PRIMARY KEY(owner,target),
 FOREIGN KEY(owner,target) REFERENCES navigation_nodes(owner,id) ON DELETE CASCADE
) WITHOUT ROWID;
"""
HEX = re.compile(r"[a-f0-9]{64}\Z")
MAX_PAGE = 100
MAX_TERMS = 96
MAX_BEAM = 48
MAX_STEPS = 6


def _id(value):
    if not isinstance(value,str) or not HEX.fullmatch(value):
        raise ValueError("invalid navigation graph identity")
    return value


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _integer(value,low,high):
    if type(value) is not int or not low<=value<=high:
        raise ValueError("navigation graph bound")
    return value


INDEX_REVISION = _digest([CONCEPTS, MAX_TERMS, 'trigram-v1'])


def term_keys(text):
    tokens=set(words(text))
    keys={"w:"+t for t in tokens}
    keys.update("c:"+str(i) for i in concepts(tokens))
    # Character shingles form a bounded typo-tolerant retrieval lane.
    keys.update("g:"+t[i:i+3] for t in tokens for i in range(max(0,len(t)-2)))
    # Exact and concept keys have priority. Hash ordering makes selection
    # stable without favoring the alphabetically earliest trigrams.
    exact=sorted(k for k in keys if not k.startswith("g:"))
    grams=sorted((k for k in keys if k.startswith("g:")),key=_digest)
    return tuple((exact+grams)[:MAX_TERMS])


def index_node(db,owner,target,url):
    prior=db.execute("SELECT revision FROM navigation_indexed WHERE owner=? AND target=?",
                  (owner,target)).fetchone()
    if prior and prior["revision"]==INDEX_REVISION:
        return
    if prior:
        db.execute("DELETE FROM navigation_postings WHERE owner=? AND target=?",(owner,target))
    parsed=urlsplit(url)
    db.executemany("INSERT OR IGNORE INTO navigation_postings VALUES(?,?,?)",
        ((owner,key,target) for key in term_keys(parsed.hostname+" "+parsed.path)))
    db.execute("INSERT INTO navigation_indexed VALUES(?,?,?) ON CONFLICT(owner,target) "
               "DO UPDATE SET revision=excluded.revision",(owner,target,INDEX_REVISION))


def publish_edges(db,owner,grant,rows):
    identities={url:identifier for identifier,url,_ in rows}
    count=0
    for child,url,row in rows:
        # The checkpoint has one primary relation but does not bind every
        # secondary relation to a specific parent. Only the primary pair
        # can be asserted as typed provenance; other parents are generic.
        parent=row["parent_url"]
        for source in set(row["parents"]) | ({parent} if parent else set()):
            if source not in identities or identities[source]==child:
                continue
            relation=row["kind"] if source==parent else "observed_parent"
            result=db.execute("INSERT OR IGNORE INTO navigation_edges VALUES(?,?,?,?,?)",
                              (owner,grant,identities[source],child,relation))
            count+=result.rowcount
    return count


def reindex(db,owner,*,after=None,limit=100):
    """Explicit lazy migration; never implies old topology can be recreated."""
    _integer(limit,1,MAX_PAGE)
    lower="" if after is None else _id(after)
    rows=db.execute("""SELECT n.id,n.url FROM navigation_nodes n
        WHERE n.owner=? AND n.id>? AND NOT EXISTS(
        SELECT 1 FROM navigation_indexed i WHERE i.owner=n.owner AND i.target=n.id AND i.revision=?)
        ORDER BY n.id LIMIT ?""",(owner,lower,INDEX_REVISION,limit+1)).fetchall()
    for row in rows[:limit]:
        index_node(db,owner,row["id"],row["url"])
    return {"indexed":min(len(rows),limit),"next_cursor":rows[limit-1]["id"]
        if len(rows)>limit else None,"network_authorized":False,
        "historical_edge_backfill_verified":False}


def _active_sql(alias):
    # Alias is internal, never a caller-controlled identifier.
    return ("EXISTS (SELECT 1 FROM navigation_witnesses w JOIN navigation_grants g "
            "ON g.owner=w.owner AND g.grant_id=w.grant_id WHERE w.owner="+alias+".owner "
            "AND w.target="+alias+".id AND g.state='active' AND g.expires>?)")


def neighbors(db,owner,target,*,direction="children",after=None,limit=32,now):
    _id(target);_integer(limit,1,MAX_PAGE)
    if direction not in {"children","parents"}:
        raise ValueError("invalid navigation edge direction")
    left,right=("parent","child") if direction=="children" else ("child","parent")
    lower="" if after is None else _id(after)
    sql=f"""SELECT e.{right} AS id,n.url,n.host,MIN(e.relation) AS relation,
       COUNT(DISTINCT e.grant_id) AS supporting_grants
       FROM navigation_edges e JOIN navigation_grants g
       ON g.owner=e.owner AND g.grant_id=e.grant_id
       JOIN navigation_nodes n ON n.owner=e.owner AND n.id=e.{right}
       WHERE e.owner=? AND e.{left}=? AND e.{right}>?
       AND g.state='active' AND g.expires>?
       GROUP BY e.{right},n.url,n.host ORDER BY e.{right} LIMIT ?"""
    rows=db.execute(sql,(owner,target,lower,now,limit+1)).fetchall()
    return {"neighbors":[{**dict(row),"network_authorized":False} for row in rows[:limit]],
            "next_cursor":rows[limit-1]["id"] if len(rows)>limit else None,
            "network_authorized":False,"historical_topology_complete":False}


def retrieve(db,owner,*,query,now,host=None,limit=48,per_term=32,due_only=False):
    """Multi-lane indexed candidate pool; bounded, not exhaustive search.

    This performs at most MAX_TERMS indexed seeks, each returning a
    bounded number. No full-catalogue scan or dynamic SQL identifier.
    An omitted index or tail is explicitly reported as incomplete.
    """
    _integer(limit,1,MAX_BEAM);_integer(per_term,1,64)
    if type(due_only) is not bool:
        raise ValueError("navigation due filter")
    if host is not None and (not isinstance(host,str) or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+",host)):
        raise ValueError("invalid navigation host")
    if not isinstance(query,str) or not query.strip() or len(query)>512:
        raise ValueError("navigation graph query")
    keys=term_keys(query)
    votes=Counter();truncated=False
    for key in keys:
        sql=("SELECT p.target FROM navigation_postings p JOIN navigation_nodes n "
             "ON n.owner=p.owner AND n.id=p.target LEFT JOIN navigation_reviews r "
             "ON r.owner=n.owner AND r.target=n.id WHERE p.owner=? AND p.term=? "
             "AND "+_active_sql("n")+" AND (r.state IS NULL OR r.state='candidate')")
        args=[owner,key,now]
        if host is not None:
            sql+=" AND n.host=?";args.append(host)
        if due_only:
            sql+=" AND (r.next_review IS NULL OR r.next_review<=?)";args.append(now)
        sql+=" ORDER BY p.target LIMIT ?";args.append(per_term+1)
        rows=db.execute(sql,args).fetchall()
        truncated|=len(rows)>per_term
        weight=4 if key.startswith("w:") else 3 if key.startswith("c:") else 1
        for row in rows[:per_term]:
            votes[row["target"]]+=weight
    # Bound the second stage before reading full target metadata.
    candidates=[]
    for identifier,vote in sorted(votes.items(),key=lambda p:(-p[1],p[0]))[:limit*2]:
        row=db.execute("SELECT id,url,host FROM navigation_nodes WHERE owner=? AND id=?",
                       (owner,identifier)).fetchone()
        if row is None:
            continue
        feature=semantic_features(query,row["url"])
        candidates.append({**dict(row),"features":feature,"votes":vote,
            "score":round(.85*feature["score"]+.15*vote/max(1, max(votes.values())),8)})
    candidates.sort(key=lambda x:(-x["score"],x["id"]))
    # New and backfilled targets share the same index. This query uses
    # the owner/id row key and exits at the first missing index witness.
    incomplete=db.execute("""SELECT 1 FROM navigation_nodes n WHERE n.owner=?
        AND NOT EXISTS(SELECT 1 FROM navigation_indexed i
        WHERE i.owner=n.owner AND i.target=n.id AND i.revision=?) LIMIT 1""",(owner,INDEX_REVISION)).fetchone() is not None
    return {"targets":candidates[:limit],"index_backfill_pending":incomplete,
        "lane_truncated":truncated or len(votes)>limit,"network_authorized":False,
        "exhaustive":False}


def portfolio(db,owner,*,query,now,limit=12):
    """Jeeves objective coverage + Dragon diversity/lineage exploration.

    Greedy maximal marginal relevance balances semantic coverage, host
    diversity, novel concepts and corroborated paths. Each selected target
    remains an unreviewed candidate, never a dispatch instruction.
    """
    _integer(limit,1,24)
    pool=retrieve(db,owner,query=query,now=now,limit=MAX_BEAM)
    remaining=pool["targets"][:]
    # Cache current witnessed lineage and outcomes once per bounded candidate.
    context={}
    for row in remaining:
        support=neighbors(db,owner,row["id"],direction="parents",limit=2,now=now)
        feedback=outcomes(db,owner,row["id"],now=now)
        context[row["id"]]=(min(1.,len(support["neighbors"])/2),feedback)
    selected=[];hosts=Counter();covered=set();known_terms=set(words(query))
    while remaining and len(selected)<limit:
        scored=[]
        for candidate in remaining:
            terms=set(words(urlsplit(candidate["url"]).path))
            tags=concepts(terms)
            fresh=len(tags-covered)/max(1,len(tags))
            redundancy=max((len(terms & earlier["_terms"])/max(1,len(terms | earlier["_terms"]))
                            for earlier in selected),default=0.)
            # Use real current graph support, not a source's asserted authority.
            topology,feedback=context[candidate["id"]]
            jeeves=.72*candidate["score"]+.18*len(known_terms & terms)/max(1,len(known_terms))+.10*feedback["yield_prior"]
            dragon=.35*fresh+.30/(1+hosts[candidate["host"]])+.20*topology+.15*feedback["exploration_prior"]
            score=.60*jeeves+.40*dragon-.20*redundancy
            scored.append((score,candidate["id"],candidate,terms,tags,jeeves,dragon,topology))
        score,_,candidate,terms,tags,jeeves,dragon,topology=min(scored,key=lambda x:(-x[0],x[1]))
        remaining.remove(candidate);hosts[candidate["host"]]+=1;covered.update(tags)
        selected.append({**candidate,"_terms":terms,"jeeves":round(jeeves,8),
            "dragon":round(dragon,8),"joint":round(score,8),"lineage_support":topology,
            "historical_feedback":context[candidate["id"]][1],
            "network_authorized":False,"reviewed":False})
    for row in selected:row.pop("_terms")
    return {"targets":selected,"distinct_hosts":len(hosts),"covered_concepts":len(covered),
        "index_backfill_pending":pool["index_backfill_pending"],
        "lane_truncated":pool["lane_truncated"],"network_authorized":False,
        "selection_is_advisory":True,"receipt":_digest([query,now,selected])}


def review(db,owner,target,*,state,reason,expected_revision,next_review,now):
    _id(target)
    if state not in {"candidate","held","retired"}:
        raise ValueError("navigation review state")
    if not isinstance(reason,str) or not 1<=len(reason)<=256 or any(ord(c)<32 for c in reason):
        raise ValueError("navigation review reason")
    _integer(expected_revision,0,2**63-2)
    _integer(next_review,now,now+3650*86400)
    if not db.execute("SELECT 1 FROM navigation_nodes n WHERE n.owner=? AND n.id=? AND "
                      +_active_sql("n"),(owner,target,now)).fetchone():
        raise LookupError("current target unavailable")
    prior=db.execute("SELECT revision FROM navigation_reviews WHERE owner=? AND target=?",
                     (owner,target)).fetchone()
    revision=prior["revision"] if prior else 0
    if revision!=expected_revision:
        raise ValueError("navigation review revision changed")
    db.execute("""INSERT INTO navigation_reviews VALUES(?,?,?,?,?,?)
        ON CONFLICT(owner,target) DO UPDATE SET revision=excluded.revision,
        state=excluded.state,next_review=excluded.next_review,reason=excluded.reason""",
        (owner,target,revision+1,state,next_review,reason))
    return {"target":target,"revision":revision+1,"state":state,
            "next_review":next_review,"network_authorized":False}


_EVENT_PHASES={"captured":"captured","duplicate":"duplicate","discovered":"discovered",
               "rejected":"rejected","retry":"retry","error":"error",
               "source_rights_restricted":"restricted"}


def publish_outcomes(db,owner,grant,rows,snapshot):
    """Persist only bounded outcome categories; never copy titles or bodies.

    Seen means visited/settled, not successful capture. Exact captured URLs
    are joined against the canonical source registry; recent event history
    is a partial observation, not an invented lifetime success rate.
    """
    captured={}
    for source in snapshot["sources"].values():
        for key in ("canonical_url","fetched_url"):
            captured[source[key]]=int(source["fetched_at"])
    seen=set(snapshot["seen"])
    events={}
    for event in snapshot["events"]:
        if event["kind"] in _EVENT_PHASES and isinstance(event.get("url"),str):
            events[event["url"]]=(_EVENT_PHASES[event["kind"]],int(event["at"]))
    for identifier,url,row in rows:
        if url in captured:
            phase,at="captured",captured[url]
        elif url in events:
            phase,at=events[url]
        elif url in seen:
            phase,at="visited_unclassified",0
        else:
            phase,at=("pending" if row["pending"] else "observed"),0
        db.execute("INSERT INTO navigation_outcomes VALUES(?,?,?,?,?)",
                   (owner,grant,identifier,phase,at))


def outcomes(db,owner,target,*,now):
    # Keep at most 256 independent grant witnesses per advisory computation.
    rows=db.execute("""SELECT o.phase,o.observed_at FROM navigation_outcomes o
        JOIN navigation_grants g ON g.owner=o.owner AND g.grant_id=o.grant_id
        WHERE o.owner=? AND o.target=? AND g.state='active' AND g.expires>?
        ORDER BY o.grant_id LIMIT 257""",(owner,target,now)).fetchall()
    phases=Counter(row["phase"] for row in rows[:256])
    settled=sum(phases[k] for k in ("captured","duplicate","discovered","rejected","retry","error","restricted"))
    successful=phases["captured"]+phases["discovered"]
    # Conservative shrinkage: unknown observations never become successes.
    yield_prior=(1+successful)/(2+settled)
    latest=max((row["observed_at"] for row in rows[:256]),default=0)
    overdue=1. if latest==0 else min(1.,max(0.,now-latest)/(30*86400))
    exploration=.65/(1+settled)+.35*overdue
    return {"witnesses":min(len(rows),256),"phases":dict(phases),
        "outcome_window_truncated":len(rows)>256,"yield_prior":round(yield_prior,8),
        "exploration_prior":round(exploration,8),"last_observed_at":latest,
        "historical_success_is_not_future_permission":True}


def trail(db,owner,*,root,query,now,depth=3,beam=24):
    """Bounded cycle-safe directed multi-hop browsing proposals.

    Each returned edge was witnessed under an active retained grant. The
    graph is not a crawler and cannot walk the live web.
    """
    _id(root);_integer(depth,1,MAX_STEPS);_integer(beam,1,MAX_BEAM)
    if not isinstance(query,str) or not query.strip() or len(query)>512:
        raise ValueError("navigation trail objective")
    if not db.execute("SELECT 1 FROM navigation_nodes n WHERE n.owner=? AND n.id=? AND "
                      +_active_sql("n"),(owner,root,now)).fetchone():
        raise LookupError("active root unavailable")
    visited={root};frontier=[(root,[root])];result=[];truncated=False
    for level in range(1,depth+1):
        candidates={}
        for parent,path in frontier:
            page=neighbors(db,owner,parent,now=now,limit=min(beam,24))
            truncated|=page["next_cursor"] is not None
            for row in page["neighbors"]:
                target=row["id"]
                if target in visited:continue
                score=semantic_features(query,row["url"])["score"]
                proposal={**row,"path":[*path,target],"depth":level,
                    "score":round(.85*score+.15/(1+level),8),"network_authorized":False}
                prior=candidates.get(target)
                if prior is None or (-proposal["score"],proposal["path"])<(-prior["score"],prior["path"]):
                    candidates[target]=proposal
        slots=beam-len(result)
        ordered=sorted(candidates.values(),key=lambda x:(-x["score"],x["id"]))
        truncated|=len(ordered)>slots
        chosen=ordered[:slots]
        result.extend(chosen);visited.update(row["id"] for row in chosen)
        frontier=[(row["id"],row["path"]) for row in chosen]
        if not frontier or len(result)>=beam:
            break
    return {"root":root,"targets":result,"max_depth":depth,"beam":beam,
        "truncated":truncated or len(result)>=beam,"network_authorized":False,
        "historical_topology_complete":False}
