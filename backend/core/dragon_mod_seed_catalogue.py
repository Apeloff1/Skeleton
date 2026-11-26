"""Scalable, deterministic game and mod discovery seed catalogue.

The frozen input manifests are curated *candidate* identities, not remotely
verified provider exports. Route expansion enumerates provider-specific
surfaces; it is not crawling, source verification, or asset downloading.
Each row records its construction basis and preserves the candidate identity.
A cross-game directory or tool project never becomes a fake game identity.
"""
from __future__ import annotations

from collections import Counter,defaultdict
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from core.dragon_game_corpus import GameCorpus,clean,digest,game_id,key,source_url,_id
from core.dragon_game_taxonomy import SOURCE_CLASSES,FAMILIES,view_mode
from core.dragon_hoarder_bulk import owner_key
from core.dragon_release_discovery import MAX_ENTRIES,MAX_FEED_BYTES,PROVIDERS
from core.dragon_release_queue import ReleaseQueue,MAX_ROWS_PER_IMPORT

ROOT=Path(__file__).parent
MAX_SEEDS=100_000
MAX_APPS=8192
MAX_REPOS=8192
MAX_COMMUNITIES=8192
MAX_FILE_BYTES=8*1024*1024
MAX_PAGE=100
MAX_SELECTION=256
MAX_APP_SELECTION=128
APPID=re.compile(r"[1-9][0-9]{1,11}\Z")
SLUG=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
REPO=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
GROUP=re.compile(r"[a-z][a-z0-9-]{0,63}\Z")

# Public route patterns are deliberately separate from verified availability.
# Workshop can be unavailable for individual games, SteamDB/ProtonDB are
# independent providers, and some GitHub project sections may be disabled.
STEAM_ROUTES=(
    ("steam","storefront","Store","https://store.steampowered.com/app/{id}/",False),
    ("steam","reference_database","Community hub","https://steamcommunity.com/app/{id}/",False),
    ("steam","community_workshop","Workshop","https://steamcommunity.com/app/{id}/workshop/",True),
    ("steam","community_forum","Discussions","https://steamcommunity.com/app/{id}/discussions/",False),
    ("steam","strategy_database","Community guides","https://steamcommunity.com/app/{id}/guides/",False),
    ("steam","screenshot_gallery","Screenshots","https://steamcommunity.com/app/{id}/screenshots/",False),
    ("steam","fan_art_reference","Artwork","https://steamcommunity.com/app/{id}/images/",False),
    ("steam","gameplay_video","Videos","https://steamcommunity.com/app/{id}/videos/",False),
    ("steam","storefront_review","Community reviews","https://steamcommunity.com/app/{id}/reviews/",False),
    ("steam","release_feed","Community news","https://steamcommunity.com/app/{id}/allnews/",False),
    ("steam","announcement_article","Store news","https://store.steampowered.com/news/app/{id}/",False),
    ("steam","achievement_database","Achievement statistics","https://steamcommunity.com/stats/{id}/achievements/",False),
    ("community","reference_database","SteamDB app metadata","https://steamdb.info/app/{id}/",False),
    ("community","patch_notes","SteamDB patch history","https://steamdb.info/app/{id}/patchnotes/",True),
    ("community","public_release_manifest","SteamDB depot metadata","https://steamdb.info/app/{id}/depots/",True),
    ("community","release_revision","SteamDB change history","https://steamdb.info/app/{id}/history/",True),
    ("community","compatibility_layer_report","ProtonDB compatibility","https://www.protondb.com/app/{id}",True),
)
NEXUS_ROUTES=(
    ("mod_game_directory","Nexus game mod hub","https://www.nexusmods.com/{slug}"),
    ("mod_project_directory","Nexus mod project list","https://www.nexusmods.com/{slug}/mods/"),
    ("mod_category_directory","Nexus category directory","https://www.nexusmods.com/{slug}/mods/categories/"),
)
REPOSITORY_ROUTES=(
    ("mod_project_readme","Repository",""),
    ("mod_project_releases","Versioned releases","/releases"),
    ("mod_project_tags","Version tags","/tags"),
    ("mod_project_issues","Issue tracker","/issues"),
    ("mod_project_wiki","Documentation wiki","/wiki"),
    ("mod_project_discussion","Project discussions","/discussions"),
)
COMMUNITY_ROUTES={
    "thunderstore":(("mod_game_directory","Package community","https://thunderstore.io/c/{slug}/"),),
    "curseforge":(("mod_game_directory","Modding community","https://www.curseforge.com/{slug}"),),
    "modio":(("mod_game_directory","Modding community","https://mod.io/g/{slug}"),),
    "moddb":(
        ("mod_game_directory","Game profile","https://www.moddb.com/games/{slug}"),
        ("mod_project_directory","Mods","https://www.moddb.com/games/{slug}/mods"),
        ("mod_file_catalogue","File metadata","https://www.moddb.com/games/{slug}/downloads"),
        ("addon_directory","Addons","https://www.moddb.com/games/{slug}/addons"),
        ("modding_guide_index","Tutorials","https://www.moddb.com/games/{slug}/tutorials"),
    ),
}
LANES={"game_surfaces","mod_platforms","tool_repositories","specialist_sites"}
BASELINE="dragon_mod_seed_apps.json"
TOOLS="dragon_mod_seed_tools.json"
COMMUNITIES="dragon_mod_seed_providers.json"


