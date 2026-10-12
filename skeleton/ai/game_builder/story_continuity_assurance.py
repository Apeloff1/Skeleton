"""High-assurance scene-production contracts for Jeeves' original game builder.

An immutable character/region/item specification is pinned before scene one.
One scene at a time receives an independent, hash-linked receipt. Both authoring
and source replay reject identity drift, unsupported wardrobe/item moves and
facial expressions contradicting an explicitly authored dialogue intent.

This verifies *source manifests and declared media fingerprints*, not actual
voice acoustics or facial likeness in rendered video. The audio/vision model
verifiers must run separately before release-grade certification.
"""
from __future__ import annotations

from copy import deepcopy
from .story_canon_fabric import (
    BIBLE, SCENE, StoryCanonError, colors, digest, ident, ids, number,
    require, shape, signed, sign, text, validate_story_bible,
    verify_story_history,
)

CONTRACT = "skeleton.game_builder.production_consistency_contract.v1"
RECEIPT = "skeleton.game_builder.scene_confirmation_receipt.v1"
ACT_TARGET = 100
SCENE_TARGET = 9999
EMOTIONS = frozenset(("neutral","joy","sadness","fear","anger",
                      "surprise","disgust","concern","determined","listening"))
QC_GATES = (
    "original_world_bible", "locked_voice_identity", "voice_source_fingerprint",
    "facial_geometry", "dialogue_expression_by_intent", "historical_wardrobe",
    "scene_items_and_ownership", "causal_item_transfers", "region_style",
    "region_palette", "cast_and_event_causality", "prior_scene_digest",
    "prior_confirmation_receipt", "full_historical_reparse", "reviewed_rights",
)


def contract_template(bible):
    """Blank reviewed stage-three plan. Missing fields never receive fake proof."""
    validate_story_bible(bible)
    require(bible["phase"] == "design", "approved character and world design required")
    return {
        "schema": CONTRACT, "project": bible["project"],
        "bible_digest": bible["digest"], "act_target": ACT_TARGET,
        "scene_target": SCENE_TARGET,
        "characters": [{
            "id": row["id"], "voice_id": "", "voice_asset_sha256": "",
            "voice_style": "", "language": "", "accent": "",
            "face_id": "", "facial_geometry": {
                "eye_shape": "", "nose": "", "jaw": "", "mouth": "",
                "skin_details": ""}, "expressions": [],
            "wardrobe": [{"id": "", "outfit": row["appearance"]["outfit"],
                          "palette": row["appearance"]["palette"],
                          "fabric": "", "details": ""}],
        } for row in bible["characters"]],
        "regions": [{
            "id": row["id"], "style_id": "", "era": "",
            "palette": row["palette"], "architecture": row["architecture"],
            "materials": row["materials"], "style_notes": "",
        } for row in bible["regions"]],
        "items": [],
        "human_design_reviewed": False,
        "digest": None,
    }


