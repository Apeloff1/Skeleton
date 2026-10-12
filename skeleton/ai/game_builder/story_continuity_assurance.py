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

CONTRACT = "skeleton.game_builder.production_consistency_contract.v2"
RECEIPT = "skeleton.game_builder.scene_confirmation_receipt.v2"
CHAPTER_TARGET = 100
ACT_TARGET = 1000
SCENE_TARGET = 9999
EMOTIONS = frozenset(("neutral","joy","sadness","fear","anger",
                      "surprise","disgust","concern","determined","listening"))
QC_GATES = (
    "original_world_bible", "locked_voice_identity", "voice_source_fingerprint",
    "facial_geometry", "dialogue_expression_by_intent", "historical_wardrobe",
    "scene_items_and_ownership", "causal_item_transfers", "region_style",
    "region_palette", "cast_and_event_causality", "prior_scene_digest",
    "prior_confirmation_receipt", "full_historical_reparse", "reviewed_rights",
    "chapter_highlighters", "suspense_and_pacing", "prologue_interlude_logic",
    "chapter_ending_closure", "chapter_scoped_model_context",
)


def contract_template(bible):
    """Blank reviewed stage-three plan. Missing fields never receive fake proof."""
    validate_story_bible(bible)
    require(bible["phase"] == "design", "approved character and world design required")
    return {
        "schema": CONTRACT, "project": bible["project"],
        "bible_digest": bible["digest"], "chapter_target": CHAPTER_TARGET,
        "act_target": ACT_TARGET,
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
    signed(contract, CONTRACT, ("project","bible_digest","chapter_target","act_target",
                               "scene_target","characters","regions","items",
                               "human_design_reviewed"))
    require(bible["story"].get("planned_chapters") == CHAPTER_TARGET and
            bible["story"]["planned_acts"] == ACT_TARGET,
            "100-chapter and 1000-act signed story outline required")
    require(contract["project"] == bible["project"] and
            contract["bible_digest"] == bible["digest"],
            "production assurance must lock the exact reviewed world")
    require(contract["chapter_target"] == CHAPTER_TARGET and
            contract["act_target"] == ACT_TARGET and
            contract["scene_target"] == SCENE_TARGET,
            "100 chapters, 1000 acts and exactly 9999 scenes are mandatory")
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
        require([line.get("line_id") for line in row["dialogue_expressions"]] ==
                [utterance["id"] for utterance in utterances],
                "facial/emotional cues must follow the actual spoken-line order")
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
        witness = next((event for event in scene["events"]
                        if event["id"] == move["event_ref"]), None)
        require(move["from_owner"] == owned[key] and
                (move["to_owner"] in identities or move["to_owner"] == "world") and
                (move["from_owner"] == "world" or
                 move["from_owner"] in scene["cast"]) and
                (move["to_owner"] == "world" or
                 move["to_owner"] in scene["cast"]) and
                witness is not None and witness["kind"] == "item_transfer" and
                key in witness["summary"].casefold() and
                (move["from_owner"] == "world" or
                 witness["actor"] == move["from_owner"]),
                "item transfer needs an explicit onstage authored transfer event")
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
    required_items = {key for key, item in items.items()
                      if item["asset"] in scene_item_ids}
    require(required_items == observed,
            "every historical costume prop/item shown in the scene must be accounted for")
    return owned


def _receipt(contract, scene, observations, previous_receipt,
             previous_state, next_state, previous_item_state,
             next_items, prefix_digest):
    """Single-stage confirmation bound to all preceding verified receipts."""
    body = {
        "schema": RECEIPT, "contract_digest": contract["digest"],
        "sequence": scene["sequence"], "chapter": scene["chapter"],
        "act": scene["act"],
        "scene": scene["scene"],
        "scene_source_digest": _source_scene_digest(scene),
        "previous_receipt_digest": previous_receipt,
        "historical_chain_digest_before": prefix_digest,
        "character_state_before": digest(previous_state),
        "character_state_after": digest(next_state),
        "item_state_before": digest(previous_item_state),
        "item_state_after": digest(next_items),
        "observations": observations,
        "passed_checks": list(QC_GATES),
        "entire_source_chain_reparsed": True,
        "actual_acoustic_voice_verified": False,
        "actual_rendered_face_verified": False,
        "human_source_approval_required": True,
    }
    return {**body, "digest": digest(body)}


def _advance_characters(before, scene):
    """Replay reviewed state transitions; source history validates their cause."""
    state = {name: dict(value) for name, value in before.items()}
    for event in scene["events"]:
        for change in event["changes"]:
            who = change["character"]
            key = change["field"]
            require(state[who][key] == change["previous"],
                    "historic character state differs from witnessed predecessor")
            state[who][key] = change["value"]
    return state


def _history_root(bible, contract):
    return digest({"bible": bible["digest"], "contract": contract["digest"],
                   "stage": 0})


def _advance_root(root, scene, receipt):
    return digest({"previous_history": root, "source": scene["digest"],
                   "confirmation": receipt["digest"]})


def verify_production_history(bible, contract, scenes):
    """O(N) full historical source replay plus O(N) receipt re-verification.

    Each *new* scene also triggers a fresh full replay from stage one. That is
    deliberate. No check trusts a cached projection or producer's assertion.
    """
    validate_contract(contract, bible)
    require(type(scenes) in (list, tuple) and len(scenes) <= SCENE_TARGET,
            "reviewable 9999-stage history required")
    index = verify_story_history(bible, scenes)
    from .story_chapter_context import validate_chapter_history
    chapters = validate_chapter_history(
        scenes,require_final=len(scenes)==SCENE_TARGET)
    character_state = {x["id"]: dict(x["state"]) for x in bible["characters"]}
    item_state = _review_state(contract)
    previous_receipt = None
    root = _history_root(bible, contract)
    visited_acts = set()
    visited_chapters = set()
    previous_scene = None
    for stage in scenes:
        number(stage["scene"], 1, 9999, "one scene number within an act")
        require(stage.get("chapter") == (stage["act"]-1)//10+1,
                "strict source must link chapter and global act")
        if previous_scene is None:
            require((stage["act"],stage["scene"]) == (1,1),
                    "stage one must start at act 1 scene 1")
        elif stage["act"] == previous_scene["act"]:
            require(stage["scene"] == previous_scene["scene"] + 1,
                    "no missing scene number inside the original act")
        else:
            require(stage["act"] == previous_scene["act"] + 1 and
                    stage["scene"] == 1,
                    "each new act must begin at scene one without skipping acts")
        receipt = stage.get("assurance")
        require(type(receipt) is dict, "stage is missing its own identity/QC receipt")
        before = character_state
        after = _advance_characters(before, stage)
        new_items = _check_attestation(
            bible, contract, stage, before, after, item_state,
            previous_receipt, receipt.get("observations"))
        expected = _receipt(contract, stage, receipt["observations"],
                            previous_receipt, before, after,
                            item_state, new_items, root)
        require(expected == receipt,
                "full history reparse rejects forged or drifting stage receipt")
        root = _advance_root(root, stage, receipt)
        item_state = new_items
        character_state = after
        previous_receipt = receipt["digest"]
        visited_acts.add(stage["act"])
        visited_chapters.add(stage["chapter"])
        previous_scene = stage
    require(character_state == index["current_state"],
            "independent cast state projection disagrees with replay")
    result = {
        "schema": "skeleton.game_builder.production_history_confirmation.v1",
        "bible_digest": bible["digest"], "contract_digest": contract["digest"],
        "accepted_scenes": len(scenes), "planned_scenes": SCENE_TARGET,
        "planned_chapters": CHAPTER_TARGET, "planned_acts": ACT_TARGET,
        "current_chapter": chapters["current_chapter"],
        "indexed_plot_highlighters": len(chapters["highlights"]),
        "closed_chapters": len(chapters["closed_chapters"]),
        "fully_completed": len(scenes) == SCENE_TARGET and
                           len(visited_acts) == ACT_TARGET and
                           len(visited_chapters) == CHAPTER_TARGET,
        "verified_source_head": index["head_digest"],
        "verified_receipt_head": previous_receipt,
        "verified_chain_head": root,
        "current_character_state": character_state,
        "current_item_owners": item_state,
        "all_prior_scenes_reparsed": True,
        "scene_order_proved": True, "deviations_approved": 0,
        "actual_voice_audio_verification_completed": False,
        "actual_rendered_facial_matching_completed": False,
    }
    return {**result, "digest": digest(result)}


def seal_production_scene(bible, contract, history, candidate, observations):
    """Certify exactly the next source scene; never manufacture scene content."""
    validate_contract(contract, bible)
    require(type(candidate) is dict and "assurance" not in candidate,
            "producer may not supply a self-certified assurance receipt")
    prior = verify_production_history(bible, contract, history)
    require(len(history) < SCENE_TARGET and
            candidate.get("sequence") == len(history) + 1,
            "one scene at a time, in exact 1..9999 order")
    pending = {k: v for k, v in candidate.items() if k != "digest"}
    plain = sign(pending, SCENE)
    # The full replay checks narrative continuity, actor facts, palette,
    # scene ordering, event causality and immutable historical world source.
    next_index = verify_story_history(bible, [*history, plain])
    from .story_chapter_context import validate_chapter_history
    validate_chapter_history([*history, plain],
                             require_final=len(history)+1==SCENE_TARGET)
    before = prior["current_character_state"]
    after = next_index["current_state"]
    current_items = prior["current_item_owners"]
    next_items = _check_attestation(
        bible, contract, plain, before, after, current_items,
        prior["verified_receipt_head"], observations)
    receipt = _receipt(contract, plain, observations,
                       prior["verified_receipt_head"], before, after,
                       current_items, next_items, prior["verified_chain_head"])
    sealed = sign({**pending, "assurance": receipt}, SCENE)
    verify_production_history(bible, contract, [*history, sealed])
    return sealed


def confirm_stage(workspace, project):
    """Independently verify every previously approved scene and chained receipt."""
    from .story_workspace import load_story_workspace, load_continuity_contract
    bible, scenes, _ = load_story_workspace(workspace, project)
    require(bible is not None, "reviewed story, cast and world source required")
    contract = load_continuity_contract(workspace, project)
    require(contract is not None, "reviewed 100-act continuity contract required")
    return verify_production_history(bible, contract, scenes)