def _pairs(values):
    out={}
    for k,v in values:
        if k in out:raise ValueError("duplicate seed data field")
        out[k]=v
    return out


def _read(name,schema,fields):
    raw=(ROOT/name).read_bytes()
    if not 1<=len(raw)<=MAX_FILE_BYTES:raise ValueError("seed input byte bound")
    doc=json.loads(raw,object_pairs_hook=_pairs)
    if not isinstance(doc,dict) or doc.get("schema")!=schema or set(doc)!=fields:
        raise ValueError("seed input schema")
    return raw,doc


def _match(regex,value):
    if not isinstance(value,str) or not regex.fullmatch(value):raise ValueError("seed input identity")
    return value


def _canonical_locator(url):
    """Collapse root/trailing-slash spelling for census only, not fetching."""
    p=urlsplit(source_url(url))
    return p.scheme+"://"+p.netloc+(p.path.rstrip("/") or "/")


def _array(value,limit):
    if not isinstance(value,list) or not 1<=len(value)<=limit:raise ValueError("seed input row bound")
    return value


@lru_cache(maxsize=1)
def _load():
    ar,a=_read(BASELINE,"dragon.mod-seed-apps.v1",{"schema","provenance","games"})
    tr,t=_read(TOOLS,"dragon.mod-tool-repositories.v1",{"schema","description","repositories"})
    cr,c=_read(COMMUNITIES,"dragon.mod-provider-seeds.v1",{"schema","provenance","communities","sites"})
    # The revision binds the actual route specification, title inputs,
    # original directory identity and canonicalized resulting records.
    from core.dragon_source_directory import _load as old_directory
    old_revision,_,legacy,_=old_directory()
    legacy_urls={_canonical_locator(row["url"]) for row in legacy.values()}
    rows={};apps={};by_app=defaultdict(list);by_lane=defaultdict(list);seen={}
    old_overlap=set();collisions=0
    def add(*,lane,group,title,label,url,provider,kind,basis,appid=None,mod_related=False):
        nonlocal collisions
        if lane not in LANES or kind not in SOURCE_CLASSES or type(mod_related) is not bool:
            raise ValueError("seed route taxonomy")
        group=_match(GROUP,group);title=clean(title,256);label=clean(label,160)
        url=source_url(url)
        normalized=_canonical_locator(url)
        # One locator once within the expanded catalogue. Repeated aliases
        # (including old/canonical slash variants) don't inflate the count.
        previous=seen.get(normalized)
        if previous:
            collisions+=1;return
        if normalized in legacy_urls:old_overlap.add(normalized)
        lid=digest(["dragon.mod-seeds.v1",lane,url,provider,kind,appid])
        if lid in rows:raise ValueError("seed identity collision")
        if appid is not None and appid not in apps:raise ValueError("unknown app")
        item={"seed_id":lid,"lane":lane,"group":group,"title":title,"label":label,
              "url":url,"provider":provider,"kind":kind,"family":SOURCE_CLASSES[kind].family,
              "view_mode":view_mode(kind),"basis":basis,"appid":appid,
              "candidate_game_id":game_id("steam",appid) if appid else None,
              "mod_related":mod_related,"verified":False,"network_authorized":False,
              "provider_identity_verified":False}
        rows[lid]=item;seen[normalized]=lid;by_lane[lane].append(lid)
        if appid:by_app[appid].append(lid)
        if len(rows)>MAX_SEEDS:raise ValueError("seed catalogue capacity")

    for row in _array(a["games"],MAX_APPS):
        if not isinstance(row,dict) or not {"appid","title","genre"}.issubset(row) or set(row)-{"appid","title","genre","nexus"}:
            raise ValueError("game candidate schema")
        appid=_match(APPID,row["appid"])
        if appid in apps:raise ValueError("duplicate app candidate")
        title=clean(row["title"],256)
        group=_match(GROUP,row["genre"])
        apps[appid]={"appid":appid,"title":title,"group":group,"candidate_game_id":game_id("steam",appid),
                     "verified":False}
    # An identical Nexus game domain reused by different editions is not a
    # confirmed app alias. Retain it on the non-VR candidate only if unique,
    # otherwise keep its discovery surface unbound.
    slugs=Counter(r["nexus"].lower() for r in a["games"] if "nexus" in r)
    seen_nexus=set()
    for row in a["games"]:
        appid=row["appid"];title=apps[appid]["title"];group=apps[appid]["group"]
        for provider,kind,label,route,mod_related in STEAM_ROUTES:
            add(lane="game_surfaces",group=group,title=title,label=label,
                url=route.format(id=appid),provider=provider,kind=kind,
                basis="generated_provider_route",appid=appid,mod_related=mod_related)
        if "nexus" in row:
            slug=_match(SLUG,row["nexus"]).lower()
            if slug in seen_nexus:continue
            seen_nexus.add(slug)
            ambiguous=slugs[slug]>1
            for kind,label,route in NEXUS_ROUTES:
                add(lane="mod_platforms",group="nexusmods",title=title if not ambiguous else slug,
                    label=label,url=route.format(slug=slug),provider="nexusmods",kind=kind,
                    basis="generated_provider_route",appid=None if ambiguous else appid,mod_related=True)
    repo_names=set()
    for row in _array(t["repositories"],MAX_REPOS):
        if not isinstance(row,dict) or set(row)!={"repo","title","domain"}:raise ValueError("repository candidate schema")
        repository=_match(REPO,row["repo"])
        if repository.lower() in repo_names:raise ValueError("duplicate tool repository")
        repo_names.add(repository.lower())
        title=clean(row["title"],256);group=_match(GROUP,row["domain"])
        for kind,label,tail in REPOSITORY_ROUTES:
            add(lane="tool_repositories",group=group,title=title,label=label,
                url="https://github.com/"+repository+tail,provider="github",kind=kind,
                basis="generated_repository_route",mod_related=True)
    for row in _array(c["communities"],MAX_COMMUNITIES):
        if not isinstance(row,dict) or set(row)!={"provider","slug","title"}:raise ValueError("mod community schema")
        provider=row["provider"];slug=_match(SLUG,row["slug"]);title=clean(row["title"],256)
        if provider not in COMMUNITY_ROUTES:raise ValueError("unknown mod community provider")
        for kind,label,route in COMMUNITY_ROUTES[provider]:
            add(lane="mod_platforms",group=provider,title=title,label=label,
                url=route.format(slug=slug),provider=provider,kind=kind,
                basis="generated_provider_route",mod_related=True)
    for row in _array(c["sites"],MAX_COMMUNITIES):
        if not isinstance(row,dict) or set(row)!={"url","title","kind"}:raise ValueError("specialist seed schema")
        host=urlsplit(source_url(row["url"])).hostname
        # Known direct locators use a neutral catalogue namespace; do not
        # invent ownership or credentials from their hostnames.
        add(lane="specialist_sites",group="modding-web",title=row["title"],label="Public source root",
            url=row["url"],provider="community",kind=row["kind"],
            basis="curated_locator",mod_related=True)
    revision=digest({
        "files":[hashlib.sha256(x).hexdigest() for x in (ar,tr,cr)],"legacy":old_revision,
        "routes":sorted((v["seed_id"],v["family"],v["group"],v["label"],v["basis"],v["title"],v["mod_related"]) for v in rows.values()),
        "schema":"dragon.mod-seeds.v1",
    })
    for appid in apps:
        apps[appid]["seeds"]=len(by_app[appid])
        apps[appid]["mod_related_seeds"]=sum(rows[r]["mod_related"] for r in by_app[appid])
    # Compute the precise union, not total route records across directories.
    stats={"legacy_records":len(legacy),"legacy_unique_locators":len(legacy_urls),
           "expanded_records":len(rows),"overlap_with_legacy":len(old_overlap),
           "total_unique_locators":len(legacy_urls|set(seen)),
           "distinct_hosts":len({urlsplit(url).hostname for url in legacy_urls|set(seen)}),
           "mod_related_records":sum(r["mod_related"] for r in rows.values()),
           "curated_locator_records":sum(r["basis"]=="curated_locator" for r in rows.values()),
           "generated_route_records":sum(r["basis"]!="curated_locator" for r in rows.values()),
           "candidate_apps":len(apps),"candidate_repositories":len(repo_names),
           "candidate_community_slugs":len(c["communities"]),"duplicate_routes_elided":collisions,
           "lanes":dict(Counter(r["lane"] for r in rows.values())),
           "providers":dict(Counter(r["provider"] for r in rows.values())),
           "groups":dict(Counter(r["group"] for r in rows.values()))}
    return revision,rows,apps,{k:tuple(sorted(v)) for k,v in by_app.items()},tuple(sorted(rows)),stats


