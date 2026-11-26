"""Research-backed design-lead catalogues, not autonomous crawling permission.

The leads below are public documentation/directory URLs checked in the design
pass. They are metadata seeds only; source rights and freshness must be verified
by the runtime. No credentials, private player records or executable tools.
"""
from __future__ import annotations

import json
from core.dragon_game_corpus import MAX_SOURCES,MAX_GAMES,MAX_REVISIONS
from core.dragon_game_taxonomy import SOURCE_CLASSES,FAMILIES
from core.dragon_hoarder_manifests import MAX_MANIFESTS
from core.dragon_hoarder_bulk import MAX_VOLUMES
from core.dragon_release_queue import MAX_PENDING

PROFILES={
    "persistent-mmo":{
        "title":"Persistent MMO and third-party tool ecosystem",
        "example":"EVE Online","provider":"developer","id":"eve-online",
        "reference_urls":(
            ("https://developers.eveonline.com/","developer_portal"),
            ("https://developers.eveonline.com/docs/services/esi/overview/","public_api_reference"),
            ("https://developers.eveonline.com/docs/services/static-data/","static_data_export"),
            ("https://developers.eveonline.com/static-data/tranquility/latest.jsonl","public_update_feed"),
            ("https://developers.eveonline.com/static-data/tranquility/schema-changelog.yaml","static_data_schema"),
            ("https://developers.eveonline.com/docs/community/","third_party_tool_directory"),
            ("https://wiki.eveuniversity.org/Third-party_tools","third_party_tool_directory"),
            ("https://developers.eveonline.com/docs/support/","official_support"),
            ("https://wiki.eveuniversity.org/Static_Data_Export","game_data_conversion"),
            ("https://www.eveonline.com/news/view/eve-evolved-the-future-of-eves-api","developer_blog"),
        ),
        "design_load":{"source_identities":5_000_000,"retained_revisions":100_000_000,
                       "structured_rows":100_000_000,"media_objects":1_000_000},
    },
    "large-open-world":{
        "title":"Large open-world and emergent online ecosystem",
        "example":"Grand Theft Auto VI","provider":"publisher","id":"gta-vi",
        "reference_urls":(("https://www.rockstargames.com/VI","storefront"),
            ("https://www.rockstargames.com/VI/only-in-leonida","world_atlas"),
            ("https://www.rockstargames.com/VI/launch-gallery","screenshot_gallery"),),
        "design_load":{"source_identities":10_000_000,"retained_revisions":200_000_000,
                       "structured_rows":100_000_000,"media_objects":5_000_000},
    },
}


def _expanded_profiles():
    from core.dragon_source_directory import _load,PRESET_IDENTITIES
    _,groups,rows,_=_load()
    profiles={k:dict(v) for k,v in PROFILES.items()}
    mapping={"persistent-mmo":"eve","large-open-world":"gta-vi",
             "warcraft-raid-addon":"warcraft","gta-roleplay":"gta-v",
             "fallout-modding":"fallout","mario-franchise":"mario"}
    designs={
        "warcraft-raid-addon":("Raid encounters, character theory, addon and combat analytics",12_000_000,400_000_000,100_000_000,3_000_000),
        "gta-roleplay":("Open-world atlas, roleplay servers, resource frameworks and vehicle catalogues",15_000_000,450_000_000,100_000_000,5_000_000),
        "fallout-modding":("Franchise, branching RPG records, mods, plugins and world maps",12_000_000,350_000_000,100_000_000,4_000_000),
        "mario-franchise":("Platformer franchise, course creation, retro history, speedruns and visual references",8_000_000,250_000_000,100_000_000,5_000_000),
    }
    for pid,gid in mapping.items():
        namespace,external,title=PRESET_IDENTITIES[gid]
        routes=tuple((r["url"],r["kind"]) for r in rows.values() if r["group"]==gid)
        if pid in profiles:
            p=profiles[pid]
            # Keep every original reference; broaden the profile with new
            # independent directional leads. Same URL/kind only once.
            p["reference_urls"]=tuple(dict.fromkeys(p["reference_urls"]+routes))
        else:
            name,sources,revisions,data,media=designs[pid]
            profiles[pid]={"title":name,"example":title,"provider":namespace,
                "id":external,"reference_urls":routes,"design_load":{
                    "source_identities":sources,"retained_revisions":revisions,
                    "structured_rows":data,"media_objects":media}}
        profiles[pid]["directory_group"]=gid
        profiles[pid]["scope"]=groups[gid]["scope"]
    return profiles


def public_profiles():
    return {"profiles":[{"id":k,"title":p["title"],"example":p["example"],
             "candidate_urls":len(p["reference_urls"]),"design_load":p["design_load"],
             "directory_group":p["directory_group"],"scope":p["scope"],
             "measured":False,"network_authority":False} for k,p in sorted(_expanded_profiles().items())],
            "architectural_limits":{"source_classes":len(SOURCE_CLASSES),"families":len(FAMILIES),
                "sources_per_game":MAX_SOURCES,"games_per_owner":MAX_GAMES,
                "observations_per_owner":MAX_REVISIONS,"manifest_ids_per_owner":MAX_MANIFESTS,
                "retained_queue_rows_per_owner":MAX_PENDING,"volumes_per_lane":MAX_VOLUMES},
            "populated":False,"production_capacity_verified":False}


def manifest(profile):
    p=_expanded_profiles().get(profile)
    if not p:raise ValueError("unknown profile")
    links=[{"url":url,"kind":kind,"language":"en"} for url,kind in p["reference_urls"]]
    # A profile describes the design load, not a claim of actual game scale or
    # a release date. Live discovery supplies separately timestamped metadata.
    entries=[{"id":p["id"],"title":p["example"],"stage":"unknown","links":links[i:i+8]} for i in range(0,len(links),8)]
    return json.dumps({"schema":"dragon.game-feed.v1","provider":p["provider"],"entries":entries},
                      ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