def validate_contract(contract, bible):
    validate_story_bible(bible)
    signed(contract, CONTRACT, ("project","bible_digest","act_target",
                               "scene_target","characters","regions","items",
                               "human_design_reviewed"))
    require(contract["project"] == bible["project"] and
            contract["bible_digest"] == bible["digest"],
            "production assurance must lock the exact reviewed world")
    require(contract["act_target"] == ACT_TARGET and
            contract["scene_target"] == SCENE_TARGET,
            "100 acts and exactly 9999 planned scenes are mandatory")
    require(contract["human_design_reviewed"] is True,
            "design/voice identity attestation must be explicitly reviewed")
    approved = ids(bible["characters"], "approved cast")
    characters = {}
    for item in contract["characters"] if type(contract["characters"]) is list else []:
        shape(item, ("id","voice_id","voice_asset_sha256","voice_style",
                     "language","accent","face_id","facial_geometry",
                     "expressions","wardrobe"), "locked character identity")
        who = ident(item["id"], "voice/cast")
        require(who in approved and who not in characters,
                "voice identity cannot introduce or duplicate characters")
        for field in ("voice_id","face_id"):
            ident(item[field], field)
        require(type(item["voice_asset_sha256"]) is str and
                len(item["voice_asset_sha256"]) == 64 and
                all(ch in "0123456789abcdef" for ch in item["voice_asset_sha256"]),
                "immutable original voice master needs a real 64-digit SHA-256")
        for field in ("voice_style","language","accent"):
            text(item[field], "original " + field, 250)
        facial = shape(item["facial_geometry"],
                       ("eye_shape","nose","jaw","mouth","skin_details"),
                       "persistent facial structure")
        for key in facial:
            text(facial[key], "facial identity " + key, 250)
        rules = {}
        for entry in item["expressions"] if type(item["expressions"]) is list else []:
            shape(entry, ("intent","expression"), "approved facial cue")
            text(entry["intent"], "authored dialogue intent", 200)
            require(entry["expression"] in EMOTIONS,
                    "unrecognized facial expression")
            require(entry["intent"] not in rules, "duplicate emotional intent")
            rules[entry["intent"]] = entry["expression"]
        require(rules, "every character needs a mapped dialogue/face expression")
        wardrobe = {}
        for row in item["wardrobe"] if type(item["wardrobe"]) is list else []:
            shape(row, ("id","outfit","palette","fabric","details"),
                  "original detailed clothing record")
            key = ident(row["id"], "outfit")
            require(key not in wardrobe, "duplicate outfit identity")
            text(row["outfit"], "named historical outfit", 250)
            text(row["fabric"], "cloth and material", 250)
            text(row["details"], "clothing features", 400)
            approved_palette = colors(approved[who]["appearance"]["palette"],
                                      "character palette")
            require(colors(row["palette"], "outfit colors") == approved_palette,
                    "wardrobe variant cannot replace canonical original character color")
            wardrobe[key] = row
        require(wardrobe and
                any(w["outfit"] == approved[who]["state"]["outfit"]
                    for w in wardrobe.values()),
                "character needs an original canonical starting outfit")
        characters[who] = item
    require(set(characters) == set(approved), "every character needs one immutable voice and face")
    region_source = ids(bible["regions"], "world regions")
    region_map = {}
    for row in contract["regions"] if type(contract["regions"]) is list else []:
        shape(row, ("id","style_id","era","palette",
                    "architecture","materials","style_notes"),
              "period-sensitive region style")
        key = ident(row["id"], "styled region")
        ident(row["style_id"], "immutable regional style")
        require(key in region_source and key not in region_map,
                "style cannot introduce or duplicate original regions")
        for field in ("era","architecture","style_notes"):
            text(row[field], "region " + field, 500)
        require(colors(row["palette"], "region palette") ==
                colors(region_source[key]["palette"], "source region palette"),
                "historic regional palette mismatch")
        require(row["architecture"] == region_source[key]["architecture"]
                and row["materials"] == region_source[key]["materials"],
                "historic architecture or materials changed without a new approved world")
        region_map[key] = row
    require(set(region_map) == set(region_source),
            "every original region needs a locked thematic style")
    asset_source = ids(bible["assets"], "original assets")
    items = {}
    require(type(contract["items"]) is list and len(contract["items"]) <= 2048,
            "bounded canonical item inventory required")
    for item in contract["items"]:
        shape(item, ("id","asset","initial_owner","details","style_id"),
              "original item identity")
        item_id = ident(item["id"], "item")
        asset = item["asset"]
        require(item_id not in items and asset in asset_source and
                asset_source[asset]["kind"] in ("item","prop"),
                "item must be an original approved asset")
        require(asset_source[asset]["rights"] == "original_reviewed",
                "unreviewed equipment cannot enter scene production")
        require(item["initial_owner"] == "world" or item["initial_owner"] in characters,
                "item owner must be world or an actual character")
        text(item["details"], "persistent item detailing", 400)
        require(item["style_id"] == region_map[asset_source[asset]["region"]]["style_id"],
                "item inherits exact original regional style")
        items[item_id] = item
    return contract


def _source_scene_digest(scene):
    """Prevents a recursive receipt -> scene checksum dependency."""
    return digest({key:value for key,value in scene.items()
                   if key not in ("digest","assurance")})


def _review_state(contract):
    return {item["id"]: item["initial_owner"] for item in contract["items"]}