def summary():
    revision,_,_,_,_,stats=_load()
    return {"revision":revision,**stats,"catalogue_only":True,"network_authorized":False,
            "source_verified":False,"training_allowed":False,"physical_capacity_verified":False}


def _fingerprint(revision,*values):
    return digest([revision,*values])


def _lower(after,fingerprint):
    if after is None:return ""
    if not isinstance(after,str) or len(after)!=129 or after[:65]!=fingerprint+":":
        raise ValueError("seed cursor mismatch")
    return _id(after[65:])


def _terms(value):
    if value is None:return []
    terms=re.findall(r"[^\W_]+",clean(value,256).casefold())[:16]
    if not terms:raise ValueError("seed search fields")
    return terms


def page(*,lane=None,group=None,provider=None,family=None,kind=None,appid=None,q=None,
         mod_only=False,after=None,limit=32):
    revision,rows,apps,by_app,ordered,stats=_load()
    if type(limit) is not int or not 1<=limit<=MAX_PAGE or type(mod_only) is not bool:
        raise ValueError("seed page bounds")
    if lane is not None and lane not in LANES:raise ValueError("seed lane")
    if group is not None and group not in stats["groups"]:raise ValueError("seed group")
    if provider is not None and provider not in stats["providers"]:raise ValueError("seed provider")
    if family is not None and family not in FAMILIES:raise ValueError("seed family")
    if kind is not None and kind not in SOURCE_CLASSES:raise ValueError("seed kind")
    if appid is not None and appid not in apps:raise ValueError("candidate app")
    terms=_terms(q)
    fingerprint=_fingerprint(revision,"seeds",lane,group,provider,family,kind,appid,terms,mod_only)
    lower=_lower(after,fingerprint)
    data=[]
    for lid in by_app[appid] if appid else ordered:
        if lid<=lower:continue
        row=rows[lid]
        if mod_only and not row["mod_related"]:continue
        if any(want is not None and row[field]!=want for field,want in (
            ("lane",lane),("group",group),("provider",provider),("family",family),("kind",kind))):continue
        hay=" ".join(str(row[x]).replace("_"," ").replace("-"," ").casefold()
                       for x in ("title","label","kind","family","group","provider","url"))
        if any(term not in hay for term in terms):continue
        data.append(dict(row))
        if len(data)>limit:break
    next_cursor=fingerprint+":"+data[limit-1]["seed_id"] if len(data)>limit else None
    return {"revision":revision,"seeds":data[:limit],"next_cursor":next_cursor,
            "catalogue_only":True,"network_authorized":False,"source_verified":False,"training_allowed":False}


