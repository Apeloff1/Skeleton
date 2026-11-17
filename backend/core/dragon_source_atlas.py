"""Current-grant source atlas and intelligent navigation suggestions.

The immutable registry contains possible entry points. The dynamic atlas
uses only owner-retained checkpoint witnesses. It does not persist new
copies of URLs, change grant lifetime, infer source rights, fetch resources
or produce dispatchable crawl manifests. Newly published checkpoints
automatically extend the atlas through the canonical navigation graph.
"""
from __future__ import annotations

from collections import Counter,defaultdict
import re
from urllib.parse import urlsplit

from core import dragon_navigation_graph as graph
from skeleton.ai.webcrawler.source_navigation import catalogue,rank_sources,objective,score_source,BRIDGES,discovery_profile
from skeleton.ai.webcrawler.navigation_semantics import digest,words,concepts

MAX_HOSTS=64
MAX_SAMPLES=12
MAX_GRAPH_POOL=96
MAX_PLAN=48
HOST=re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+\Z")


def _host(value):
    if not isinstance(value,str) or len(value)>253 or not HOST.fullmatch(value):
        raise ValueError("source host identity")
    return value


def _unit(n):return max(0.,min(1.,float(n)))


def _sample(db,owner,host,now):
    """At most 12 current due targets per host, with exact feedback witnesses."""
    rows=db.execute("""SELECT n.id,n.url,n.host FROM navigation_nodes n
        LEFT JOIN navigation_reviews r ON r.owner=n.owner AND r.target=n.id
        WHERE n.owner=? AND n.host=? AND """+graph._active_sql("n")+"""
        AND (r.state IS NULL OR (r.state='candidate' AND r.next_review<=?))
        ORDER BY n.id LIMIT ?""",(owner,host,now,now,MAX_SAMPLES+1)).fetchall()
    samples=[]
    for row in rows[:MAX_SAMPLES]:
        feedback=graph.outcomes(db,owner,row["id"],now=now)
        samples.append({**dict(row),"feedback":feedback})
    return samples,len(rows)>MAX_SAMPLES


def inventory(db,owner,*,now,after=None,limit=32):
    graph._integer(limit,1,MAX_HOSTS)
    lower="" if after is None else _host(after)
    # Host-keyset seeking uses the canonical (owner,host,id) index rather
    # than copying a second independent global URL table.
    rows=db.execute("""SELECT DISTINCT n.host FROM navigation_nodes n
        WHERE n.owner=? AND n.host>? AND """+graph._active_sql("n")+"""
        ORDER BY n.host LIMIT ?""",(owner,lower,now,limit+1)).fetchall()
    registry=catalogue();items=[]
    for row in rows[:limit]:
        host=row["host"]
        samples,truncated=_sample(db,owner,host,now)
        known=sorted({s.id for target in samples if (s:=registry.match(target["url"])) is not None})
        items.append({"host":host,"known_source_ids":known,"sample_targets":len(samples),
            "sample_truncated":truncated,"observed_phases":dict(sum((Counter(t["feedback"]["phases"]) for t in samples),Counter())),
            "captured_witnesses":sum(t["feedback"]["phases"].get("captured",0) for t in samples),
            "metadata_only":True,"network_authorized":False})
    result={"hosts":items,"next_cursor":rows[limit-1]["host"] if len(rows)>limit else None,
            "catalogue":registry.summary(),"sample_is_bounded":True,"global_completeness_claimed":False,
            "network_authorized":False}
    return {**result,"receipt":digest(result)}


def trace(db,owner,*,host,now,limit=24,after=None):
    """Cross-host bridge proposals from actual current graph lineage only."""
    host=_host(host);graph._integer(limit,1,48)
    if after is not None:graph._id(after)
    # The parent sample is explicitly bounded. This avoids walking the
    # complete adjacency list of a gigantic documentation or mod origin.
    samples,truncated=_sample(db,owner,host,now)
    neighbours={}
    for target in samples:
        page=graph.neighbors(db,owner,target["id"],direction="children",limit=24,now=now)
        truncated|=page["next_cursor"] is not None
        for row in page["neighbors"]:
            child=row["id"]
            if row["host"]==host or after is not None and child<=after:continue
            review=db.execute("SELECT state,next_review FROM navigation_reviews WHERE owner=? AND target=?",(owner,child)).fetchone()
            if review and (review["state"]!="candidate" or review["next_review"]>now):continue
            previous=neighbours.get(child)
            if previous is None:
                neighbours[child]={"target_id":child,"url":row["url"],"host":row["host"],
                    "parent_ids":[target["id"]],"network_authorized":False}
            elif len(previous["parent_ids"])<4:previous["parent_ids"].append(target["id"])
    ordered=sorted(neighbours.values(),key=lambda x:x["target_id"])
    result={"host":host,"targets":ordered[:limit],"parent_sample_count":len(samples),
        "next_cursor":ordered[limit-1]["target_id"] if len(ordered)>limit else None,
        "sample_truncated":truncated,"graph_complete":False,"network_authorized":False}
    return {**result,"receipt":digest(result)}


def _historical(feedback):
    # Rejected/restricted outcomes remain negative evidence rather than
    # an invitation to evade the underlying boundary.
    phases=feedback["phases"]
    bad=sum(phases.get(k,0) for k in ("rejected","restricted","error","retry"))
    captured=phases.get("captured",0);discovered=phases.get("discovered",0)
    count=captured+discovered+bad
    quality=(1+captured+.45*discovered)/(2+count)
    return _unit(quality),_unit(bad/max(1,count)),count