def _check_attestation(bible, contract, scene, history_state, post_state,
                       item_state, previous_receipt, source):
    identities = ids(contract["characters"], "locked cast")
    regions = ids(contract["regions"], "locked regions")
    items = ids(contract["items"], "locked items")
    attributes = shape(source, ("cast","region","items","transfers"),
                       "scene-level observed evidence")
    seen = set()
    cast = attributes["cast"]
    require(type(cast) is list and len(cast) == len(scene["cast"]),
            "every onscreen character requires an independent visual/voice record")
    for row in cast:
        shape(row, ("character","voice_id","voice_asset_sha256",
                    "face_id","facial_geometry_digest","outfit_id",
                    "outfit_palette","dialogue_expressions"),
              "onscreen immutable character observations")
        who = row["character"]
        require(who in scene["cast"] and who not in seen,
                "onscreen character identity missing or duplicated")
        seen.add(who)
        identity = identities[who]
        require(row["voice_id"] == identity["voice_id"] and
                row["voice_asset_sha256"] == identity["voice_asset_sha256"],
                "VOICE REPLACEMENT: immutable voice ID or source fingerprint drift")
        require(row["face_id"] == identity["face_id"] and
                row["facial_geometry_digest"] == digest(identity["facial_geometry"]),
                "FACIAL IDENTITY DRIFT: eyes, nose, mouth or jaw changed")
        clothes = ids(identity["wardrobe"], "historical wardrobe")
        require(row["outfit_id"] in clothes and
                clothes[row["outfit_id"]]["outfit"] == post_state[who]["outfit"],
                "unexplained historical clothing substitution")
        require(colors(row["outfit_palette"], "onscreen outfit palette") ==
                colors(clothes[row["outfit_id"]]["palette"], "locked outfit palette"),
                "clothing coloration differs from approved visual design")
        utterances = [speech for speech in scene["dialogue"] if speech["speaker"] == who]
        require(type(row["dialogue_expressions"]) is list and
                len(row["dialogue_expressions"]) == len(utterances),
                "every audible line must have a verified matching face expression")
        rule = {x["intent"]:x["expression"] for x in identity["expressions"]}
        seen_lines = set()
        for line in row["dialogue_expressions"]:
            shape(line, ("line_id","intent","expression"),
                  "line-by-line facial/voice synchronization intent")
            matching = next((speech for speech in utterances
                             if speech["id"] == line["line_id"]),None)
            require(matching is not None and line["line_id"] not in seen_lines,
                    "missing or duplicated historic dialogue line")
            seen_lines.add(line["line_id"])
            require(line["intent"] == matching["intent"] and
                    rule.get(matching["intent"]) == line["expression"],
                    "facial expression contradicts the authored line's emotional intent")
    require(seen == set(scene["cast"]), "cast identity/voice coverage incomplete")
    region = shape(attributes["region"],
                   ("id","style_id","era","palette","architecture"),
                   "approved scenic period and theme")
    expected = regions[scene["region"]]
    require(region["id"] == scene["region"] and
            region["style_id"] == expected["style_id"] and
            region["era"] == expected["era"] and
            region["architecture"] == expected["architecture"] and
            colors(region["palette"], "observed regional colors") ==
            colors(expected["palette"], "historic regional colors"),
            "the scene deviates from its original period, architecture or regional palette")
    scene_item_ids = {entry["asset"] for entry in scene["assets"]}
    require(type(attributes["transfers"]) is list and len(attributes["transfers"]) <= 128,
            "finite audited item transfers required")
    owned = dict(item_state)
    event_ids = {event["id"] for event in scene["events"]}
    touched = set()
    for move in attributes["transfers"]:
        shape(move, ("item","from_owner","to_owner","event_ref","reason"),
              "historical item ownership transfer")
        key = move["item"]
        require(key in items and key not in touched,
                "item ownership may be updated once per scene with evidence")
        touched.add(key)
        require(move["from_owner"] == owned[key] and
                (move["to_owner"] in identities or move["to_owner"] == "world") and
                move["event_ref"] in event_ids,
                "unrecorded item teleportation, duplication or ownership transfer")
        text(move["reason"], "item change explanation", 300)
        owned[key] = move["to_owner"]
    observed = set()
    require(type(attributes["items"]) is list and len(attributes["items"]) <= 256,
            "bounded observed original inventory required")
    for item in attributes["items"]:
        shape(item, ("id","owner","asset_digest","style_id","palette"),
              "original equipment appearance")
        key = item["id"]
        require(key in items and key not in observed,
                "observed equipment has no unique original source")
        observed.add(key)
        source_item = items[key]
        asset = next(x for x in bible["assets"] if x["id"] == source_item["asset"])
        require(source_item["asset"] in scene_item_ids,
                "item shown without source-reviewed scene asset reference")
        require(item["owner"] == owned[key] and
                item["asset_digest"] == digest(asset) and
                item["style_id"] == source_item["style_id"] and
                colors(item["palette"], "observed item palette") ==
                colors(asset["palette"], "approved equipment color"),
                "historic item appearance or possession drift")
    return owned


def _state_after(bible, scene_history):
    return verify_story_history(bible, scene_history)["current_state"]


def _receipt(contract,scene,observations,previous_receipt,previous_state,next_state,
             previous_item_state,next_items,index_digest):
    body={
        "schema": RECEIPT, "contract_digest": contract["digest"],
        "sequence": scene["sequence"],"act":scene["act"],"scene":scene["scene"],
        "scene_source_digest":_source_scene_digest(scene),
        "previous_receipt_digest":previous_receipt,
        "historical_index_digest_before":index_digest,
        "character_state_before":digest(previous_state),
        "character_state_after":digest(next_state),
        "item_state_before":digest(previous_item_state),
        "item_state_after":digest(next_items),
        "observations": observations,
        "passed_checks":list(QC_GATES),
        "all_source_history_reparsed":True,
        "model_has_perfect_infinite_memory":False,
        "voice_audio_acoustically_tested":False,
        "visual_facial_geometry_render_tested":False,
        "human_commit_required":True,
    }
    return {**body,"digest":digest(body)}


