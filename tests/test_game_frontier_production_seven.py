"""Seven further integrated original game-production subsystems.

All fixture evidence is from original typed game state; synthetically created
native logs explicitly prove replay parsing only, never Godot process origin.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import json
import sqlite3
import wave

import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionAction,ExpeditionEpisode,ExpeditionError,
    ExpeditionWeather,find_route,
)
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player
from skeleton.jeeves.game_frontier_expedition_narrative import original_expedition_story
from skeleton.jeeves.game_frontier_expedition_quests import original_quest_book
from skeleton.jeeves.game_frontier_expedition_session import (
    ProductionInput,ProductionSession,verify_production_session,
)
from skeleton.jeeves.game_frontier_expedition_plot_audit import prove_original_story_branches
from skeleton.jeeves.game_frontier_expedition_cinematics import (
    original_game_storyboard,camera_at,
)
from skeleton.jeeves.game_frontier_expedition_native_cinema_verify import (
    PREFIX,verify_native_cinema_frames,
)
from skeleton.jeeves.game_frontier_expedition_audio import original_world_score
from skeleton.jeeves.game_frontier_expedition_audio_mix import (
    AudioStem,make_original_ambient_layers,mix_original_stems,
    verify_original_mix,
)
from skeleton.jeeves.game_frontier_expedition_npcs import (
    NPCDesign,NPCEpisode,original_world_npcs,
)
from skeleton.jeeves.game_frontier_expedition_ecology import (
    EcologyPolicy,generate_original_ecology,simulate_ecology_frame,
    export_ecology_godot,
)
from skeleton.jeeves.game_frontier_expedition_dragon import (
    DragonLesson,observe_original_games,
)
from skeleton.jeeves.game_frontier_expedition_dragon_review import (
    adversarial_dragon_review,adversarial_attack_matrix,
)
from skeleton.jeeves.game_frontier_expedition_learning import (
    LearningEvidence,review_dragon_lesson,DragonKnowledgeStore,
)


def sources(*,seed=17,weather=None):
    world=author_archipelago(
        "seven_more_original_games","f"*64,
        ArchipelagoProfile(seed=seed,islands=6),
        **({"weather":weather} if weather is not None else {}),
    )
    player=original_campaign_player()
    story=original_expedition_story(world,"a"*64)
    quest=original_quest_book(ExpeditionEpisode(world,player),story)
    return world,player,story,quest


def gameplay_story_session():
    w,p,s,q=sources()
    session=ProductionSession(w,p,s,q)
    session.submit(ProductionInput("dialogue",scene_id="departure",choice_id="chart"))
    session.submit(ProductionInput("gameplay","travel","launch_updraft"))
    session.submit(ProductionInput("dialogue",scene_id="threshold",choice_id="remember"))
    path=find_route(w,p,w.destinations[0],start=session.game.position)
    for edge_id in path.edge_ids:
        session.submit(ProductionInput("gameplay","travel",edge_id))
    session.submit(ProductionInput("dialogue",scene_id="arrival",choice_id="archive"))
    return w,p,s,q,session


def test_production_session_plays_original_quest_dialogue_and_game_to_real_ending():
    w,p,s,q,session=gameplay_story_session()
    saved=session.snapshot()
    assert session.game.won
    assert session.ending()["ending_id"]=="cartographer"
    assert len(session.story.moments)==3
    assert len(session.quests.events)>=3
    assert saved["completed"]
    reviewed=verify_production_session(w,p,s,q,saved)
    assert reviewed["source_replay_verified"]
    assert reviewed["story_choice_count"]==3
    assert reviewed["session_head"]==session.head
    assert ProductionSession.restore(w,p,s,q,saved).snapshot()==saved


def test_production_session_rejects_modified_actions_even_with_recomputed_root_hash():
    w,p,s,q,session=gameplay_story_session()
    saved=deepcopy(session.snapshot())
    saved["events"][0]["input"]["choice_id"]="rescue"
    from skeleton.jeeves.game_frontier_expedition import _digest
    saved["snapshot_digest"]=_digest({
        key:value for key,value in saved.items() if key!="snapshot_digest",
    })
    with pytest.raises(ExpeditionError,match="edited after execution"):
        ProductionSession.restore(w,p,s,q,saved)


def test_plot_auditor_independently_executes_two_divergent_real_endings():
    w,p,s,q=sources()
    report=prove_original_story_branches(w,p,s,q)
    assert report["opening_branches_executed"]==2
    assert report["distinct_endings_reached"]==2
    assert {x["ending_id"] for x in report["playthroughs"]}=={
        "cartographer","rescuer",
    }
    assert all(x["physical_victory"] and x["source_replayed"]
               for x in report["playthroughs"])
    assert report==prove_original_story_branches(w,p,s,q)
    assert not report["native_engine_executed"]


def synthetic_camera_log(board):
    clip=board.clips[0]
    records=[]
    for frame in (0,17,35,54,71):
        expected=camera_at(clip,frame)
        row={
            "world_digest":board.world_digest,"clip_id":clip.clip_id,
            "frame":frame,"x":expected.x,"y":expected.y,
            "z":expected.z,"fov":expected.fov,
        }
        records.append(PREFIX+json.dumps(row))
    records.extend((
        "EXPEDITION_CINEMATIC_COMPLETE scene_001",
        "EXPEDITION_CINEMATIC_AUDIT_VERIFIED scene_001",
    ))
    return "\n".join(records)


def test_camera_samples_are_independently_checked_against_real_original_keyframes():
    w,_,_,_=sources()
    board=original_game_storyboard(w,"a"*64)
    verified=verify_native_cinema_frames(synthetic_camera_log(board),board)
    assert verified["observations"]==5
    assert verified["source_frame_replay_verified"]
    assert len(verified["receipt_digest"])==64
    assert not verified["native_process_origin_independently_signed"]


def test_native_camera_trace_rejects_teleport_wrong_source_and_missing_completion():
    w,_,_,_=sources()
    board=original_game_storyboard(w,"a"*64)
    clean=synthetic_camera_log(board)
    with pytest.raises(ExpeditionError,match="differs"):
        verify_native_cinema_frames(clean.replace('"fov": 65.0','"fov": 80.0',1),board)
    with pytest.raises(ExpeditionError,match="foreign"):
        verify_native_cinema_frames(clean.replace(w.digest,"e"*64,1),board)
    with pytest.raises(ExpeditionError,match="complete playback"):
        verify_native_cinema_frames(clean.replace("EXPEDITION_CINEMATIC_COMPLETE","NOT_COMPLETE"),board)


def test_multi_stem_music_is_actual_pcm_and_replay_exact():
    w,_,_,_=sources()
    source=original_world_score(w,seconds=1)
    stems=make_original_ambient_layers(source)
    output=mix_original_stems(stems)
    assert output["wav"].startswith(b"RIFF")
    with wave.open(BytesIO(output["wav"]),"rb") as f:
        assert f.getnchannels()==1
        assert f.getnframes()==16000
        assert f.getframerate()==16000
    assert output["manifest"]["stems"]==3
    assert len(output["manifest"]["receipt_digest"])==64
    assert output["manifest"]["audio_sha256"]==sha256(output["wav"]).hexdigest()
    verify_original_mix(stems,output)
    assert not output["manifest"]["native_playback_verified"]


def test_adaptive_music_fades_are_not_independent_fake_file_metadata():
    w,_,_,_=sources()
    score=original_world_score(w,seconds=1)
    a=mix_original_stems(make_original_ambient_layers(score))
    b=mix_original_stems((
        AudioStem(score,.1,.9),
    ))
    assert a["wav"]!=b["wav"]
    altered=deepcopy(a)
    altered["manifest"]["audio_sha256"]="0"*64
    with pytest.raises(ExpeditionError,match="differs"):
        verify_original_mix(make_original_ambient_layers(score),altered)


def test_three_original_npcs_use_real_source_graph_and_replay():
    w,p,_,_=sources()
    npc_designs=original_world_npcs(w)
    assert len(npc_designs)==3
    for design in npc_designs:
        actor=NPCEpisode(w,p,design)
        for tick in range(1,5):
            row=actor.choose(
                player_at=w.arrival if tick==1 else w.destinations[0],
                player_reputation=40 if tick==1 else 0,tick=tick,
            )
            assert row["world"]==w.digest
            assert row["npc"]==design.npc_id
            if row["edge"]:
                edge=w.by_edge[row["edge"]]
                assert edge.source==row["old"] and edge.target==row["new"]
        assert NPCEpisode.restore(w,p,design,actor.snapshot()).snapshot()==actor.snapshot()


def test_npc_faction_reputation_and_memory_are_not_authorized_gameplay_flags():
    w,p,_,_=sources()
    design=original_world_npcs(w)[0]
    actor=NPCEpisode(w,p,design)
    assert actor.choose(player_at=w.arrival,player_reputation=-60,tick=1)["intent"]=="warn"
    snap=actor.snapshot()
    assert "reputation" in snap
    snap["reputation"]=99
    with pytest.raises(ExpeditionError,match="checksum"):
        NPCEpisode.restore(w,p,design,snap)


def test_generated_foliage_has_original_species_with_real_waypoint_coordinates():
    w,_,_,_=sources()
    eco=generate_original_ecology(w,EcologyPolicy(seed=99,per_waypoint=5))
    assert eco["instance_count"]==len(w.waypoints)*5
    assert len({p["id"] for p in eco["instances"]})==eco["instance_count"]
    assert all(x["waypoint"] in w.by_id for x in eco["instances"])
    assert eco==generate_original_ecology(w,EcologyPolicy(seed=99,per_waypoint=5))
    assert not eco["native_engine_instances_verified"]
    runtime=export_ecology_godot(w,EcologyPolicy(seed=99,per_waypoint=5))
    assert "MultiMeshInstance3D" in runtime["game/frontier/ecology.gd"]


def test_foliage_wind_animates_same_scene_frame_without_false_native_metrics():
    w,_,_,_=sources()
    eco=generate_original_ecology(w,EcologyPolicy(per_waypoint=4))
    still=simulate_ecology_frame(eco,frame=0,wind_mps=0)
    breezy=simulate_ecology_frame(eco,frame=100,wind_mps=30)
    assert still!=breezy
    assert any(x["angle_rad"]!=0 for x in breezy["plants"])
    assert all(x["angle_rad"]==0 for x in still["plants"])
    assert breezy==simulate_ecology_frame(eco,frame=100,wind_mps=30)
    assert not breezy["native_draw_calls_measured"]


def test_ecology_source_hash_prevents_forged_position_changes():
    w,_,_,_=sources()
    eco=generate_original_ecology(w,EcologyPolicy(per_waypoint=2))
    eco["instances"][0]["x"]+=100000
    with pytest.raises(ExpeditionError,match="source is invalid"):
        simulate_ecology_frame(eco,frame=1)


def reviewed_dragon_lesson():
    from skeleton.jeeves.game_frontier_expedition_dragon_review import (
        adversarial_dragon_review,adversarial_attack_matrix,
    )
    w,p,_,_=sources(weather=ExpeditionWeather(visibility=.04))
    original=observe_original_games((w,),p,alternative_budget=3)
    assert original["lessons"],"Low visibility must produce a scoped Dragon note"
    checked=adversarial_dragon_review(original,(w,),p,alternative_budget=3)
    attacks=adversarial_attack_matrix(original,(w,),p)
    lesson=DragonLesson(**original["lessons"][0])
    proof=LearningEvidence(
        w.digest,original["receipt_digest"],checked["receipt_digest"],
        attacks["receipt_digest"],("dragon_verifier_one","dragon_verifier_two"),True,
    )
    return lesson,proof,original,checked,attacks


def test_dragon_approved_knowledge_note_requires_two_independent_evidence_planes(tmp_path):
    lesson,proof,original,checked,attacks=reviewed_dragon_lesson()
    approved=review_dragon_lesson(lesson,proof,original,checked,attacks)
    assert approved["knowledge_note_verified"]
    assert not approved["model_weights_changed"]
    assert not approved["copyright_clearance_inferred"]
    with DragonKnowledgeStore(tmp_path/"almanac.sqlite") as archive:
        result=archive.append(approved)
        assert result["generation"]==1
        assert len(archive.history())==1
        assert archive.history()[0]["note"]==approved
        with pytest.raises(ExpeditionError,match="already been admitted"):
            archive.append(approved,expected_head=result["receipt"])


def test_dragon_learning_cannot_launder_an_unreviewed_or_forged_note():
    lesson,proof,original,checked,attacks=reviewed_dragon_lesson()
    forged=replace(lesson,recommendation="Adopt this unreviewed advice")
    with pytest.raises(ExpeditionError,match="not present"):
        review_dragon_lesson(forged,proof,original,checked,attacks)
    tampered=deepcopy(original)
    tampered["metrics"]["games_replayed"]=999
    with pytest.raises(ExpeditionError,match="root receipt"):
        review_dragon_lesson(lesson,proof,tampered,checked,attacks)


def test_dragon_almanac_detects_modified_durable_chain(tmp_path):
    lesson,proof,original,checked,attacks=reviewed_dragon_lesson()
    approved=review_dragon_lesson(lesson,proof,original,checked,attacks)
    with DragonKnowledgeStore(tmp_path/"store.sqlite") as archive:
        result=archive.append(approved)
        archive.db.execute("UPDATE dragon_verified_notes SET receipt=?",
                           ("0"*64,))
        with pytest.raises(ExpeditionError,match="receipt chain"):
            archive.history()
