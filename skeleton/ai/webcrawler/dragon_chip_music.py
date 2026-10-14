"""Deterministic original 8-bit score composer for native cartridge/PC genres.

The compiler emits individual playable frequency steps, not recorded music,
lyrics or generated copies of commercial game soundtracks. Rhythmic motifs
reflect game pacing and are embedded as static C data in the native executable.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from .dragon_game_blueprints import PRNG,GAME_MODES

NOTES={
  "C3":131,"D3":147,"E3":165,"F3":175,"G3":196,"A3":220,"B3":247,
  "C4":262,"D4":294,"E4":330,"F4":349,"G4":392,"A4":440,"B4":494,
  "C5":523,"D5":587,"E5":659,"F5":698,"G5":784,"A5":880,"B5":988,
}
MODE_SCALE={
  "arena":("C4","E4","G4","A4","C5","E5","G5"),
  "platform":("C4","D4","E4","G4","A4","C5","D5"),
  "adventure":("D4","E4","F4","A4","C5","D5","F5"),
  "dungeon":("C3","D3","F3","G3","A3","C4","D4"),
  "tactics":("E3","G3","A3","C4","D4","E4","G4"),
  "racer":("C4","E4","G4","B4","D5","E5","G5"),
}
MODE_BPM={"arena":148,"platform":124,"adventure":100,
          "dungeon":84,"tactics":92,"racer":174}

@dataclass(frozen=True)
class ChipScore:
    mode:str
    seed:int
    beats_per_minute:int
    frames_per_step:int
    melody_hz:tuple[int,...]
    harmony_hz:tuple[int,...]
    note_events:int
    fingerprint:str
    schema:str="skeleton.ai.dragon.original_chip_score.v1"

def compose(mode:str,seed:int,steps:int=64)->ChipScore:
    if mode not in GAME_MODES:raise ValueError("soundtrack mode unavailable")
    if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<2**32:
        raise ValueError("chiptune seed requires uint32")
    if isinstance(steps,bool) or not isinstance(steps,int) or not 16<=steps<=128 or steps%16:
        raise ValueError("composition must contain 16-step phrases")
    rng=PRNG(seed^0xB0A5FEED)
    scale=MODE_SCALE[mode]
    motif=[rng.pick(len(scale)) for _ in range(8)]
    melody=[];harmony=[]
    for i in range(steps):
        bar=i//16
        note=motif[(i+bar)%8]
        # Genre-adaptive rests and phrase structure; no infinite arpeggios.
        accent=(i%4==0)
        active=(i%8!=7 and (accent or rng.pick(6)>=2))
        pitch=NOTES[scale[note]] if active else 0
        if mode=="dungeon" and i%4!=0 and rng.pick(3)!=0:pitch=0
        melody.append(pitch)
        if i%4==0:
            harmony.append(NOTES[scale[(note+4)%len(scale)]])
        else:harmony.append(0)
    length=round(900/MODE_BPM[mode])
    length=max(4,min(13,length))
    evidence=sha256(json.dumps([mode,seed,melody,harmony,length],
                               separators=(",",":")).encode()).hexdigest()
    return ChipScore(mode,seed,MODE_BPM[mode],length,tuple(melody),
                     tuple(harmony),sum(n>0 for n in melody),evidence)

def emit_score_header(score:ChipScore)->str:
    if not isinstance(score,ChipScore) or score.mode not in GAME_MODES:
        raise ValueError("validated original chip score required")
    count=len(score.melody_hz)
    if count!=len(score.harmony_hz) or count<16 or count>128:
        raise ValueError("invalid number of musical steps")
    if any(not 0<=n<=2000 for n in score.melody_hz+score.harmony_hz):
        raise ValueError("invalid playable frequency")
    first=", ".join(str(n) for n in score.melody_hz)
    second=", ".join(str(n) for n in score.harmony_hz)
    return (
        "#ifndef DRAGON_CHIP_SCORE_H\n#define DRAGON_CHIP_SCORE_H\n"
        f"#define DRAGON_SCORE_STEPS {count}\n"
        f"#define DRAGON_SCORE_INTERVAL {score.frames_per_step}\n"
        f"static const unsigned short DRAGON_MELODY[{count}] = {{{first}}};\n"
        f"static const unsigned short DRAGON_HARMONY[{count}] = {{{second}}};\n"
        "#endif\n"
    )

def score_manifest(score:ChipScore)->dict:
    return asdict(score)
