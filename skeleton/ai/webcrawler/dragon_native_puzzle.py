"""Generate original finite Sokoban games with optimal abstract walk proofs.

Each emitted level is actually solved by bounded exact BFS over player and
crates. The native C99 terminal game embeds the resulting original levels
and real move-by-move solution and replays every level via --selftest.
No SDL, browser, emulator SDK, dependencies or precompiled binaries.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass,asdict
from hashlib import sha256
import json

WIDTH=12
HEIGHT=10
MAX_LEVELS=8
MAX_SEARCH=120000
MAX_SOLUTION=400
ACTIONS=((-1,0,"a"),(1,0,"d"),(0,-1,"w"),(0,1,"s"))
BASE_LEVELS=(
    ("############","#..........#","#...#......#","#..........#",
     "#...@......#","#....$.....#","#....o.....#","#..........#",
     "#..........#","############"),
    ("############","#..........#","#..........#","#...@......#",
     "#....$$....#","#....oo....#","#..........#","#..........#",
     "#..........#","############"),
    ("############","#..........#","#...##.....#","#..........#",
     "#..@..$....#","#......o...#","#..........#","#..........#",
     "#..........#","############"),
    ("############","#..........#","#...##.....#","#..........#",
     "#..@.$.$...#","#....o.o...#","#..........#","#..........#",
     "#..........#","############"),
)

@dataclass(frozen=True)
class LevelProof:
    stage:int
    solution:str
    steps:int
    examined_states:int
    crates:int
    input_digest:str
    solution_digest:str
    optimal_within_abstract_grid:bool=True

def _parse(rows:tuple[str,...]):
    if len(rows)!=HEIGHT or any(len(r)!=WIDTH for r in rows):
        raise ValueError("native puzzle map size must be 12x10")
    if any(c not in "#.@$o" for r in rows for c in r):
        raise ValueError("unsupported puzzle tile")
    flat="".join(rows)
    starts=[i for i,c in enumerate(flat) if c=="@"]
    boxes=tuple(sorted(i for i,c in enumerate(flat) if c=="$"))
    goals=frozenset(i for i,c in enumerate(flat) if c=="o")
    if len(starts)!=1 or not boxes or len(boxes)!=len(goals) or len(boxes)>3:
        raise ValueError("game puzzle needs one player, 1..3 crates and matching goals")
    walls=frozenset(i for i,c in enumerate(flat) if c=="#")
    if any(i in walls for i in boxes+tuple(goals)+tuple(starts)):
        raise ValueError("crate or player overlaps wall")
    return starts[0],boxes,goals,walls

def solve_grid(rows:tuple[str,...])->tuple[str,int]:
    start,boxes,goals,walls=_parse(rows)
    initial=(start,boxes)
    parents={initial:None}
    pending=deque((initial,))
    final=None
    while pending and len(parents)<=MAX_SEARCH:
        state=pending.popleft()
        hero,crates=state
        if set(crates)==goals:
            final=state;break
        crate_set=set(crates)
        for dx,dy,action in ACTIONS:
            x,y=hero%WIDTH,hero//WIDTH
            nx,ny=x+dx,y+dy
            if not (0<=nx<WIDTH and 0<=ny<HEIGHT):continue
            target=nx+ny*WIDTH
            if target in walls:continue
            new_boxes=crates
            if target in crate_set:
                bx,by=nx+dx,ny+dy
                if not (0<=bx<WIDTH and 0<=by<HEIGHT):continue
                ahead=bx+by*WIDTH
                if ahead in walls or ahead in crate_set:continue
                new_boxes=tuple(sorted(ahead if v==target else v for v in crates))
            next_state=(target,new_boxes)
            if next_state not in parents:
                parents[next_state]=(state,action)
                pending.append(next_state)
        if len(parents)>MAX_SEARCH:
            break
    if final is None:
        raise ValueError("bounded native puzzle solver did not prove solvability")
    rev=[]
    while final!=initial:
        earlier,move=parents[final]
        rev.append(move);final=earlier
    solution="".join(reversed(rev))
    if not 1<=len(solution)<=MAX_SOLUTION:
        raise ValueError("native puzzle solution exceeds bounded input sequence")
    return solution,len(parents)

def transformed_level(stage:int,seed:int,difficulty:int=4)->tuple[str,...]:
    if isinstance(stage,bool) or not isinstance(stage,int) or not 0<=stage<MAX_LEVELS:
        raise ValueError("native puzzle level index out of bounds")
    if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<2**32:
        raise ValueError("native puzzle seed must be uint32")
    if isinstance(difficulty,bool) or not isinstance(difficulty,int) or not 1<=difficulty<=10:
        raise ValueError("native puzzle difficulty must be 1..10")
    source=BASE_LEVELS[(stage+max(0,difficulty-4)//2)%len(BASE_LEVELS)]
    flags=(seed^(stage*0x9E3779B1))&3
    rows=source
    if flags&1:rows=tuple(r[::-1] for r in rows)
    if flags&2:rows=tuple(reversed(rows))
    _parse(rows)
    return rows

C_SOURCE=r'''/* Dragon Native Sokoban: pure C99, ANSI terminal, no SDL/no WebView.
  Gameplay: push crates onto original goals; undo and reset; bounded levels.
  Each level is solved in advance with a canonical shortest walk trace. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "dragon_puzzle.h"
#define N (LEVEL_W*LEVEL_H)
#define UNDO_MAX 1024
typedef struct{
 int player,boxes[3],count,moves,pushes;
}State;
static State state,undo[UNDO_MAX];
static char world[N+1];
static uint8_t goals[N];
static int chapter=0,undo_count=0,total_moves=0,total_pushes=0;
static int tiles_loaded=0;
static int is_wall(int cell){return cell<0||cell>=N||world[cell]=='#';}
static int crate_at(int cell){
 for(int i=0;i<state.count;i++)if(state.boxes[i]==cell)return i;
 return -1;
}
static int level_done(void){
 for(int i=0;i<state.count;i++)if(!goals[state.boxes[i]])return 0;
 return state.count>0;
}
static int load_level(int index){
 if(index<0||index>=LEVEL_COUNT)return 0;
 chapter=index;memset(&state,0,sizeof(state));
 memset(goals,0,sizeof(goals));undo_count=0;
 for(int y=0;y<LEVEL_H;y++){
  for(int x=0;x<LEVEL_W;x++){
   int cell=y*LEVEL_W+x;
   char c=dragon_levels[index][y][x];
   world[cell]=(c=='#'?'#':'.');
   if(c=='@')state.player=cell;
   if(c=='$'){
    if(state.count>=3)return 0;
    state.boxes[state.count++]=cell;
   }
   if(c=='o')goals[cell]=1;
  }
 }
 world[N]=0;state.moves=0;state.pushes=0;tiles_loaded=1;
 return 1;
}
static int perform(char key){
 int dx=0,dy=0;
 if(key=='w')dy=-1;
 else if(key=='s')dy=1;
 else if(key=='a')dx=-1;
 else if(key=='d')dx=1;
 else return 0;
 int x=state.player%LEVEL_W,y=state.player/LEVEL_W;
 int nx=x+dx,ny=y+dy;
 if(nx<0||nx>=LEVEL_W||ny<0||ny>=LEVEL_H)return 0;
 int to=ny*LEVEL_W+nx;
 if(is_wall(to))return 0;
 int crate=crate_at(to);
 int ahead=-1;
 if(crate>=0){
  int bx=nx+dx,by=ny+dy;
  if(bx<0||bx>=LEVEL_W||by<0||by>=LEVEL_H)return 0;
  ahead=by*LEVEL_W+bx;
  if(is_wall(ahead)||crate_at(ahead)>=0)return 0;
 }
 if(undo_count<UNDO_MAX)undo[undo_count++]=state;
 else return 0; /* bounded history: never silently lose rollback */
 if(crate>=0){state.boxes[crate]=ahead;state.pushes++;total_pushes++;}
 state.player=to;state.moves++;total_moves++;
 return 1;
}
static void rollback(void){
 if(undo_count>0)state=undo[--undo_count];
}
static void draw(void){
 printf("\033[H\033[2J");
 printf("DRAGON PUZZLE FORGE | level %d/%d | moved %d | pushes %d\n",
   chapter+1,LEVEL_COUNT,state.moves,state.pushes);
 printf("W/A/S/D move | U undo | R reset | H hint from start | Q quit\n");
 for(int y=0;y<LEVEL_H;y++){
  for(int x=0;x<LEVEL_W;x++){
   int loc=y*LEVEL_W+x;
   char ch=world[loc];
   int crate=crate_at(loc);
   if(loc==state.player)ch=goals[loc]?'+':'@';
   else if(crate>=0)ch=goals[loc]?'*':'$';
   else if(goals[loc])ch='o';
   if(ch=='#')printf("\033[38;5;240m%c\033[0m",ch);
   else if(ch=='$'||ch=='*')printf("\033[33m%c\033[0m",ch);
   else if(ch=='@'||ch=='+')printf("\033[32m%c\033[0m",ch);
   else if(ch=='o')printf("\033[36m%c\033[0m",ch);
   else putchar(ch);
  }
  putchar('\n');
 }
 printf("Crates on goals: ");
 int placed=0;
 for(int i=0;i<state.count;i++)placed+=goals[state.boxes[i]]?1:0;
 printf("%d / %d\n",placed,state.count);
}
static int selftest(void){
 for(int level=0;level<LEVEL_COUNT;level++){
  if(!load_level(level))return 2;
  const char*trace=dragon_solutions[level];
  int len=(int)strlen(trace);
  if(len!=dragon_solution_length[level]||len<1||len>400)return 3;
  for(int i=0;i<len;i++)if(!perform(trace[i]))return 4;
  if(!level_done())return 5;
  printf("PUZZLE_STAGE_PASS level=%d moves=%d pushes=%d\n",
    level+1,state.moves,state.pushes);
  if(state.moves!=len)return 6;
 }
 printf("DRAGON_NATIVE_PUZZLE_SELFTEST PASS stages=%d\n",LEVEL_COUNT);
 return 0;
}
int main(int argc,char**argv){
 if(argc==2&&!strcmp(argv[1],"--selftest"))return selftest();
 if(argc==2&&!strcmp(argv[1],"--list")){
  for(int i=0;i<LEVEL_COUNT;i++)
   printf("level=%d solution_moves=%d\n",i+1,dragon_solution_length[i]);
  return 0;
 }
 if(!load_level(0))return 8;
 while(1){
  draw();
  if(level_done()){
   printf("Puzzlesolved! Press N to continue or Q to quit.\n");
  }
  if(chapter==LEVEL_COUNT-1&&level_done())
   printf("Campaign completed; final stage is complete.\n");
  char buffer[64];
  if(!fgets(buffer,sizeof(buffer),stdin))break;
  for(int i=0;buffer[i];i++){
   char key=buffer[i];
   if(key=='q'||key=='Q')return 0;
   if(key=='r'||key=='R'){load_level(chapter);break;}
   if(key=='u'||key=='U'){rollback();continue;}
   if(key=='h'||key=='H'){
    if(state.moves==0)
     printf("Canonical first input: %c\n",dragon_solutions[chapter][0]);
    else printf("Restart to view canonical opening move.\n");
    break;
   }
   if(key=='n'||key=='N'){
    if(level_done()&&chapter+1<LEVEL_COUNT)load_level(chapter+1);
    break;
   }
   if(!level_done())perform(key);
  }
 }
 return 0;
}
'''

def emit_native_puzzle(*,seed:int,stages:int=4,difficulty:int=4)->dict[str,str]:
    if isinstance(stages,bool) or not isinstance(stages,int) or not 1<=stages<=MAX_LEVELS:
        raise ValueError("native puzzle stages must be 1..8")
    layouts=[];solutions=[];proofs=[]
    for index in range(stages):
        grid=transformed_level(index,seed,difficulty)
        path,states=solve_grid(grid)
        start,boxes,goals,walls=_parse(grid)
        layouts.append(grid);solutions.append(path)
        proofs.append(LevelProof(index,path,len(path),states,len(boxes),
             sha256("\n".join(grid).encode()).hexdigest(),
             sha256(path.encode()).hexdigest()))
    rows=["  {\n"+",\n".join('    "'+row+'"' for row in grid)+"\n  }"
          for grid in layouts]
    header=(
       "#ifndef DRAGON_PUZZLE_H\n#define DRAGON_PUZZLE_H\n"
       f"#define LEVEL_W {WIDTH}\n#define LEVEL_H {HEIGHT}\n"
       f"#define LEVEL_COUNT {stages}\n"
       "static const char dragon_levels[LEVEL_COUNT][LEVEL_H][LEVEL_W+1]={\n"+
       ",\n".join(rows)+"\n};\n"
       "static const char* dragon_solutions[LEVEL_COUNT]={"+
       ", ".join('"'+x+'"' for x in solutions)+"};\n"+
       "static const int dragon_solution_length[LEVEL_COUNT]={"+
       ", ".join(str(len(p)) for p in solutions)+"};\n"
       "#endif\n"
    )
    cmake="""\