def verify_production_history(bible,contract,scenes):
    """Full source-chain replay and receipt/identity/wardrobe/inventory validation."""
    validate_contract(contract,bible)
    require(type(scenes) in (list,tuple) and len(scenes)<=SCENE_TARGET,
            "original 9999-stage sequence is bounded")
    stripped=[{k:v for k,v in scene.items() if k!="assurance"}
              for scene in scenes]
    # Independently verify the *entire* source before any receipt can pass.
    index=verify_story_history(bible,stripped)
    character_state={x["id"]:dict(x["state"]) for x in bible["characters"]}
    item_state=_review_state(contract)
    previous=None
    previous_receipt=None
    # Source index before each scene is hash linked; this reconstruction is
    # intentionally exhaustive and cannot skip early scenes.
    prior_scenes=[]
    for entry,plain in zip(scenes,stripped):
        receipt=entry.get("assurance")
        require(type(receipt) is dict, "scene missing required confirmation receipt")
        before_index=verify_story_history(bible,prior_scenes)
        prior_scenes.append(plain)
        stage_index=verify_story_history(bible,prior_scenes)
        next_state=stage_index["current_state"]
        changed_items=_check_attestation(
            bible,contract,entry,character_state,next_state,item_state,
            previous_receipt,receipt.get("observations"))
        expected=_receipt(contract,entry,receipt["observations"],
                         previous_receipt,character_state,next_state,
                         item_state,changed_items,before_index["digest"])
        require(receipt==expected,
                "historical stage receipt differs from independent full-source reparse")
        character_state=next_state
        item_state=changed_items
        previous_receipt=receipt["digest"]
        previous=entry
    result={
        "schema":"skeleton.game_builder.production_history_confirmation.v1",
        "bible_digest":bible["digest"],"contract_digest":contract["digest"],
        "accepted_scenes":len(scenes),"planned_scenes":SCENE_TARGET,
        "planned_acts":ACT_TARGET,
        "fully_completed":len(scenes)==SCENE_TARGET and
                          len({s["act"] for s in scenes})==ACT_TARGET,
        "verified_source_head":index["head_digest"],
        "verified_receipt_head":previous_receipt,
        "current_character_state":character_state,
        "current_item_owners":item_state,
        "all_prior_scenes_reparsed":True,
        "required_scene_order_proved":True,
        "no_deviation_accepted":True,
        "actual_voice_audio_verification_completed":False,
        "actual_rendered_facial_matching_completed":False,
    }
    return {**result,"digest":digest(result)}


def seal_production_scene(bible,contract,history,candidate,observations):
    """Only one next scene, after full 1..N previous history validation."""
    validate_contract(contract,bible)
    require(type(candidate) is dict and "assurance" not in candidate,
            "receipt signing requires clean original source scene")
    prior=verify_production_history(bible,contract,history)
    require(len(history)<SCENE_TARGET and candidate.get("sequence")==len(history)+1,
            "exactly one next stage can be authored, never a batch")
    pending={k:v for k,v in candidate.items() if k!="digest"}
    plain=sign(pending,SCENE)
    before=verify_story_history(bible,[{k:v for k,v in s.items() if k!="assurance"}
                                      for s in history])
    next_index=verify_story_history(bible,[
        *({k:v for k,v in s.items() if k!="assurance"} for s in history),plain])
    next_state=next_index["current_state"]
    current_items=prior["current_item_owners"]
    after_items=_check_attestation(
        bible,contract,plain,prior["current_character_state"],next_state,
        current_items,prior["verified_receipt_head"],observations)
    receipt=_receipt(contract,plain,observations,prior["verified_receipt_head"],
                     prior["current_character_state"],next_state,
                     current_items,after_items,before["digest"])
    sealed=sign({**pending,"assurance":receipt},SCENE)
    # Complete reparse is the final acceptance gate; never trust our fast path.
    verify_production_history(bible,contract,[*history,sealed])
    return sealed


def confirm_stage(workspace,project):
    """Evidence receipt for all reviewed stages, including empty opening stage."""
    from .story_workspace import load_story_workspace,load_continuity_contract
    bible,scenes,_=load_story_workspace(workspace,project)
    require(bible is not None,"foundation/cast/world approval required")
    contract=load_continuity_contract(workspace,project)
    require(contract is not None,"100-act continuity agreement not approved")
    return verify_production_history(bible,contract,scenes)
