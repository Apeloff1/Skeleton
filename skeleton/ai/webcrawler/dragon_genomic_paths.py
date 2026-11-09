"""Massive exact-indexed original choice paths: 16 genuine actions over 16 turns.

For every valid world genome, 16**16 distinct source action sequences are
addressable without enumeration. Each 4-bit path digit selects a different
*implemented, safely available* game-world verb that modifies canonical time,
resources, science or ecological/route observations. We verify actual replays
rather than treating a random bit string as a finished playable game.

The guarantee is for 16-choice programmable routes from fresh world state,
not arbitrary survival/world victory, subjective uniqueness or publishing.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass
import re

from .dragon_world_genome import (
    GENOMIC_WORLD_COUNT,integer_address,unrank_genome_address,
    WorldGenomeAddress,
)
from .dragon_genomic_world import (
    SCHEMA as GAME_SCHEMA,AXIS_ACTIONS,initial_genomic_state,
    legal_actions,play,replay_genomic,report,
)
from .dragon_living_world import _sha

SCHEMA="skeleton.ai.dragon.genomic_choice_path.v1"
CHOICES_PER_STEP=16
STEPS_PER_PATH=16
PROGRAM_COUNT=CHOICES_PER_STEP**STEPS_PER_PATH  # exact 2**64
GLOBAL_CHOICE_PATH_COUNT=GENOMIC_WORLD_COUNT*PROGRAM_COUNT
MAX_INDEX_LEN=len(str(GLOBAL_CHOICE_PATH_COUNT))
DECIMAL=re.compile(r"(0|[1-9][0-9]*)\Z")
# Chosen verbs are universally present at the start of every valid world:
# no resource preconditions and no time/action limit within 16 turns.
# All distinct verbs affect actual canonical world time and recorded signals.
CHOICE_VERBS=(
    "survey_elevation","map_biomes","study_river","explore_caves",
    "scan_skies","forecast_storm","study_seasons","chart_stars",
    "tend_flora","track_fauna","forage_food","prospect_ore",
    "plan_building","mediate_dispute","scout_pass","trace_shifting_wall",
)
assert len(CHOICE_VERBS)==16==len(set(CHOICE_VERBS))
assert all(v in AXIS_ACTIONS for v in CHOICE_VERBS)


@dataclass(frozen=True)
class ChoiceProgram:
    schema:str
    decimal_path_index:str
    world_decimal_index:str
    local_program_code:str
    word:tuple[int,...]
    actions:tuple[str,...]
    world_genome_digest:str
    start_history_digest:str
    final_history_digest:str
    final_turn:int
    final_energy:int
    final_hydration:int
    final_knowledge:int
    sampled_signals:tuple[int,...]
    distinct_source_actions:int
    actually_played:bool
    finished_game_release_approved:bool
    execution_digest:str


def code_word(n:int)->tuple[int,...]:
    if type(n) is not int or not 0<=n<PROGRAM_COUNT:
        raise ValueError("genomic action program does not fit sixteen 4-bit decisions")
    digits=[0]*STEPS_PER_PATH
    for pos in range(STEPS_PER_PATH-1,-1,-1):
        digits[pos]=n&15
        n>>=4
    return tuple(digits)


def word_code(word:tuple[int,...])->int:
    if (type(word) is not tuple or len(word)!=STEPS_PER_PATH or
        any(type(i) is not int or not 0<=i<CHOICES_PER_STEP for i in word)):
        raise ValueError("original route must have sixteen real 4-bit action decisions")
    result=0
    for digit in word:result=result*16+digit
    return result


def _parse_path(value:str)->int:
    if (type(value) is not str or not 1<=len(value)<=MAX_INDEX_LEN or
        not DECIMAL.fullmatch(value)):
        raise ValueError("game path index must be a canonical decimal string")
    number=int(value)
    if number>=GLOBAL_CHOICE_PATH_COUNT:
        raise ValueError("game path index exceeds exact playable path lattice")
    return number


def rank_path(world_decimal_index:str,word:tuple[int,...])->str:
    world=integer_address(world_decimal_index)
    return str(world*PROGRAM_COUNT+word_code(word))


def unrank_path(path_decimal_index:str)->tuple[WorldGenomeAddress,tuple[int,...]]:
    index=_parse_path(path_decimal_index)
    world_n,program_n=divmod(index,PROGRAM_COUNT)
    return unrank_genome_address(str(world_n)),code_word(program_n)


def materialize_path(path_decimal_index:str)->ChoiceProgram:
    addr,word=unrank_path(path_decimal_index)
    first=initial_genomic_state(addr)
    now=first
    actions=[]
    for step,digit in enumerate(word):
        action=CHOICE_VERBS[digit]
        available={
            candidate["name"]:candidate for candidate in legal_actions(addr,now)
        }
        if action not in available or not available[action]["available"]:
            # This is an assurance error, not permission to fabricate a
            # next route edge. Universal sixteen-step paths are contractual.
            raise ValueError("one original world no longer supports its indexed route")
        now=play(addr,now,action)
        actions.append(action)
    if now.base.turn!=first.base.turn+STEPS_PER_PATH or (
        now.choices!=first.choices+STEPS_PER_PATH
    ):
        raise ValueError("indexed route did not execute all original gameplay actions")
    proof={
        "schema":SCHEMA,"path":path_decimal_index,
        "world":addr.decimal_index,"word":word,
        "actions":actions,
        "genome":addr.genome_digest,
        "first":first.history_digest,"last":now.history_digest,
        "current_world_state":now.base.history_digest,
        "real_signals":now.signals,
        "stamina":now.stamina,"hydration":now.hydration,
        "knowledge":now.knowledge,
    }
    return ChoiceProgram(
        schema=SCHEMA,
        decimal_path_index=path_decimal_index,
        world_decimal_index=addr.decimal_index,
        local_program_code=str(word_code(word)),
        word=word,actions=tuple(actions),
        world_genome_digest=addr.genome_digest,
        start_history_digest=first.history_digest,
        final_history_digest=now.history_digest,
        final_turn=now.base.turn,
        final_energy=now.stamina,
        final_hydration=now.hydration,
        final_knowledge=now.knowledge,
        sampled_signals=now.signals,
        distinct_source_actions=len(set(actions)),
        actually_played=True,finished_game_release_approved=False,
        execution_digest=_sha(proof),
    )


def verify_path(program:ChoiceProgram)->dict:
    if not isinstance(program,ChoiceProgram) or program.schema!=SCHEMA:
        raise ValueError("unrecognized original route evidence")
    replayed=materialize_path(program.decimal_path_index)
    if replayed!=program:
        raise ValueError("original game route evidence changed after gameplay")
    addr,_=unrank_path(program.decimal_path_index)
    actual=replay_genomic(addr,program.actions)
    if actual.history_digest!=program.final_history_digest:
        raise ValueError("original indexed path was not mechanically replayable")
    return {
        "schema":SCHEMA,
        "verified":True,
        "actual_actions":len(program.actions),
        "world_still_playable":not actual.base.endings_seen or (
            addr.lifecycle in ("unending","optional_endings","postgame",
                               "multiple_endings")),
        "scope":"exact independent replay of a real original 16-action choice "
                "history, not verified originality of finished game",
    }


def pathspace_summary()->dict:
    return {
        "schema":SCHEMA,
        "actual_implemented_choices_per_step":CHOICES_PER_STEP,
        "bounded_executable_decisions_per_path":STEPS_PER_PATH,
        "per_world_choice_programs":str(PROGRAM_COUNT),
        "genomically_addressable_worlds":str(GENOMIC_WORLD_COUNT),
        "globally_addressable_choice_paths":str(GLOBAL_CHOICE_PATH_COUNT),
        "sampled_in_summary":0,
        "shipped_unique_games":0,
        "why_counts_are_exact":"mixed-radix reversible addressing where each "
                               "4-bit digit selects a different implemented action",
        "novelty_claim":"none without separate structural/player/legal audit",
    }


def sample_paths(world_index:str,*,limit:int=4)->dict:
    if type(limit) is not int or not 1<=limit<=10:
        raise ValueError("sample only a bounded number of real paths")
    integer_address(world_index)
    # Widely spaced programs exercise different actual world verbs and
    # different choices within the same world-genome seed.
    steps=[(PROGRAM_COUNT-1)*i//max(1,limit-1) for i in range(limit)]
    rows=[materialize_path(
        str(int(world_index)*PROGRAM_COUNT+program))
        for program in steps]
    return {
        "schema":SCHEMA,
        "world_index":world_index,
        "sampled_count":len(rows),
        "distinct_actual_action_histories":len({row.actions for row in rows}),
        "routes":[asdict(row) for row in rows],
        "claim":"only these sampled paths were actually executed and independently "
                "measured, not every program in the huge address space",
    }