cmake_minimum_required(VERSION 3.16)
project(DragonNativePuzzle C)
set(CMAKE_C_STANDARD 99)
add_executable(dragon_game src/main.c)
target_include_directories(dragon_game PRIVATE include)
if(MSVC)
  target_compile_options(dragon_game PRIVATE /W3)
else()
  target_compile_options(dragon_game PRIVATE -Wall -Wextra -Wpedantic)
endif()
"""
    make="""\
CC ?= cc
CFLAGS ?= -O2 -std=c99 -Wall -Wextra -pedantic
all: dragon_game
dragon_game: src/main.c include/dragon_puzzle.h
\t$(CC) $(CFLAGS) -Iinclude src/main.c -o dragon_game
selftest: dragon_game
\t./dragon_game --selftest
clean:
\trm -f dragon_game
"""
    info={
      "schema":"skeleton.ai.dragon.puzzle_proof.v1",
      "mode":"original_native_sokoban",
      "search":"exact bounded BFS over player location and crate set",
      "seed":seed,"stages":stages,"difficulty":difficulty,
      "level_proofs":[asdict(p) for p in proofs],
      "native_runtime_test_required":True,
      "proof_scope":"optimal abstract grid moves, not C executable verification",
    }
    readme=(
       "# Dragon Original Native Puzzle Adventure\n\n"
       "This project builds a real standalone C99 terminal game. No browser,"
       " SDL2 or framework is required. Compile: make, or cmake -S . -B build"
       " then cmake --build build. Run ./dragon_game interactively (Windows:"
       " dragon_game.exe). Each level is generated from original hand-authored"
       " puzzle patterns under deterministic geometric transformations and"
       " independently solved by exact BFS before export. Execute"
       " ./dragon_game --selftest for real native move replay and completion."
       " Wall graphics are ANSI/ASCII terminal cells, not 3D console renders."
       " Build/run status remains source_generated until an actual compiler"
       " and runner confirm it.\n"
    )
    from .dragon_native_puzzle_hints import enable_live_hints
    runtime=enable_live_hints(C_SOURCE)
    return {"src/main.c":runtime,"include/dragon_puzzle.h":header,
            "CMakeLists.txt":cmake,"Makefile":make,
            "dragon-puzzle-proof.json":json.dumps(info,sort_keys=True,indent=2)+"\n",
            "README.puzzle.md":readme}
