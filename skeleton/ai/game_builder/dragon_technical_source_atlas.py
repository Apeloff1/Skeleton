"""Dragon task-aware curated source atlas, backed by canonical almanacs.

Editorial link leads only. No network I/O, source rights, independence,
training or memory-promotion authority is granted by import or ranking.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import DragonAlmanacs, _auth
from .dragon_almanac_sequence import SequentialAlmanacWorker
from .dragon_source_catalog import canonical_source_url
from .dragon_technical_source_seeds import SEEDS
from .reviewed_knowledge import _integer

_ADJACENT = {
    "npc": ("ai", "agents", "testing", "dialogue"),
    "editor": ("accessibility", "serialization", "scripting", "testing"),
    "crawler": ("security", "rights", "research", "licensing"),
    "errors": ("debugging", "diagnostics", "testing", "compiler"),
    "retro": ("homebrew", "rom", "sprites", "audio"),
    "gameboy": ("homebrew", "rgbds", "rom", "sprites"),
    "physics": ("ecs", "performance", "testing", "timing"),
    "quest": ("dialogue", "narrative", "npc", "scenes"),
    "rendering": ("shader", "graphics", "performance", "accessibility"),
    "music": ("audio", "latency", "accessibility", "sound"),
    "release": ("shipping", "rights", "security", "packaging"),
    "ai": ("evaluation", "agents", "security", "training"),
    "game": ("engine", "design", "assets", "qa"),
    "level": ("editor", "tilemap", "narrative", "physics"),
    "rpg": ("narrative", "quest", "dialogue", "save"),
    "maze": ("pathfinding", "level", "editor", "physics"),
    "gameplay": ("physics", "ai", "animation", "qa"),
    "multiplayer": ("network", "replication", "matchmaking", "security"),
    "homebrew": ("console", "retro", "portability", "compiler"),
    "porting": ("runtime", "formats", "shipping", "performance"),
    "shader": ("graphics", "materials", "rendering", "gpu"),
    "performance": ("optimization", "profiling", "graphics", "physics"),
    "animation": ("rigging", "sprites", "assets", "skeletal"),
    "dialogue": ("narrative", "quest", "localization", "accessibility"),
    "testing": ("qa", "fuzzing", "profiling", "debugging"),
    "syntax": ("compiler", "coding", "debugging", "errors"),
    "license": ("rights", "compliance", "shipping", "assets"),
    "localization": ("translation", "unicode", "subtitles", "accessibility"),
    "pipeline": ("production", "assets", "formats", "build"),
    "console": ("homebrew", "shipping", "portability", "graphics"),
}
_DAYS = {"engine":14, "runtime":14, "graphics":30, "audio":60,
    "homebrew":90, "coding":14, "security":30, "ai":14, "research":30,
    "accessibility":90, "shipping":30, "rights":90,
    "physics":30, "network":14, "assets":30, "animation":30,
    "narrative":60, "qa":14, "optimization":14, "localization":60,
    "formats":60, "production":30}
_WORD = re.compile(r"[a-z0-9]+")
_ID = re.compile(r"source-[0-9a-f]{64}\Z")
_SLUG = re.compile(r"[a-z][a-z0-9-]{1,39}\Z")


def _curate():
    rows=[]; urls=set(); slugs=set()
    for slug,raw,family,words in SEEDS:
        url=canonical_source_url(raw)
        topics=tuple(words.split())
        if (urlsplit(url).scheme != "https" or not _SLUG.fullmatch(slug) or slug in slugs or url in urls
            or family not in _DAYS or not 1<=len(topics)<=16
            or any(not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}",word) for word in topics)):
            raise ValueError("invalid curated atlas seed")
        urls.add(url); slugs.add(slug)
        rows.append({"slug":slug,"url":url,"family":family,
            "topics":list(topics),"suggested_review_days":_DAYS[family],
            "availability":"not_checked","rights":"not_assessed",
            "independence":"not_assessed","crawler_authorized":False,
            "training_authorized":False})
    return tuple(sorted(rows,key=lambda s:s["slug"]))


CATALOG=_curate()
CATALOG_DIGEST=canonical_digest({"schema":"skeleton.dragon.technical_sources.v1",
                                 "sources":CATALOG})


class DragonTechnicalSources:
    """Owner-scoped editorial receipts and real canonical policy-stage jobs."""

    def __init__(self, almanacs: DragonAlmanacs):
        if not isinstance(almanacs,DragonAlmanacs):
            raise TypeError("canonical DragonAlmanacs required")
        self.a=almanacs; self.db=almanacs.db
        self.worker=SequentialAlmanacWorker(almanacs)
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_technical_source_events_v1(
            owner TEXT NOT NULL, source TEXT NOT NULL, revision INTEGER NOT NULL,
            body TEXT NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY(owner,source,revision))""")

    def _history(self,owner,sid):
        rows=self.db.execute("""SELECT revision,body,digest FROM
          dragon_technical_source_events_v1 WHERE owner=? AND source=?
          ORDER BY revision LIMIT 65""",(owner,sid)).fetchall()
        if len(rows)>64: raise ValueError("editorial history cap exceeded")
        result=[]; parent=None
        for i,(revision,raw,digest) in enumerate(rows):
            doc=json.loads(raw)
            if (revision!=i or not isinstance(doc,dict)
                or canonical_digest(doc)!=digest
                or doc.get("owner")!=owner or doc.get("source_id")!=sid
                or doc.get("revision")!=i or doc.get("parent_digest")!=parent
                or doc.get("crawler_authorized") is not False
                or doc.get("training_authorized") is not False):
                raise ValueError("editorial history integrity invalid")
            if result and doc["recorded_at"]<result[-1]["recorded_at"]:
                raise ValueError("editorial chronology invalid")
            result.append({**doc,"digest":digest});parent=digest
        return result

    def import_catalog(self,owner,*,authorized,recorded_at):
        _auth(owner,authorized)
        _integer(recorded_at,"editorial record timestamp",0,4_102_444_800)
        added=events=0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            for seed in CATALOG:
                url=seed["url"];sid="source-"+sha256(url.encode()).hexdigest()
                chain=self._history(owner,sid)
                old=self.db.execute("""SELECT body,digest FROM dragon_almanac_sources
                    WHERE owner=? AND source=?""",(owner,sid)).fetchone()
                if old:
                    saved=json.loads(old[0])
                    if (canonical_digest(saved)!=old[1] or
                        saved.get("url")!=url or saved.get("source_id")!=sid or
                        saved.get("training_authorized") is not False):
                        raise ValueError("existing source integrity invalid")
                else:
                    saved={"source_id":sid,"url":url,"host":urlsplit(url).hostname,
                        "kind":"web_candidate","discoveries":[],
                        "availability":"not_checked","rights":"not_assessed",
                        "independence":"not_assessed","training_authorized":False,
                        "provisional_discovery":True}
                    self.db.execute("INSERT INTO dragon_almanac_sources VALUES(?,?,?,?)",
                        (owner,sid,canonical_json(saved),canonical_digest(saved)))
                    added+=1
                topic=self.a.ensure_topic(owner,("Sources","Provisional",
                    "Technical atlas",seed["family"],seed["slug"]),authorized=True)
                while topic is not None:
                    self.db.execute("INSERT OR IGNORE INTO dragon_almanac_members VALUES(?,?,?)",
                                    (owner,topic,sid))
                    topic=self.db.execute("""SELECT parent FROM dragon_almanac_topics
                        WHERE owner=? AND topic=?""",(owner,topic)).fetchone()[0]
                if chain and chain[-1]["seed"]==seed: continue
                if chain and recorded_at<chain[-1]["recorded_at"]:
                    raise ValueError("editorial timestamp predates parent")
                if len(chain)>=64: raise ValueError("source history capacity reached")
                changed=sorted(k for k in seed if not chain or
                    chain[-1]["seed"].get(k)!=seed[k])
                doc={"schema":"skeleton.dragon.technical_source_event.v1",
                    "owner":owner,"source_id":sid,"revision":len(chain),
                    "parent_digest":chain[-1]["digest"] if chain else None,
                    "recorded_at":recorded_at,"catalog_digest":CATALOG_DIGEST,
                    "seed":seed,"improvements":
                        ["("+key+": metadata revised)" for key in changed] if chain
                        else ["(new candidate; no source content inspected)"],
                    "source_content_fetched":False,"page_freshness":"unknown",
                    "crawler_authorized":False,"training_authorized":False}
                self.db.execute("INSERT INTO dragon_technical_source_events_v1 VALUES(?,?,?,?,?)",
                    (owner,sid,len(chain),canonical_json(doc),canonical_digest(doc)))
                events+=1
            jobs=self.worker.seed(owner,authorized=True)
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"catalog_digest":CATALOG_DIGEST,"curated_leads":len(CATALOG),
            "new_source_metadata":added,"new_editorial_events":events,
            "new_policy_stage_jobs":jobs,"network_requests":0,
            "approved_knowledge_added":0,"crawler_authorized":False,
            "training_authorized":False}

    def plan(self,owner,query,*,authorized,limit=20,max_per_host=2,
             include_adjacent=True):
        _auth(owner,authorized)
        _integer(limit,"research limit",1,100)
        _integer(max_per_host,"host diversity cap",1,20)
        if (type(include_adjacent) is not bool or not isinstance(query,str)
            or not 2<=len(query)<=300 or
            any(ord(c)<32 or ord(c)==127 for c in query)):
            raise ValueError("bounded research question required")
        words=set(_WORD.findall(query.lower()))
        near=set()
        if include_adjacent:
            for word in words: near.update(_ADJACENT.get(word,()))
        candidates=[]
        for seed in CATALOG:
            sid="source-"+sha256(seed["url"].encode()).hexdigest()
            history=self._history(owner,sid)
            if not history: continue
            if history[-1]["seed"]!=seed:
                raise ValueError("updated editorial seed must be imported before planning")
            terms=set(seed["topics"])|{seed["family"]}
            direct=sorted(words & terms)
            adjacent=sorted((near & terms)-set(direct))
            if not direct and not adjacent: continue
            row=self.db.execute("""SELECT j.stage,j.state,j.input_digest,s.body,s.digest
                FROM dragon_almanac_jobs j JOIN dragon_almanac_sources s
                ON j.owner=s.owner AND j.source=s.source
                WHERE j.owner=? AND j.source=?""",(owner,sid)).fetchone()
            if row is None: raise ValueError("source not in canonical policy queue")
            stage,state,input_digest,raw,digest=row
            saved=json.loads(raw)
            if (canonical_digest(saved)!=digest or
                saved.get("url")!=seed["url"] or saved.get("source_id")!=sid):
                raise ValueError("source metadata integrity invalid")
            if stage==0 and digest!=input_digest:
                raise ValueError("stale source policy input")
            score=10*len(direct)+3*len(adjacent)
            candidates.append((-score,seed["url"],{"source_id":sid,
                "slug":seed["slug"],"url":seed["url"],
                "host":urlsplit(seed["url"]).hostname,"family":seed["family"],
                "score":score,"direct_topic_matches":direct,
                "adjacent_topic_matches":adjacent,
                "editorial_recorded_at":history[-1]["recorded_at"],
                "editorial_revision":history[-1]["revision"],
                "editorial_improvements":history[-1]["improvements"],
                "suggested_review_days":seed["suggested_review_days"],
                "page_last_fetched_at":None,"page_freshness":"unknown",
                "policy_stage":stage,"policy_state":state,
                "crawler_authorized":False,"training_authorized":False}))
        chosen=[];hosts=Counter();families=Counter()
        for _,_,item in sorted(candidates):
            if hosts[item["host"]]>=max_per_host: continue
            chosen.append(item);hosts[item["host"]]+=1
            families[item["family"]]+=1
            if len(chosen)>=limit: break
        return {"schema":"skeleton.dragon.technical_source_plan.v1",
            "owner":owner,"query":query,"catalog_digest":CATALOG_DIGEST,
            "candidate_matches":len(candidates),"selected":chosen,
            "families":dict(sorted(families.items())),
            "ranking_scope":"unreviewed_metadata_relevance_not_evidence",
            "queue_modified":False,"crawler_authorized":False,
            "training_authorized":False,"rights_review_required":True}

    def history(self,owner,source_id,*,authorized):
        _auth(owner,authorized)
        if not isinstance(source_id,str) or not _ID.fullmatch(source_id):
            raise ValueError("exact source ID required")
        return {"owner":owner,"source_id":source_id,
            "events":self._history(owner,source_id),"training_authorized":False}
