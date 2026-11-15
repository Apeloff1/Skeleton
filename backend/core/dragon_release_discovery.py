"""Source discovery adapters for bounded, locally supplied release manifests.

These parsers do not fetch URLs. Allowlisted provider IDs are hints, not
permission to fetch. The canonical crawler owns DNS, robots, redirect and
network admission. All external content is treated as data.
"""
from __future__ import annotations

from dataclasses import dataclass,replace
from datetime import date
import hashlib
import json
import re
from urllib.parse import urlsplit
from xml.etree import ElementTree

MAX_FEED_BYTES=2*1024*1024
MAX_ENTRIES=500
MAX_LINKS=8
PROVIDERS={"steam","gog","itch","epic","xbox","playstation","nintendo",
           "igdb","wikidata","independent","open_source","preservation",
           "fandom","mediawiki","wiki_gg","strategywiki","gamefaqs","mobygames",
           "archive_org","github","gitlab","moddb","nexusmods","modrinth","curseforge",
           "youtube","vimeo","twitch","peertube","gamebanana","speedrun",
           "apple_app_store","google_play","humble","game_jolt","itch_jam",
           "publisher","developer","museum","library","academic","press","esports",
           "community","official_support","open_game_data"}
HOSTS={
    "steam":"store.steampowered.com", "gog":"www.gog.com",
    "itch":"itch.io", "epic":"store.epicgames.com",
    "xbox":"www.xbox.com", "playstation":"www.playstation.com",
    "nintendo":"www.nintendo.com", "wikidata":"www.wikidata.org",
}
from core.dragon_game_taxonomy import KINDS
STAGES={"announced","early_access","released","updated","delisted","unknown"}


def _sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _text(value,limit):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError("invalid feed field")
    return value.strip()


@dataclass(frozen=True)
class Proposal:
    namespace: str
    external_id: str
    title: str
    stage: str
    source: str
    kind: str
    language: str
    event_key: str
    version: str|None
    released_on: str|None

    def observation(self):
        from dataclasses import asdict
        return asdict(self)


def _proposal(provider, entry, link):
    from core.dragon_game_corpus import source_url,key,clean
    external=key(entry["id"])
    title=clean(entry["title"],256)
    stage=entry.get("stage","unknown")
    kind=link.get("kind","storefront")
    if stage not in STAGES or kind not in KINDS:
        raise ValueError("unsupported release classification")
    source=source_url(link["url"])
    lang=clean(link.get("language","und"),32).lower()
    if not re.fullmatch(r"[a-z]{2,8}(?:-[a-z0-9]{1,8}){0,3}|und",lang):
        raise ValueError("invalid language")
    released=entry.get("released_on")
    if released is not None:
        if not isinstance(released,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",released):
            raise ValueError("invalid release day")
        date.fromisoformat(released)
    version=entry.get("version")
    if version is not None:
        version=clean(version,128)
    fields=[provider,external,title,stage,source,kind,lang,version,released]
    event=_sha(fields)
    return Proposal(provider,external,title,stage,source,kind,lang,event,version,released)


def _bounded(raw):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_FEED_BYTES:
        raise ValueError("feed size bound")


def _unique_pairs(pairs):
    out={}
    for key,value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key]=value
    return out


def parse_manifest(raw):
    """Normalized multi-provider JSON feed. Deterministic source proposals."""
    _bounded(raw)
    try:
        data=json.loads(raw,object_pairs_hook=_unique_pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (UnicodeError,RecursionError) as exc:
        raise ValueError("invalid feed encoding") from exc
    if not isinstance(data,dict) or set(data)!={"schema","provider","entries"} or data["schema"]!="dragon.game-feed.v1":
        raise ValueError("unknown feed schema")
    provider=data["provider"]
    if not isinstance(provider,str) or provider not in PROVIDERS:
        raise ValueError("unknown feed provider")
    entries=data["entries"]
    if not isinstance(entries,list) or not 1<=len(entries)<=MAX_ENTRIES:
        raise ValueError("feed item bound")
    results={}
    for entry in entries:
        if not isinstance(entry,dict) or not {"id","title","links"}.issubset(entry) or set(entry)-{"id","title","links","stage","version","released_on"}:
            raise ValueError("invalid feed record")
        links=entry["links"]
        if not isinstance(links,list) or not 1<=len(links)<=MAX_LINKS:
            raise ValueError("source count bound")
        for link in links:
            if not isinstance(link,dict) or "url" not in link or set(link)-{"url","kind","language"}:
                raise ValueError("invalid feed link")
            item=_proposal(provider,entry,link)
            results[item.event_key]=item
    return list(results.values())


def parse_steam_catalogue(raw):
    """Accept a locally supplied Steam app-list response; no API key required here."""
    _bounded(raw)
    try:
        data=json.loads(raw,object_pairs_hook=_unique_pairs)
        entries=data["applist"]["apps"]
    except (KeyError,TypeError,RecursionError,UnicodeError) as exc:
        raise ValueError("invalid app-list") from exc
    if not isinstance(entries,list) or not 1<=len(entries)<=MAX_ENTRIES:
        raise ValueError("paginate app-list before import")
    out=[]
    for entry in entries:
        if not isinstance(entry,dict) or type(entry.get("appid")) is not int or not 0<entry["appid"]<2**63:
            raise ValueError("invalid app id")
        app=str(entry["appid"])
        out.append(_proposal("steam",{"id":app,"title":entry.get("name"),"stage":"unknown"},
                             {"url":"https://store.steampowered.com/app/"+app+"/","kind":"storefront"}))
    return out


def parse_release_feed(raw,*,provider,external_id,title):
    """RSS/Atom patch/release candidates, attached to an explicit game identity.

    Do not infer release validity from item titles. Entry URLs are candidates
    only. Reject DTD/entity declarations before parsing and limit all input.
    """
    _bounded(raw)
    if provider not in PROVIDERS:
        raise ValueError("unknown provider")
    # Force UTF-8, excluding alternate encodings that could conceal declarations.
    try:
        value=raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("feed must be UTF-8") from exc
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)",value,re.IGNORECASE) or "\x00" in value:
        raise ValueError("unsafe XML declarations")
    try:
        root=ElementTree.fromstring(value)
    except ElementTree.ParseError as exc:
        raise ValueError("invalid XML") from exc
    tag=lambda x:x.rsplit("}",1)[-1]
    if tag(root.tag) not in {"rss","feed"}:
        raise ValueError("unknown feed root")
    result=[]
    items=[x for x in root.iter() if tag(x.tag) in {"entry","item"}]
    if not 1<=len(items)<=MAX_ENTRIES:
        raise ValueError("feed item bound")
    for item in items:
        link=None
        for child in item:
            if tag(child.tag)=="link" and child.get("rel","alternate")=="alternate":
                link=child.get("href") or child.text
                if link:
                    break
        if not link:
            continue
        candidate=_proposal(provider,{"id":external_id,"title":title,"stage":"unknown"},
            {"url":link,"kind":"release_feed"})
        # Same article URL can carry distinct patch announcements. Bind event
        # identity to bounded explicit feed fields without interpreting claims.
        marker=[]
        for child in item:
            if tag(child.tag) in {"guid","id","title","published","updated","pubDate"}:
                marker.append([tag(child.tag),(child.text or "")[:2048]])
        result.append(replace(candidate,event_key=_sha([candidate.event_key,marker])))
    return list({x.event_key:x for x in result}.values())