def applications(*,group=None,q=None,after=None,limit=32):
    revision,_,apps,_,_,_=_load()
    if type(limit) is not int or not 1<=limit<=MAX_PAGE:raise ValueError("application page")
    if group is not None and group not in {row["group"] for row in apps.values()}:
        raise ValueError("application group")
    terms=_terms(q);fingerprint=_fingerprint(revision,"apps",group,terms)
    lower=_lower(after,fingerprint)
    ordered=sorted(apps.values(),key=lambda a:a["candidate_game_id"])
    result=[]
    for row in ordered:
        if row["candidate_game_id"]<=lower or group is not None and row["group"]!=group:continue
        hay=(row["title"]+" "+row["appid"]+" "+row["group"]).casefold()
        if any(x not in hay for x in terms):continue
        result.append(dict(row))
        if len(result)>limit:break
    return {"revision":revision,"applications":result[:limit],
            "next_cursor":fingerprint+":"+result[limit-1]["candidate_game_id"] if len(result)>limit else None,
            "catalogue_only":True,"network_authorized":False,"source_verified":False,"training_allowed":False}


def _validated_intent(revision,operation,acknowledged):
    current,*_=_load()
    if acknowledged is not True:raise ValueError("explicit seed metadata acknowledgement required")
    if _id(revision)!=current:raise ValueError("seed catalogue revision changed")
    if not isinstance(operation,str) or not 1<=len(operation)<=128 or operation.strip()!=operation:
        raise ValueError("seed operation identity")
    return current,"mod-seed:"+digest(operation)