def plan(db,owner,*,query,now,limit=32,families=None,previous=None,mode="balanced"):
    graph._integer(limit,1,MAX_PLAN)
    if mode not in {"balanced","coverage","exploration","conservation"}:
        raise ValueError("source navigation mode")
    previous=[] if previous is None else previous
    if not isinstance(previous,list) or len(previous)>512 or any(not isinstance(x,str) for x in previous) or len(set(previous))!=len(previous):
        raise ValueError("source prior selection bounds")
    old={graph._id(x) for x in previous}
    task=objective(query);registry=catalogue()
    root_plan=rank_sources(query,limit=64,families=families,previous=previous,registry=registry)
    candidates={}
    # Curated roots are explicitly unobserved by this plan. Their source
    # identity is separate from the SHA-256 of an admitted graph URL.
    for root in root_plan["sources"]:
        sid=root["source_id"]
        candidates[sid]={**root,"candidate_id":sid,"origin":"registry",
            "target_id":None,"historical_quality":.5,"restriction_rate":0.,
            "witness_count":0,"lineage_support":0.,"observed":False}
    page=graph.retrieve(db,owner,query=query,now=now,limit=48,per_term=32,
                        due_only=True,exploration_epoch=now//3600)
    for row in page["targets"]:
        if row["id"] in old:continue
        source=registry.match(row["url"])
        if families is not None and (source is None or source.family not in families):continue
        feedback=graph.outcomes(db,owner,row["id"],now=now)
        quality,bad,count=_historical(feedback)
        parent=graph.neighbors(db,owner,row["id"],direction="parents",limit=4,now=now)
        hint=score_source(source,task)[0] if source else row["score"]
        base=.72*row["score"]+.28*hint
        # A known source's curated name is never a substitute for actual
        # checkpoint lineage or independent evidence.
        candidates[row["id"]]={"candidate_id":row["id"],"source_id":source.id if source else None,
            "target_id":row["id"],"url":row["url"],"host":row["host"],
            "name":source.name if source else row["host"],"family":source.family if source else "discovered",
            "kind":source.kind if source else "observed_locator","ecosystems":sorted(source.ecosystems) if source else [],
            "relevance":_unit(base),"historical_quality":quality,"restriction_rate":bad,
            "witness_count":feedback["witnesses"],"lineage_support":len(parent["neighbors"])/4,
            "observed":True,"origin":"retained_graph","network_authorized":False,
            "access_verified":False,"rights_verified":False}
    if len(candidates)>MAX_GRAPH_POOL+64:raise ValueError("source plan candidate bound")
    weights={"balanced":(.60,.20,.20),"coverage":(.75,.15,.10),
             "exploration":(.43,.12,.45),"conservation":(.58,.37,.05)}[mode]
    chosen=[];hosts=Counter();families_used=Counter();kinds=Counter();urls=set()
    while candidates and len(chosen)<limit:
        ranked=[]
        for key,row in candidates.items():
            if row["url"] in urls:continue
            diversity=(.45/(1+hosts[row["host"]])+.30/(1+families_used[row["family"]])
                       +.25/(1+kinds[row["kind"]]))
            relevance=row["relevance"]
            # Select a combination of objective fit, witnessed outcome
            # history, and unexplored complementary ecosystems.
            jeeves=.72*relevance+.18*row["historical_quality"]+.10*row["lineage_support"]
            dragon=.55*diversity+.30/(1+row["witness_count"])+.15*relevance
            priority=_unit(weights[0]*jeeves+weights[1]*row["historical_quality"]+weights[2]*dragon
                           -.25*row["restriction_rate"])
            ranked.append((-round(priority,10),key,jeeves,dragon))
        if not ranked:break
        neg,key,jeeves,dragon=min(ranked)
        row=candidates.pop(key)
        urls.add(row["url"]);hosts[row["host"]]+=1;families_used[row["family"]]+=1;kinds[row["kind"]]+=1
        root=registry.by_id.get(row["source_id"])
        strategy={"directory":"catalogue_index","community":"version_and_dependency_metadata",
            "reference":"taxonomy_and_citations","documentation":"versioned_navigation_tree",
            "asset_catalogue":"license_and_item_metadata","dataset":"manifest_schema_and_release_metadata",
            "connector_docs":"documented_endpoint_and_auth_review","observed_locator":"witnessed_hyperlinks"}[row["kind"]]
        chosen.append({**row,"priority":-neg,"jeeves":round(jeeves,8),"dragon":round(dragon,8),
            "navigation_strategy":strategy,"bridge_families":list(BRIDGES[root.family]) if root else [],
            "navigation_profile":discovery_profile(row["url"],task,registry),
            "permission_required":True,"network_authorized":False})
    result={"schema":"skeleton.dragon.source-navigation-plan.v1","catalogue":registry.summary(),
        "sources":chosen,"ecosystems":root_plan["ecosystems"],"goals":root_plan["goals"],
        "distinct_hosts":len(hosts),"mode":mode,"retained_graph_candidates":len(page["targets"]),
        "index_backfill_pending":page["index_backfill_pending"],"lane_truncated":page["lane_truncated"],
        "selection_is_advisory":True,"model_inference_executed":False,"network_authorized":False,
        "source_rights_granted":False}
    return {**result,"receipt":digest(result)}
