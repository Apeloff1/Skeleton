"""Conservative structural source hints for explicitly authorized sitemap feeds.

Rules classify public locator shapes only. They do not certify MIME, actual
page content, source provenance, copyright, meaning, or network authority.
The classified_sitemap adapter is opt-in to avoid changing historical source
identity when upgrading existing generic sitemap subscriptions.
"""
from __future__ import annotations

import re
from urllib.parse import unquote,urlsplit

from core.dragon_game_corpus import source_url
from core.dragon_game_taxonomy import SOURCE_CLASSES

# Prefer specific interoperable source kinds over broad thematic guesses.
EXTENSIONS={
    ".pdf":"pdf_manual",".png":"visual_effect_reference",".jpg":"photo_reference",
    ".jpeg":"photo_reference",".webp":"photo_reference",".gif":"animation_demo",
    ".mp4":"gameplay_video",".webm":"gameplay_video",".mp3":"audio_commentary",
    ".ogg":"audio_commentary",".wav":"audio_commentary",".vtt":"caption_track_catalogue",
    ".srt":"caption_track_catalogue",".jsonl":"public_jsonl_dataset",
    ".csv":"public_csv_dataset",".parquet":"public_parquet_dataset",".sqlite3":"public_sqlite_dataset",
}
# Ordered by specificity. A rule requires a whole normalized path segment,
# not a substring in the host, query string, or an arbitrary article title.
PATH_RULES=(
    ({"addons","addon"}, "addon_directory"),
    ({"modpacks","mod-packs","collections"}, "mod_collection_catalogue"),
    ({"mods","modding"}, "mod_collection_catalogue"),
    ({"plugins","extensions"}, "public_plugin_catalogue"),
    ({"load-orders","load-order"}, "plugin_load_order"),
    ({"changelog","changelogs","patch-notes","release-notes"}, "patch_notes"),
    ({"guides","walkthroughs","walkthrough"}, "strategy_database"),
    ({"vehicles","cars","motorcycles","aircraft"}, "vehicle_database"),
    ({"heists","missions"}, "mission_reference"),
    ({"collectibles","secrets"}, "collectible_reference"),
    ({"maps","atlas","map"}, "map_database"),
    ({"zones","regions","locations"}, "location_reference"),
    ({"dungeons","mythic-plus"}, "dungeon_reference"),
    ({"raids","encounters"}, "raid_reference"),
    ({"classes","specializations","specs"}, "specialization_database"),
    ({"talents","talent-calculator"}, "talent_calculator"),
    ({"spells","abilities"}, "ability_reference"),
    ({"gear","equipment","items"}, "item_database"),
    ({"quests","quest"}, "quest_database"),
    ({"achievements","trophies"}, "achievement_database"),
    ({"characters","npcs","creatures","enemies"}, "character_profile"),
    ({"crafting","recipes"}, "recipe_reference"),
    ({"markets","auction-house","prices"}, "regional_market"),
    ({"leaderboards","rankings","standings"}, "leaderboard_record"),
    ({"speedruns","speedrun","runs"}, "speedrun_category_rules"),
    ({"splits","timings"}, "speedrun_split_schema"),
    ({"levels","courses","stages"}, "platformer_level_database"),
    ({"sprites","spritesheets","tilesets"}, "sprite_sheet_catalogue"),
    ({"screenshots","gallery","galleries"}, "screenshot_gallery"),
    ({"soundtracks","music","audio"}, "soundtrack_reference"),
    ({"trailers","videos","vods"}, "gameplay_video"),
    ({"manuals","documents","documentation"}, "technical_whitepaper"),
    ({"api","openapi","graphql"}, "public_api_reference"),
    ({"datasets","exports","data-dumps"}, "public_data_export"),
    ({"history","archive","archives"}, "archival_record"),
    ({"compatibility","compat"}, "compatibility_matrix"),
    ({"accessibility"}, "accessibility_feature_matrix"),
    ({"wiki"}, "community_wiki"),
    ({"news","announcements","updates"}, "announcement_article"),
)
LANGUAGES={"en","ja","zh","ko","de","fr","es","it","pt","pl","ru","uk","tr","ar","he","th",
           "vi","id","ms","hi","sv","nb","da","fi","nl","cs","el","hu","ro","bg","sr","sk",
           "en-us","en-gb","pt-br","zh-cn","zh-tw","es-mx","es-es","fr-ca","ko-kr","ja-jp"}

def classify_locator(locator):
    url=source_url(locator);p=urlsplit(url)
    # Percent-encoded path separators must not manufacture segments. Rename
    # punctuation only inside a segment, never reparse decoded paths as URLs.
    raw=p.path.split("/")
    normalized=[]
    for segment in raw:
        decoded=unquote(segment,encoding="utf-8",errors="replace").casefold()
        if "/" in decoded or "\\" in decoded or len(decoded)>256:
            continue
        normalized.append(re.sub(r"[\s_]+","-",decoded).strip("-"))
    nonempty=[s for s in normalized if s]
    first=nonempty[0] if nonempty else ""
    language=first if first in LANGUAGES else "und"
    terminal=nonempty[-1] if nonempty else ""
    suffix="."+terminal.rsplit(".",1)[-1] if "." in terminal else ""
    if suffix in EXTENSIONS:
        kind=EXTENSIONS[suffix];basis="extension_hint"
    else:
        # The final slug often describes a particular title, not a section.
        # Include it only when it exactly matches a known section.
        segments=set(nonempty)
        kind="reference_database";basis="generic_locator"
        for literals,candidate in PATH_RULES:
            if segments&literals:
                kind=candidate;basis="path_section_hint";break
    if kind not in SOURCE_CLASSES:raise ValueError("classification taxonomy differs")
    return {"kind":kind,"language":language,"basis":basis,"verified":False,
            "network_authorized":False,"content_type_verified":False}