def _queue(path,scope,namespace,entries,operation):
    if not 1<=len(entries)<=MAX_ENTRIES or sum(len(e["links"]) for e in entries)>MAX_ROWS_PER_IMPORT:
        raise ValueError("seed import batch exceeds durable queue bounds")
    raw=json.dumps({"schema":"dragon.game-feed.v1","provider":namespace,"entries":entries},
                   ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    if len(raw)>MAX_FEED_BYTES:raise ValueError("seed manifest byte bound")
    return ReleaseQueue(path).enqueue(scope,raw=raw,adapter="manifest",operation=operation)


def _entries(external,title,selection):
    links=[{"url":r["url"],"kind":r["kind"],"language":"und"} for r in selection]
    return [{"id":external,"title":title,"stage":"unknown","links":links[i:i+8]}
            for i in range(0,len(links),8)]


def import_applications(path,scope,*,revision,operation,appids,mod_only=False,acknowledged=False):
    """One atomic durable queue batch across explicit provider-native app IDs.

    Candidate titles are not confirmed by this operation. Restrict selection
    to app-bound seeds, preserving each app rather than binding many unrelated
    games to one record. No per-site network operations are scheduled.
    """
    revision,op=_validated_intent(revision,operation,acknowledged)
    if type(mod_only) is not bool:raise ValueError("seed selection mode")
    if not isinstance(appids,list) or not 1<=len(appids)<=MAX_APP_SELECTION:
        raise ValueError("seed application selection bounds")
    selection=sorted(_match(APPID,x) for x in appids)
    if len(set(selection))!=len(selection):raise ValueError("duplicate app selection")
    _,rows,apps,by_app,_,_=_load()
    if any(x not in apps for x in selection):raise ValueError("unknown candidate app")
    entries=[];counts=[]
    for appid in selection:
        chosen=[rows[sid] for sid in by_app[appid] if not mod_only or rows[sid]["mod_related"]]
        if not chosen:raise ValueError("empty candidate app source selection")
        entries.extend(_entries(appid,apps[appid]["title"],chosen))
        counts.append({"appid":appid,"game_id":game_id("steam",appid),"seeds":len(chosen)})
    receipt=_queue(path,scope,"steam",entries,op)
    return {**receipt,"revision":revision,"applications":counts,"selected":sum(x["seeds"] for x in counts),
            "capture_granted":False,"source_verified":False,"training_allowed":False}


def attach_specialists(path,scope,*,revision,operation,game,seed_ids,acknowledged=False):
    """Bind a selected neutral tool/community source to one existing game.

    App-bound seeds can only attach to the matching exact Steam identity,
    avoiding cross-title or cross-edition catalogue contamination.
    """
    revision,op=_validated_intent(revision,operation,acknowledged)
    game=_id(game);owner=owner_key(scope)
    if not isinstance(seed_ids,list) or not 1<=len(seed_ids)<=MAX_SELECTION:
        raise ValueError("specialist selection bounds")
    ids=sorted(_id(x) for x in seed_ids)
    if len(set(ids))!=len(ids):raise ValueError("duplicate seed selection")
    _,rows,_,_,_,_=_load()
    if any(x not in rows for x in ids):raise ValueError("unknown seed ID")
    chosen=[rows[x] for x in ids]
    with GameCorpus(path)._db() as db:
        record=db.execute("SELECT namespace,external_id,title FROM games WHERE owner=? AND id=?",(owner,game)).fetchone()
    if record is None:raise LookupError("owned game unavailable")
    namespace,external,title=record["namespace"],record["external_id"],record["title"]
    if namespace not in PROVIDERS or game_id(namespace,external)!=game:
        raise ValueError("game identity not supported by release queue")
    if any(r["appid"] is not None and r["candidate_game_id"]!=game for r in chosen):
        raise ValueError("app-specific seed cannot bind to a different game")
    receipt=_queue(path,scope,namespace,_entries(external,title,chosen),op)
    return {**receipt,"revision":revision,"game_id":game,"selected":len(ids),
            "capture_granted":False,"source_verified":False,"training_allowed":False}
