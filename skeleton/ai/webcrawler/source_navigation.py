"""Source-aware navigation over a curated, non-authorizing registry.

Source roots are candidate metadata, not a whitelist or a claim of
availability, license, trust, robots compliance or acquisition rights.
Only existing admitted frontier entries may receive a scheduling signal.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from heapq import nsmallest
from pathlib import Path
import json
import ipaddress
import math
import os
import re
from urllib.parse import urlsplit,unquote

from .navigation_semantics import words,concepts,grams,digest

FAMILIES={"game-discovery","mods","mmo","game-worlds","engine-tools",
          "open-assets","datasets","apis","history-media","global"}
KINDS={"directory","community","reference","documentation","asset_catalogue","dataset","connector_docs"}
MAX_REGISTRY=65536
MAX_BYTES=32*1024*1024
MAX_RANK_POOL=384
MAX_ROOTS=64
HOST=re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+\Z")
REGISTRY_PATH=Path(__file__).with_name("catalogues")/"dragon_source_catalogue.v1.json"
SCHEMA="skeleton.dragon.source-catalogue.v1"
# Explicit bridges describe useful complementary investigations, not
# asserted links or shared publishers. Never synthesize source URLs.
BRIDGES={
 "game-discovery":("game-worlds","mods","history-media","global","apis"),
 "mods":("game-worlds","engine-tools","apis","open-assets","game-discovery"),
 "mmo":("apis","datasets","game-worlds","mods","global"),
 "game-worlds":("mods","mmo","history-media","game-discovery","global"),
 "engine-tools":("open-assets","apis","datasets","mods"),
 "open-assets":("engine-tools","datasets","apis"),
 "datasets":("apis","engine-tools","history-media","mmo"),
 "apis":("datasets","mods","mmo","engine-tools"),
 "history-media":("game-worlds","datasets","game-discovery","global"),
 "global":("game-discovery","game-worlds","mmo","history-media"),
}
ECOSYSTEMS={
 "eve":("eve online","eveonline","eve university","eve ref","dotlan","zkillboard","eve workbench","eve forums","eve sde","eve esi","eve developer"),
 "warcraft":("world of warcraft","wowhead","warcraft","raider io","icy veins","method","battle net"),
 "final-fantasy":("ffxiv","final fantasy","xivapi","universalis","garland tools","ff logs"),
 "minecraft":("minecraft","modrinth","curseforge","fabric","forge","neoforge","paper","spigot","bukkit"),
 "grand-theft-auto":("grand theft auto","gta","rockstar","fivem","cfx","openiv"),
 "elder-scrolls":("elder scrolls","uesp","bethesda","skse","xedit","loot","wabbajack","mod organizer"),
 "fallout":("fallout","bethesda","f4se","xedit","loot","mod organizer"),
 "nintendo":("nintendo","mario","mariowiki","zelda","zeldawiki","pokemon","bulbapedia","serebii","smash","nesdev","snes","n64brew"),
 "guild-wars":("guild wars","gw2"),
 "runescape":("runescape","osrs","runelite"),
 "path-of-exile":("path of exile","poe"),
 "destiny":("destiny","bungie","light gg"),
 "factorio":("factorio",),
 "stardew":("stardew","smapi"),
 "terraria":("terraria","tmodloader"),
 "rimworld":("rimworld",),
 "dota":("dota","opendota"),
 "league":("league of legends","riot","valorant"),
 "unreal":("unreal","fortnite","epic"),
 "godot":("godot",),
 "unity":("unity","bepinex","melonloader"),
}
GOALS={
 "mechanics":("mechanics combat quests builds skills progression stats",("reference","documentation","dataset")),
 "modding":("mods modding plugins addons dependencies compatibility map tools",("community","documentation","connector_docs")),
 "implementation":("engine sdk code scripting rendering animation physics development",("documentation","connector_docs","dataset")),
 "assets":("asset textures sprites art audio models animation materials license",("asset_catalogue","documentation","dataset")),
 "historical":("history archive preservation historical old retro manuals emulation version",("reference","dataset","directory")),
 "datasets":("data dataset dumps export api schema benchmark corpus",("dataset","connector_docs","documentation")),
 "discovery":("games catalogue catalog discovery releases platforms reviews",("directory","reference","community")),
}
FRESHNESS={"directory":7,"community":14,"reference":30,"documentation":30,"asset_catalogue":60,"dataset":30,"connector_docs":14}


def _norm(value):return " ".join(re.findall(r"[a-z0-9]+",value.casefold()))


def _contains(haystack,needle):
    return bool(needle) and (" "+needle+" ") in (" "+haystack+" ")


@lru_cache(maxsize=1)
def _normalized_ecosystems():
    return {key:tuple(_norm(alias) for alias in aliases) for key,aliases in ECOSYSTEMS.items()}


def ecosystem_tags(value):
    normalized=_norm(value)
    haystack=" "+normalized+" "
    return frozenset(key for key,aliases in _normalized_ecosystems().items()
                     if any(" "+alias+" " in haystack for alias in aliases))


# Explicit lexical aliases for compound publisher brands. A literal
# "mariowiki" token formerly disappeared from "Super Mario Nintendo"
# searches at tenfold density. Do not split or guess unrelated brands.
COMPOUND_NAMES={
    "mariowiki":("super","mario","wiki","nintendo"),
    "zeldawiki":("zelda","wiki","nintendo"),
    "warcraftlogs":("warcraft","logs","world"),
    "wowhead":("warcraft","wow"),
    "eveonline":("eve","online"),
    "steamdb":("steam","database"),
    "pcgamingwiki":("pc","gaming","wiki"),
    "n64brew":("nintendo","n64","development"),
}


def source_identity_terms(record,host,path):
    identity=set(words(record["name"]+" "+host+" "+path))
    for term in tuple(identity):
        identity.update(COMPOUND_NAMES.get(term,()))
    return frozenset(identity)


def _root(url):
    if not isinstance(url,str) or not 1<=len(url)<=512 or any(ord(c)<33 or ord(c)>126 for c in url):
        raise ValueError("source root bound")
    p=urlsplit(url)
    if (p.scheme!="https" or not p.hostname or not HOST.fullmatch(p.hostname)
            or p.netloc!=p.hostname or p.query or p.fragment or "\\" in p.path
            or any(part in (".","..") for part in unquote(p.path).split("/"))):
        raise ValueError("source root must be inert public HTTPS metadata")
    try:ipaddress.ip_address(p.hostname)
    except ValueError:pass
    else:raise ValueError("source root cannot be an IP literal")
    if p.hostname.endswith((".local",".localhost",".internal",".onion",".invalid",".test",".example")):
        raise ValueError("source root cannot be a reserved hostname")
    return p.hostname,p.path.rstrip("/") or "/"


@dataclass(frozen=True)
class Source:
    id:str
    name:str
    url:str
    host:str
    path:str
    family:str
    kind:str
    tags:frozenset
    identity_terms:frozenset
    ecosystems:frozenset
    concepts:frozenset
    grams:frozenset

    def public(self):
        return {"source_id":self.id,"name":self.name,"url":self.url,"host":self.host,
                "family":self.family,"kind":self.kind,"ecosystems":sorted(self.ecosystems),
                "suggested_review_days":FRESHNESS[self.kind],
                "access_verified":False,"rights_verified":False,"network_authorized":False}


def source_record(record):
    """Construct canonical source identity without loading a full registry."""
    if (not isinstance(record,dict) or set(record)!={"name","url","family","kind","tags"}
            or not isinstance(record["family"],str) or record["family"] not in FAMILIES
            or not isinstance(record["kind"],str) or record["kind"] not in KINDS
            or not isinstance(record["name"],str) or not 1<=len(record["name"])<=100
            or not isinstance(record["tags"],str) or not 1<=len(record["tags"])<=256):
        raise ValueError("source registry row")
    host,path=_root(record["url"])
    identity=source_identity_terms(record,host,path)
    tags=frozenset(words(record["tags"]))|identity
    ecosystems=ecosystem_tags(record["name"]+" "+host+" "+path)
    return Source(digest(["dragon-source-root",host,path]),record["name"],record["url"],host,path,
                  record["family"],record["kind"],tags,identity,ecosystems,
                  frozenset(concepts(tags)),frozenset(grams(identity)))


class Catalogue:
    def __init__(self,raw):
        if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_BYTES:raise ValueError("source registry bytes")
        data=json.loads(raw)
        if (not isinstance(data,dict) or set(data)!={"schema","revision","status","sources"}
                or data["schema"]!=SCHEMA or data["status"]!="candidate_registry_not_access_verified"
                or not isinstance(data["revision"],str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",data["revision"])
                or not isinstance(data["sources"],list) or not 1<=len(data["sources"])<=MAX_REGISTRY):
            raise ValueError("source registry schema")
        roots={};by_host={};rows=[]
        for record in data["sources"]:
            row=source_record(record)
            host,path=row.host,row.path;key=(host,path)
            if key in roots:raise ValueError("duplicate source root")
            roots[key]=row;by_host.setdefault(host,[]).append(row);rows.append(row)
        self.rows=tuple(sorted(rows,key=lambda x:x.id));self.revision=data["revision"]
        self.digest=digest(data);self._hosts={key:tuple(sorted(value,key=lambda x:-len(x.path))) for key,value in by_host.items()}
        self.by_id={x.id:x for x in self.rows}
        self._roots=roots
        self._families=dict(sorted(Counter(r.family for r in self.rows).items()))

    def match(self,url):
        try:p=urlsplit(url)
        except ValueError:return None
        if p.scheme!="https" or p.username or p.password or p.hostname not in self._hosts:
            return None
        try:
            if p.port not in (None,443):return None
        except ValueError:return None
        path=p.path.rstrip("/") or "/"
        # Longest path-prefix match in O(path depth), not O(host roots).
        # Preserve the exact slash boundary; never infer ownership from suffixes.
        while path!="/":
            source=self._roots.get((p.hostname,path))
            if source is not None:
                return source
            path=path.rpartition("/")[0] or "/"
        return self._roots.get((p.hostname,"/"))

    def summary(self):
        return {"schema":SCHEMA,"revision":self.revision,"catalogue_digest":self.digest,
                "sources":len(self.rows),"hosts":len(self._hosts),
                "families":dict(self._families),
                "candidate_only":True,"network_authorized":False}


INDEX_ENV="SKL_DRAGON_SOURCE_INDEX_MANIFEST"


def catalogue_binding():
    """Read the operator-selected generation pin, not a new source grant."""
    configured=os.environ.get(INDEX_ENV)
    if configured is None:
        return None
    if not configured.strip():
        raise ValueError("empty source index manifest path")
    from .source_catalogue_index import manifest_bytes
    path=Path(configured).resolve(strict=True)
    raw=manifest_bytes(path)
    return str(path),raw


@lru_cache(maxsize=1)
def _catalogue_generation(binding):
    if binding is None:
        return Catalogue(REGISTRY_PATH.read_bytes())
    from .source_catalogue_index import IndexedCatalogue
    return IndexedCatalogue(Path(binding[0]),binding[1],base_path=REGISTRY_PATH)


def catalogue():
    result=_catalogue_generation(catalogue_binding())
    if hasattr(result,"assert_unchanged"):
        result.assert_unchanged()
    return result


@dataclass(frozen=True)
class Objective:
    terms:frozenset
    concepts:frozenset
    grams:frozenset
    ecosystems:frozenset
    goals:tuple


def objective(query):
    if not isinstance(query,str) or not query.strip() or len(query)>1024:
        raise ValueError("source navigation objective")
    terms=frozenset(words(query))
    goals=tuple(sorted((key for key,(text,_) in GOALS.items() if terms & set(words(text)))))
    return Objective(terms,frozenset(concepts(terms)),frozenset(grams(terms)),ecosystem_tags(query),goals)


def score_source(source,task):
    exact=len(task.terms&source.identity_terms)/max(1,len(task.terms))
    lexical=len(task.terms&source.tags)/max(1,len(task.terms))
    concept=len(task.concepts&source.concepts)/max(1,len(task.concepts))
    trigram=len(task.grams&source.grams)/max(1,len(task.grams|source.grams))
    franchise=len(task.ecosystems&source.ecosystems)/max(1,len(task.ecosystems))
    kinds={kind for goal in task.goals for kind in GOALS[goal][1]}
    intent=1. if source.kind in kinds else .25 if kinds else .5
    # Prefer specifically named titles/sources over broad shared tags.
    base=.30*exact+.16*lexical+.14*concept+.10*trigram+.24*franchise+.06*intent
    if task.ecosystems and source.ecosystems and not task.ecosystems&source.ecosystems:base*=.45
    return min(1.,base),{"identity_overlap":round(exact,8),"semantic_overlap":round(concept,8),
        "ecosystem_match":round(franchise,8),"goal_kind_match":intent}


def rank_sources(query,*,limit=24,families=None,previous=(),registry=None):
    if type(limit) is not int or not 1<=limit<=MAX_ROOTS:raise ValueError("source result bound")
    if families is not None and (not isinstance(families,(list,tuple)) or not set(families)<=FAMILIES or len(families)>len(FAMILIES)):
        raise ValueError("source family filter")
    if not isinstance(previous,(list,tuple)) or len(previous)>512 or any(not isinstance(x,str) or len(x)!=64 for x in previous):
        raise ValueError("source prior identity bound")
    registry=registry or catalogue();task=objective(query);prior=set(previous)
    # Streaming scoring retains only the global best candidates and one
    # representative per origin. Thousands of repository paths on one host
    # must not evict all independent publishers before diversity selection.
    host_best={}
    indexed=hasattr(registry,"candidate_rows")
    shortlist=registry.candidate_rows(task,families,prior) if indexed else registry.rows
    def order(row):
        return (-row[1],row[0].id)
    def candidates():
        for s in shortlist:
            if s.id in prior or families is not None and s.family not in families:
                continue
            score,features=score_source(s,task)
            row=(s,score,features)
            old=host_best.get(s.host)
            if old is None or order(row)<order(old):
                host_best[s.host]=row
            yield row
    top=nsmallest(256,candidates(),key=order)
    spread=nsmallest(128,host_best.values(),key=order)
    pool=list({row[0].id:row for row in top+spread}.values())
    if len(pool)>MAX_RANK_POOL:
        raise ValueError("source rank pool invariant")
    selected=[];hosts=Counter();kinds=Counter();groups=Counter();covered=set()
    while pool and len(selected)<limit:
        def key(row):
            s,base,_=row
            novelty=len((task.terms&s.tags)-covered)/max(1,len(task.terms))
            bridge=any(s.family in BRIDGES[g] for g in groups)
            score=.70*base+.15*novelty+.06/(1+hosts[s.host])+.05/(1+kinds[s.kind])+.03/(1+groups[s.family])+.01*bridge
            return (-round(score,10),s.id)
        choice=min(pool,key=key);score=-key(choice)[0];pool.remove(choice)
        s,base,features=choice
        selected.append({**s.public(),"relevance":round(base,8),"priority":round(score,8),
            "features":features,"bridge_families":list(BRIDGES[s.family])})
        hosts[s.host]+=1;kinds[s.kind]+=1;groups[s.family]+=1;covered.update(task.terms&s.tags)
    return {"catalogue":registry.summary(),"sources":selected,"goals":list(task.goals),
            "ecosystems":sorted(task.ecosystems),"distinct_hosts":len(hosts),
            "coverage_is_estimated":True,"rank_search_is_bounded":indexed,"network_authorized":False,
            "source_rights_granted":False}


DISCOVERY_STAGES={
 "directory":("category_and_title_index","sitemap_and_feed_links","published_item_metadata","related_publishers"),
 "community":("project_index","version_and_dependency_metadata","compatibility_and_documentation","linked_upstream_projects"),
 "reference":("topic_and_taxonomy_index","related_entries_and_citations","version_and_revision_metadata","publisher_cross_reference"),
 "documentation":("navigation_tree","version_selector_and_release_notes","api_and_schema_reference","linked_examples_and_upstream"),
 "asset_catalogue":("item_index","explicit_license_metadata","revision_and_format_metadata","publisher_and_dependencies"),
 "dataset":("dataset_index","manifest_and_schema_metadata","release_provenance_and_license","related_dataset_catalogues"),
 "connector_docs":("endpoint_documentation","authentication_and_rate_policy","version_and_schema_reference","approved_connector_review"),
}
PATH_CUES={
 "index":frozenset(("index","catalog","catalogue","directory","category","categories","list","browse","sitemap","sitemaps","feed","feeds","rss","atom")),
 "versions":frozenset(("release","releases","version","versions","changelog","patch","patches","history","revision","revisions")),
 "schema":frozenset(("api","schema","schemas","reference","docs","documentation","manifest","manifests","metadata","export","exports","dataset","datasets")),
 "dependencies":frozenset(("dependency","dependencies","requirement","requirements","compatibility","plugins","addons","modules","packages")),
 "rights":frozenset(("license","licenses","licence","licences","copyright","terms","attribution")),
}
def discovery_profile(url,task,registry=None):
    """Recognize only actual admitted paths; suggested stages are symbolic."""
    registry=registry or catalogue();source=registry.match(url)
    if source is None:return None
    path_words=set(words(unquote(urlsplit(url).path,errors="replace")))
    cues=sorted(key for key,aliases in PATH_CUES.items() if path_words&aliases)
    goal_cues=set()
    if "modding" in task.goals:goal_cues.update(("dependencies","versions","schema"))
    if "historical" in task.goals:goal_cues.update(("versions","index"))
    if "assets" in task.goals:goal_cues.update(("rights","versions","schema"))
    if "datasets" in task.goals:goal_cues.update(("schema","rights","versions"))
    if "implementation" in task.goals:goal_cues.update(("schema","dependencies","versions"))
    if not goal_cues:goal_cues.add("index")
    specificity=min(1.,len(set(cues)&goal_cues)/max(1,min(2,len(goal_cues))))
    return {"source_id":source.id,"path_cues":cues,"goal_path_match":specificity,
            "navigation_stages":list(DISCOVERY_STAGES[source.kind]),
            "review_days":FRESHNESS[source.kind],"network_authorized":False}


def frontier_signal(url,task,registry=None):
    """Small advisory source signal for an already-admitted frontier URL."""
    registry=registry or catalogue();row=registry.match(url)
    if row is None:return None
    score,_=score_source(row,task)
    profile=discovery_profile(url,task,registry)
    # Symbolic path cues add a small context-specific lead value; actual
    # measured origin health and all transport policy remain controlling.
    return min(1.,.85*score+.15*profile["goal_path_match"])
