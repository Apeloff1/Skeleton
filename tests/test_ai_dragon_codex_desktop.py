"""Actually compile/run original Codex C99 game (when cc is available)."""
from __future__ import annotations
from dataclasses import replace
import shutil,subprocess
import pytest

from skeleton.ai.webcrawler.dragon_world_codex import (
    unrank,edit,AXIS_NAMES,
)
from skeleton.ai.webcrawler.dragon_codex_desktop import (
    SCHEMA,emit_codex_c99,inspect_c99_source,
)
from skeleton.ai.webcrawler.dragon_world_codex_runtime import (
    witness_to_gate,DOMAINS,
)


def test_native_original_world_game_source_contains_real_skills_and_gate_rules():
    source=unrank("0")
    game=emit_codex_c99(source)
    assert game.schema==SCHEMA
    assert game.source_name.endswith(".c")
    assert not game.actual_native_binary_produced
    assert not game.independently_compiled
    assert not game.compiled_game_selftest_passed
    assert "#define AXES 128" in game.source
    assert "gate_open" in game.source
    assert "study_skill" in game.source
    assert "DRAGON_CODEX_SELFTEST_PASS" in game.source
    assert source.codex_digest in game.source
    assert len(game.source_sha256)==64
    assert inspect_c99_source(source,game)["verified_source"]
    assert "no_mandatory_ending" in game.active_mechanics


def test_modified_native_world_game_source_is_rejected_before_export():
    source=edit("0",{"story_branching":255})
    artifact=emit_codex_c99(source)
    with pytest.raises(ValueError):
        inspect_c99_source(source,replace(
            artifact,source=artifact.source.replace("gate_open","always_open")))
    with pytest.raises(ValueError):
        inspect_c99_source(unrank("0"),artifact)


@pytest.mark.skipif(shutil.which("cc") is None,
                    reason="actual host C99 compiler not installed")
@pytest.mark.parametrize("levels",[
    {},{"plate_migration":255,"elevation_tectonics":255},
    {"dream_access":250,"portal_alignment":255,
     "world_repopulation":190,"alternate_ending_access":255},
])
def test_native_c99_compiles_and_executes_all_sixteen_delayed_passage_proofs(
    levels,tmp_path,
):
    src=edit("0",levels)
    artifact=emit_codex_c99(src)
    file=tmp_path/"original_dragon_codex.c"
    executable=tmp_path/"dragon_game"
    file.write_text(artifact.source,encoding="utf-8")
    build=subprocess.run(
        ["cc","-std=c99","-Wall","-Wextra","-Werror",
         "-O2",str(file),"-o",str(executable)],
        capture_output=True,text=True,timeout=20,check=False,
    )
    assert build.returncode==0,build.stderr
    played=subprocess.run(
        [str(executable),"--selftest"],
        capture_output=True,text=True,timeout=12,check=False,
    )
    assert played.returncode==0,played.stderr
    assert "DRAGON_CODEX_SELFTEST_PASS" in played.stdout
    assert played.stdout.count("PROVED ")==16
    assert "actual gate unlocks" in played.stdout
    listed=subprocess.run(
        [str(executable),"--list"],
        capture_output=True,text=True,timeout=12,check=False,
    )
    assert listed.returncode==0
    assert src.codex_digest in listed.stdout
    assert listed.stdout.count("next window")>=16


@pytest.mark.skipif(shutil.which("cc") is None,
                    reason="actual host C99 compiler not installed")
def test_player_can_use_original_console_to_train_wait_and_enter_secret_passage(tmp_path):
    address=edit("0",{
        "elevation_tectonics":255,"plate_migration":255,
        "story_branching":190,
    })
    game=emit_codex_c99(address)
    source=tmp_path/"world.c"
    binary=tmp_path/"world"
    source.write_text(game.source,encoding="utf-8")
    compiled=subprocess.run(
        ["cc","-std=c99","-Wall","-Wextra","-Werror",
         str(source),"-o",str(binary)],
        capture_output=True,text=True,timeout=20,
    )
    assert compiled.returncode==0,compiled.stderr
    witness=witness_to_gate(address,"geology")
    script=[]
    for step in witness:
        if step=="wait_world":
            script.append("wait")
        elif step.startswith("study_"):
            script.append("study "+str(AXIS_NAMES.index(step[6:])))
        else:
            script.append("gate "+str(DOMAINS.index("geology")))
    script.extend(["explore","map","quit"])
    played=subprocess.run(
        [str(binary)],input="\n".join(script)+"\n",
        capture_output=True,text=True,timeout=10,
    )
    assert played.returncode==0
    assert "Earned journey 0 reached -2,-3" in played.stdout
    assert "No mandatory ending" in played.stdout
    assert "128 trained axes" in game.source


def test_native_game_source_is_original_for_each_world_seed():
    worlds=[unrank("0"),edit("0",{"storm_fronts":255}),
            edit("0",{"trade_volatility":200}),
            edit("0",{"maze_mutation_frequency":155})]
    emitted=[emit_codex_c99(x) for x in worlds]
    assert len({x.source_sha256 for x in emitted})==4
    assert all(not x.actual_native_binary_produced for x in emitted)
    assert len({x.game_rules_sha256 for x in emitted})==4
