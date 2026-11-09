"""Jeeves' original-game *authoring* canon and long-range continuity verifier.

No gameplay runtime, model training, generated artwork, or legal certification.
Only human-reviewed source documents can become canon. All scene history can
be independently rebuilt; brief context is explicitly marked when truncated.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
import re

BIBLE = "skeleton.game_builder.story_bible.v1"
SCENE = "skeleton.game_builder.story_scene.v1"
ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
COLOR = re.compile(r"^#[A-Fa-f0-9]{6}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
MAX_SCENES = 9999
PHASES = ("foundation", "cast", "design")
FIELDS = ("status", "location", "affiliation", "outfit")


class StoryCanonError(ValueError):
    """Unreviewed, missing, contradictory or source-ambiguous original canon."""


def require(condition, reason):
    if not condition:
        raise StoryCanonError(reason)


def shape(value, keys, name):
    require(type(value) is dict and set(value) == set(keys),
            "exact " + name + " fields required")
    return value


def array(value, maximum, name, minimum=0):
    require(type(value) is list and minimum <= len(value) <= maximum,
            "bounded original " + name + " array required")
    return value


def ident(value, name):
    require(type(value) is str and ID.fullmatch(value) is not None,
            "invalid original " + name + " identity")
    return value


def text(value, name, limit=2000):
    require(type(value) is str and 1 <= len(value) <= limit and all(
        ord(c) >= 32 and c not in "<>" for c in value),
        "invalid or unsafe original " + name)
    return value


def number(value, minimum, maximum, name):
    require(type(value) is int and minimum <= value <= maximum,
            "invalid bounded " + name)
    return value


def colors(value, name):
    array(value, 12, name, 1)
    require(all(type(c) is str and COLOR.fullmatch(c) for c in value),
            "color palette must contain explicit hex colors")
    normalized = tuple(c.upper() for c in value)
    require(len(set(normalized)) == len(normalized),
            "duplicate visual colors in " + name)
    return normalized


def ids(rows, name):
    found = {}
    for row in rows:
        ident(row["id"], name)
        require(row["id"] not in found, "duplicate " + name + " ID")
        found[row["id"]] = row
    return found


def digest(payload):
    try:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, OverflowError) as exc:
        raise StoryCanonError("canon must contain finite typed JSON") from exc
    return sha256(encoded.encode("utf-8")).hexdigest()


def sign(document, schema):
    require(type(document) is dict, "signed source must be a typed object")
    body = {key: value for key, value in document.items()
            if key not in ("digest", "schema")}
    result = {"schema": schema, **body}
    return {**result, "digest": digest(result)}


def signed(document, schema, keys):
    shape(document, ("schema", "digest", *keys), "signed source")
    require(document["schema"] == schema and type(document["digest"]) is str
            and SHA.fullmatch(document["digest"]),
            "unsupported or malformed original source signature")
    require(digest({k: v for k, v in document.items() if k != "digest"})
            == document["digest"], "canon source checksum changed")
    return document


def story_bible_template(project):
    ident(project, "project")
    return {"schema": BIBLE, "project": project, "phase": "foundation",
            "title": "", "story": {"premise": "", "conflict": "",
                                   "themes": [], "planned_chapters": 100, "planned_acts": 1000},
            "world": {"era": "", "geography": "", "laws": []},
            "characters": [], "regions": [], "assets": [], "inspiration": [],
            "rights_reviewed": False, "digest": None}


def validate_story_bible(doc):
    signed(doc, BIBLE, ("project", "phase", "title", "story", "world",
                        "characters", "regions", "assets", "inspiration",
                        "rights_reviewed"))
    ident(doc["project"], "project")
    require(doc["phase"] in PHASES, "authoring must progress foundation -> cast -> design")
    text(doc["title"], "game title", 140)
    story = shape(doc["story"], ("premise", "conflict", "themes", "planned_acts")
                  + (("planned_chapters",) if "planned_chapters" in doc["story"] else ()),
                  "story")
    text(story["premise"], "central premise", 4000)
    text(story["conflict"], "narrative conflict", 2000)
    number(story["planned_acts"], 1, 1000, "game acts")
    if "planned_chapters" in story:
        number(story["planned_chapters"], 1, 100, "game chapters")
    for theme in array(story["themes"], 40, "original motifs", 1):
        text(theme, "original narrative motif", 100)
    world = shape(doc["world"], ("era", "geography", "laws"), "world")
    text(world["era"], "world era", 150)
    text(world["geography"], "world geography", 2000)
    for law in array(world["laws"], 128, "world laws", 1):
        text(law, "world causal law", 500)
    actors = array(doc["characters"], 256, "characters")
    regions = array(doc["regions"], 256, "regions")
    assets = array(doc["assets"], 2048, "asset specifications")
    if doc["phase"] == "foundation":
        require(not actors and not regions and not assets,
                "story/world foundation precedes cast and visual design")
    if doc["phase"] == "cast":
        require(actors and not regions and not assets,
                "character phase precedes world visual design")
    if doc["phase"] == "design":
        require(actors and regions and assets,
                "design requires cast, themed regions and original assets")
    for who in actors:
        shape(who, ("id", "name", "role", "personality", "motivation",
                    "appearance", "state"), "character")
        ident(who["id"], "character")
        for key in ("name", "role", "personality", "motivation"):
            text(who[key], "character " + key, 400)
        look = shape(who["appearance"],
                     ("hair", "eyes", "silhouette", "outfit", "palette"),
                     "character visual identity")
        for key in ("hair", "eyes", "silhouette", "outfit"):
            text(look[key], "character appearance " + key, 250)
        colors(look["palette"], "character color canon")
        state = shape(who["state"], FIELDS, "initial character state")
        require(state["status"] in ("alive", "missing", "dead"),
                "character life state must be authored")
        ident(state["location"], "character location")
        text(state["affiliation"], "character affiliation", 120)
        require(state["outfit"] == look["outfit"],
                "initial costume contradicts design bible")
    ids(actors, "cast")
    for region in regions:
        shape(region, ("id", "theme", "palette", "architecture",
                       "lighting", "materials"), "visual region")
        ident(region["id"], "region")
        for field in ("theme", "architecture", "lighting"):
            text(region[field], "regional " + field, 400)
        colors(region["palette"], "region colors")
        for material in array(region["materials"], 32, "regional materials", 1):
            text(material, "regional material", 100)
    rindex = ids(regions, "region")
    if doc["phase"] == "design":
        for who in actors:
            require(who["state"]["location"] in rindex,
                    "cast requires a location in approved geography")
    for asset in assets:
        shape(asset, ("id", "kind", "region", "palette",
                      "spec", "identity", "rights", "references"), "asset")
        ident(asset["id"], "asset")
        require(asset["kind"] in ("character", "environment", "prop", "item",
                                  "ability", "animation", "audio", "vfx", "ui"),
                "original asset must use reviewed discipline type")
        require(asset["region"] in rindex, "asset outside approved regional design")
        require(set(colors(asset["palette"], "asset colors")) <=
                set(colors(rindex[asset["region"]]["palette"], "regional colors")),
                "asset palette drifts from region theme")
        text(asset["spec"], "AI asset specification", 3000)
        text(asset["identity"], "original distinguishing asset features", 400)
        require(asset["rights"] in ("original_reviewed", "review_required"),
                "originality and rights status must be explicit")
        for ref in array(asset["references"], 30, "asset provenance"):
            require(type(ref) is str and SHA.fullmatch(ref),
                    "asset source citation requires reviewed content hash")
    ids(assets, "asset")
    for source in array(doc["inspiration"], 256, "knowledge inspirations"):
        shape(source, ("id", "digest", "license", "usage", "reviewed"),
              "inspiration provenance")
        ident(source["id"], "source")
        require(type(source["digest"]) is str and SHA.fullmatch(source["digest"]),
                "inspiration requires source provenance digest")
        text(source["license"], "source license", 160)
        text(source["usage"], "high-level transformative design notes", 400)
        require(type(source["reviewed"]) is bool,
                "inspiration needs a human rights-review signal")
    require(type(doc["rights_reviewed"]) is bool, "rights review signal required")
    if doc["phase"] == "design":
        require(doc["rights_reviewed"] is True and
                all(x["reviewed"] for x in doc["inspiration"]),
                "final design needs signed source-rights review")
        require(any(a["rights"] == "original_reviewed" for a in assets),
                "design needs at least one original approved creative asset")
    return doc


def story_scene_template(bible, *, sequence=1, chapter=None, act=1, scene=1):
    validate_story_bible(bible)
    return {"schema": SCENE, "bible_digest": bible["digest"],
            "sequence": sequence, **({"chapter": chapter} if chapter is not None else {}),
            "act": act, "scene": scene,
            "prior_digest": None, "title": "", "region": None,
            "cast": [], "looks": [], "assets": [], "beats": [],
            "dialogue": [], "interactions": [], "events": [], "digest": None}


def scene_path(doc):
    number(doc["act"], 1, 1000, "act index")
    number(doc["scene"], 1, 999999, "scene within act")
    if "chapter" in doc:
        number(doc["chapter"], 1, 100, "chapter index")
        return (f"story/chapters/chapter_{doc['chapter']:03d}/"
                f"acts/act_{doc['act']:04d}/scene_{doc['scene']:06d}.json")
    return f"story/scenes/act_{doc['act']:04d}/scene_{doc['scene']:06d}.json"


def _check_scene(bible, doc, previous, history, state, indexes):
    signed(doc, SCENE, ("bible_digest", "sequence", "act", "scene",
                        "prior_digest", "title", "region", "cast", "looks",
                        "assets", "beats", "dialogue", "interactions", "events")
           + (("chapter", "storytelling") if "chapter" in doc else ())
           + (("assurance",) if "assurance" in doc else ()))
    require(bible["phase"] == "design" and bible["rights_reviewed"],
            "no production scene before story, cast and design review")
    require(doc["bible_digest"] == bible["digest"],
            "scene tied to outdated story/cast/world bible")
    number(doc["sequence"], 1, MAX_SCENES, "ordered global scene")
    number(doc["act"], 1, bible["story"]["planned_acts"], "act number")
    number(doc["scene"], 1, 999999, "scene number")
    if "chapter" in doc:
        number(doc["chapter"], 1, 100, "chapter number")
        require(doc["chapter"] == (doc["act"]-1)//10+1,
                "chapter must contain exactly ten consecutive global acts")
    require(doc["sequence"] == (previous["sequence"]+1 if previous else 1),
            "missing scene in sequential story history")
    require(doc["prior_digest"] == (previous["digest"] if previous else None),
            "scene did not bookmark exact preceding source")
    if previous:
        require((doc["act"], doc["scene"]) >
                (previous["act"], previous["scene"]), "out-of-order original scene")
    text(doc["title"], "original scene title", 180)
    place = doc["region"]
    require(place in indexes["regions"], "scene region does not exist in bible")
    cast = array(doc["cast"], 256, "scene cast", 1)
    require(len(cast) == len(set(cast)) and
            all(w in indexes["characters"] for w in cast),
            "scene introduces unknown or duplicated actor")
    looks = array(doc["looks"], 256, "character identity anchors")
    require(len(looks) == len(cast), "every cast member needs visual continuity anchor")
    changed = {k: dict(v) for k, v in state.items()}
    newids = set()
    for event in array(doc["events"], 256, "causal events"):
        shape(event, ("id", "actor", "kind", "summary", "references", "changes"),
              "story event")
        ref = ident(event["id"], "world event")
        require(ref not in history and ref not in newids,
                "global event bookmark reused")
        require(event["actor"] in cast, "event requires a real onsite actor")
        text(event["kind"], "event type", 80)
        text(event["summary"], "event motivation", 2000)
        for before in array(event["references"], 50, "event cause references"):
            require(before in history | newids,
                    "world event cannot rely on missing prior cause")
        for change in array(event["changes"], 40, "character state changes"):
            shape(change, ("character", "field", "previous", "value", "reason"),
                  "auditable cast state transition")
            who = change["character"];key = change["field"]
            require(who in cast and key in FIELDS,
                    "only current scene cast state can be updated")
            text(change["reason"], "reason for a state transition", 400)
            require(type(change["previous"]) is str and
                    changed[who][key] == change["previous"],
                    "character contradicts previous canonical state")
            next_value = text(change["value"], "changed character state", 150)
            if key == "status":
                require(next_value in ("alive", "missing", "dead"), "unknown life state")
            if key == "location":
                require(next_value in indexes["regions"], "travel to nonexistent region")
            changed[who][key] = next_value
        newids.add(ref)
    seen = set()
    for row in looks:
        shape(row, ("character", "appearance_digest", "palette", "outfit"),
              "character visual rendering contract")
        who = row["character"]
        require(who in cast and who not in seen,
                "unapproved or repeated appearance")
        seen.add(who)
        approved = indexes["characters"][who]["appearance"]
        require(row["appearance_digest"] == digest(approved) and
                colors(row["palette"], "scene character palette") ==
                colors(approved["palette"], "canonical character color") and
                row["outfit"] == changed[who]["outfit"],
                "character look/color/outfit contradicted scene-one canon")
    require(seen == set(cast), "cast lacks a verified look")
    for who in cast:
        require(changed[who]["location"] == place,
                "character location requires authored travel before a scene")
        require(changed[who]["status"] != "dead",
                "dead cast cannot appear without a causal resurrection event")
    seen_assets = set()
    for row in array(doc["assets"], 256, "onscreen original assets"):
        shape(row, ("asset", "region", "palette"), "scene-specific asset reference")
        key = row["asset"]
        require(key in indexes["assets"] and key not in seen_assets,
                "asset reference unknown or duplicated")
        seen_assets.add(key)
        approved = indexes["assets"][key]
        require(approved["rights"] == "original_reviewed",
                "unreviewed asset cannot enter AI-generation instructions")
        require(row["region"] == place == approved["region"] and
                colors(row["palette"], "scene asset colors") ==
                colors(approved["palette"], "asset palette"),
                "asset/theme/color mismatch with source scene or region")
    for name, rows in (("dialogue", doc["dialogue"]),
                       ("interactions", doc["interactions"]),
                       ("beats", doc["beats"])):
        array(rows, 512, name, 1 if name == "beats" else 0)
        for item in rows:
            keys = (("id", "speaker", "listener", "text", "intent", "references")
                    if name == "dialogue" else
                    ("id", "actor", "target", "kind", "summary", "references")
                    if name == "interactions" else ("id", "summary", "references"))
            shape(item, keys, name)
            key = ident(item["id"], name + " bookmark")
            require(key not in history and key not in newids,
                    "historical conversation or beat key reused")
            if name != "beats":
                x, y = ((item["speaker"], item["listener"]) if name == "dialogue"
                        else (item["actor"], item["target"]))
                require(x in cast and y in cast and x != y,
                        "interaction/dialogue must name two approved scene characters")
            text(item["text"] if name == "dialogue" else item["summary"],
                 name + " authored content", 3000)
            if name == "dialogue":
                text(item["intent"], "voice direction", 200)
            if name == "interactions":
                text(item["kind"], "relationship change", 120)
            for prior in array(item["references"], 50, "story memory references"):
                require(prior in history | newids,
                        "Jeeves cannot remember an event that never occurred")
            newids.add(key)
    require(len(json.dumps(doc).encode("utf-8")) <= 256000,
            "original source scene exceeds reviewable source size")
    return changed, newids


def verify_story_history(bible, scenes):
    """Complete deterministic projection of reviewed scene sources."""
    validate_story_bible(bible)
    require(type(scenes) in (list, tuple) and len(scenes) <= MAX_SCENES,
            "bounded full story source history required")
    ix = {"characters": ids(bible["characters"], "characters"),
          "regions": ids(bible["regions"], "regions"),
          "assets": ids(bible["assets"], "assets")}
    state = {who: dict(row["state"]) for who, row in ix["characters"].items()}
    known = set()
    by_character = defaultdict(list)
    by_pair = defaultdict(list)
    by_asset = defaultdict(list)
    by_region = defaultdict(list)
    bookmarks = {}
    previous = None
    for doc in scenes:
        state, added = _check_scene(bible, doc, previous, known, state, ix)
        for who in doc["cast"]:
            by_character[who].append(doc["sequence"])
        for kind in ("dialogue", "interactions"):
            for row in doc[kind]:
                x, y = ((row["speaker"], row["listener"]) if kind == "dialogue"
                        else (row["actor"], row["target"]))
                pair = ":".join(sorted((x, y)))
                by_pair[pair].append({"ref": row["id"], "sequence": doc["sequence"],
                                     "kind": kind, "scene_digest": doc["digest"]})
        for ref in added:
            bookmarks[ref] = {"sequence": doc["sequence"],
                              "path": scene_path(doc),
                              "scene_digest": doc["digest"]}
        for item in doc["assets"]:
            by_asset[item["asset"]].append(doc["sequence"])
        by_region[doc["region"]].append(doc["sequence"])
        known.update(added);previous = doc
    result = {"schema": "skeleton.game_builder.story_history_index.v1",
              "bible_digest": bible["digest"], "scene_count": len(scenes),
              "head_digest": previous["digest"] if previous else None,
              "characters": dict(sorted(by_character.items())),
              "pairs": dict(sorted(by_pair.items())),
              "assets": dict(sorted(by_asset.items())),
              "regions": dict(sorted(by_region.items())),
              "bookmarks": dict(sorted(bookmarks.items())),
              "current_state": dict(sorted(state.items())),
              "neural_weights_modified": False, "native_game_built": False}
    return {**result, "digest": digest(result)}


def verify_story_scene(bible, history, candidate):
    old = verify_story_history(bible, history)
    verify_story_history(bible, [*history, candidate])
    return {"valid": True, "path": scene_path(candidate),
            "candidate_digest": candidate["digest"], "prior_index": old["digest"],
            "human_source_review_required": True}


def jeeves_story_brief(bible, history, *, cast, region, request, max_bookmarks=48):
    """Evidence-grounded model context, not an LLM inference call."""
    index = verify_story_history(bible, history)
    text(request, "Jeeves creative user request", 4000)
    array(cast, 16, "requested scene cast", 1)
    number(max_bookmarks, 1, 100, "conversation context page")
    characters = ids(bible["characters"], "characters")
    regions = ids(bible["regions"], "regions")
    require(region in regions and all(c in characters for c in cast),
            "Jeeves conversation must reference authored scene entities")
    pairs = [entry for pair, values in index["pairs"].items()
             if any(w in pair.split(":") for w in cast) for entry in values]
    pairs.sort(key=lambda x: (x["sequence"], x["ref"]))
    approved_assets = [a for a in bible["assets"]
                       if a["region"] == region and a["rights"] == "original_reviewed"]
    result = {"schema": "skeleton.game_builder.jeeves_story_context.v1",
              "project": bible["project"], "requested_creation": request,
              "phase": "scene_by_scene", "next_sequence": index["scene_count"] + 1,
              "bible_digest": bible["digest"], "head_digest": index["head_digest"],
              "premise": bible["story"], "world_laws": bible["world"]["laws"],
              "region_canon": regions[region], "character_canon":
                  [characters[c] for c in cast],
              "current_states": {c: index["current_state"][c] for c in cast},
              "regional_assets": approved_assets[:128],
              "pair_history": pairs[-max_bookmarks:],
              "total_pair_history": len(pairs),
              "pair_history_complete_in_brief": len(pairs) <= max_bookmarks,
              "full_history_index_digest": index["digest"],
              "full_bookmarks_resolvable_in_index": True,
              "required_gates": ["scene_chain", "NPC_relationships", "visual_identity",
                                 "regional_palette", "causal_events",
                                 "rights_provenance", "scene_state_changes"],
              "model_inference_performed": False,
              "weights_trained": False, "source_changes_approved": False}
    return {**result, "digest": digest(result)}
