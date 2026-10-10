"""Deterministic original Sokoban gameplay state parity and native CLI injection.

The independent Python simulator is not a second implementation of the
original generator: it evaluates already-authored level layouts, movement,
crate pushing, reset and bounded rollback. The C99 game offers an allowlisted
headless interface with bounded command sequences. Build verification compares
both implementations' exact state hash after each meaningful transition.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .dragon_native_puzzle import WIDTH,HEIGHT,_parse

SCHEMA="skeleton.ai.dragon.native_puzzle_state_trace.v1"
MAX_SEQUENCE=400
MOVES={"a":(-1,0),"d":(1,0),"w":(0,-1),"s":(0,1)}
OLD_MAIN='int main(int argc,char**argv){'
MAIN_HEAD=' if(argc==2&&!strcmp(argv[1],"--selftest"))return selftest();'

@dataclass(frozen=True)
class PuzzleState:
    schema:str
    level:int
    player:int
    crates:tuple[int,...]
    moves:int
    pushes:int
    solved:bool
    digest:str


def _native_hash(*,level:int,player:int,crates:tuple[int,...],
                 moves:int,pushes:int,solved:bool)->str:
    """FNV-1a over canonical byte fields, mirroring the native C implementation."""
    values=[level,player,len(crates),*crates,moves,pushes,int(solved)]
    value=2166136261
    for number in values:
        if type(number) is not int or number<0 or number>0xffffffff:
            raise ValueError("out-of-range native state scalar")
        for offset in (0,8,16,24):
            value=(value^((number>>offset)&255))*16777619&0xffffffff
    return format(value,"08x")


def simulate_grid(rows:tuple[str,...],inputs:str,*,level:int=1)->PuzzleState:
    """Independent grid physics for deterministic native replay comparison."""
    if type(level) is not int or not 1<=level<=8:
        raise ValueError("invalid native level number")
    if not isinstance(inputs,str) or len(inputs)>MAX_SEQUENCE or not re.fullmatch("[wasdur]*",inputs):
        raise ValueError("invalid or over-budget native input sequence")
    initial,boxes,goals,walls=_parse(rows)
    player=initial
    positions=list(boxes)
    moves=pushes=0
    history:list[tuple[int,tuple[int,...],int,int]]=[]
    for token in inputs:
        if token=="r":
            player=initial;positions=list(boxes);moves=pushes=0
            history=[]
            continue
        if token=="u":
            if history:
                player,reverted,moves,pushes=history.pop()
                positions=list(reverted)
            continue
        delta=MOVES[token]
        x,y=player%WIDTH,player//WIDTH
        nx,ny=x+delta[0],y+delta[1]
        if not (0<=nx<WIDTH and 0<=ny<HEIGHT):
            continue
        where=ny*WIDTH+nx
        if where in walls:
            continue
        should_push=where in positions
        new_pos=None
        if should_push:
            px,py=nx+delta[0],ny+delta[1]
            if not (0<=px<WIDTH and 0<=py<HEIGHT):
                continue
            new_pos=py*WIDTH+px
            if new_pos in walls or new_pos in positions:
                continue
        if len(history)>=1024:
            continue
        history.append((player,tuple(positions),moves,pushes))
        if should_push:
            positions[positions.index(where)]=new_pos
            pushes+=1
        player=where
        moves+=1
    state=tuple(positions)
    complete=bool(state) and all(value in goals for value in state)
    return PuzzleState(
        schema=SCHEMA,level=level,player=player,crates=state,
        moves=moves,pushes=pushes,solved=complete,
        digest=_native_hash(level=level,player=player,
                            crates=state,moves=moves,pushes=pushes,solved=complete),
    )


C_TRACE=r'''
/* Bounded, noninteractive original game replay. No filesystem/network input.
   Used to validate actual compiled push, undo, reset, and level completion
   against the independent Python simulator. Never treats source-only as play. */
static uint32_t trace_word(uint32_t h,uint32_t v){
 for(int shift=0;shift<32;shift+=8)
  h=(h^((v>>shift)&255u))*16777619u;
 return h;
}
static uint32_t state_hash(int level){
 uint32_t h=2166136261u;
 h=trace_word(h,(uint32_t)level);
 h=trace_word(h,(uint32_t)state.player);
 h=trace_word(h,(uint32_t)state.count);
 for(int i=0;i<state.count;i++)
  h=trace_word(h,(uint32_t)state.boxes[i]);
 h=trace_word(h,(uint32_t)state.moves);
 h=trace_word(h,(uint32_t)state.pushes);
 h=trace_word(h,(uint32_t)(level_done()?1:0));
 return h;
}
static int simulate_native_inputs(const char*number,const char*sequence){
 char *end=NULL;
 unsigned long stage=strtoul(number,&end,10);
 if(!number[0]||!end||*end||stage<1||stage>(unsigned long)LEVEL_COUNT)return 20;
 size_t size=strlen(sequence);
 if(size>400)return 21;
 if(!load_level((int)stage-1))return 22;
 for(size_t i=0;i<size;i++){
  char action=sequence[i];
  if(action=='r'){
   if(!load_level((int)stage-1))return 23;
   continue;
  }
  if(action=='u'){rollback();continue;}
  if(action!='w'&&action!='a'&&action!='s'&&action!='d')return 24;
  perform(action);
 }
 printf("DRAGON_NATIVE_STATE level=%lu player=%d crates=",stage,state.player);
 for(int i=0;i<state.count;i++)
  printf("%s%d",i?",":"",state.boxes[i]);
 printf(" moves=%d pushes=%d solved=%d digest=%08x\n",
        state.moves,state.pushes,level_done()?1:0,
        (unsigned)state_hash((int)stage));
 return 0;
}
'''


def enable_native_trace(source:str)->str:
    if not isinstance(source,str) or source.count(OLD_MAIN)!=1:
        raise ValueError("bounded C99 gameplay source missing")
    if source.count(MAIN_HEAD)!=1:
        raise ValueError("canonical original game entry changed")
    result=source.replace(OLD_MAIN,C_TRACE+"\n"+OLD_MAIN,1)
    result=result.replace(MAIN_HEAD,
        ' if(argc==4&&!strcmp(argv[1],"--simulate"))'
        'return simulate_native_inputs(argv[2],argv[3]);\n'+MAIN_HEAD,1)
    return result


def parse_native_state_line(line:str)->dict:
    match=re.fullmatch(
        r"DRAGON_NATIVE_STATE level=([1-8]) player=([0-9]{1,3}) "
        r"crates=([0-9]{1,3}(?:,[0-9]{1,3}){0,2}) "
        r"moves=([0-9]{1,4}) pushes=([0-9]{1,4}) solved=([01]) "
        r"digest=([a-f0-9]{8})\n?",
        line,
    )
    if match is None:
        raise ValueError("native puzzle runtime state report is malformed")
    stage,player,crates,moves,pushes,solved,digest=match.groups()
    return {
        "level":int(stage),"player":int(player),
        "crates":tuple(int(x) for x in crates.split(",")),
        "moves":int(moves),"pushes":int(pushes),
        "solved":solved=="1","digest":digest,
    }
