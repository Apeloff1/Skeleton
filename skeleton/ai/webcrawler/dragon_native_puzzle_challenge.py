"""Native original-game challenge progression with solver-referenced grades.

These are in-game, ephemeral score/stars, NOT assistant training XP or durable
knowledge authority. Optimal traces come from the authoritative exact BFS.
A replay that makes extra legal moves earns fewer stars; no fake trophies are
issued for incomplete or unverified levels.
"""
from __future__ import annotations
from dataclasses import dataclass

SCHEMA="skeleton.ai.dragon.native_puzzle_challenge.v1"

@dataclass(frozen=True)
class ChallengeResult:
    schema:str
    completed:bool
    shortest_moves:int
    actual_moves:int
    total_pushes:int
    stars:int
    efficiency_percent:int
    bonus_score:int


def grade(original_solution_length:int,actual_moves:int,pushes:int,
          *,solved:bool)->ChallengeResult:
    if (type(original_solution_length) is not int or
            not 1<=original_solution_length<=400 or
            type(actual_moves) is not int or not 0<=actual_moves<=1024 or
            type(pushes) is not int or not 0<=pushes<=actual_moves or
            type(solved) is not bool):
        raise ValueError("invalid original puzzle challenge evidence")
    if not solved:
        return ChallengeResult(SCHEMA,False,original_solution_length,
                               actual_moves,pushes,0,0,0)
    # A completed solution cannot beat the independently proved shortest
    # path. Reject fabricated solved flags rather than handing out medals.
    if actual_moves < original_solution_length:
        raise ValueError("completed puzzle move count contradicts BFS proof")
    efficiency=min(100,(100*original_solution_length)//max(1,actual_moves))
    if actual_moves<=original_solution_length:
        stars=3
    elif actual_moves*4<=original_solution_length*5:
        stars=2
    else:
        stars=1
    bonus=max(0,1000-10*max(0,actual_moves-original_solution_length))
    bonus+=100*stars
    return ChallengeResult(SCHEMA,True,original_solution_length,
                           actual_moves,pushes,stars,efficiency,bonus)


MARKER='static void draw(void){'
ENTRY='int main(int argc,char**argv){'
NEW_C=r'''
/* Original game challenge stars derive from shortest solver-proven trace.
   These are LOCAL gameplay rewards only; they cannot mint crawler XP. */
static int native_puzzle_stars(void){
 if(!level_done())return 0;
 int minimum=dragon_solution_length[chapter];
 if(state.moves<=minimum)return 3;
 if((long)state.moves*4<=(long)minimum*5)return 2;
 return 1;
}
static int native_puzzle_efficiency(void){
 if(!level_done())return 0;
 int optimal=dragon_solution_length[chapter];
 int moves=state.moves?state.moves:1;
 int score=(100*optimal)/moves;
 return score>100?100:score;
}
static int native_puzzle_bonus(void){
 if(!level_done())return 0;
 int excess=state.moves-dragon_solution_length[chapter];
 if(excess<0)excess=0;
 int points=1000-10*excess;
 if(points<0)points=0;
 return points+100*native_puzzle_stars();
}
static int challenge_selftest(void){
 for(int level=0;level<LEVEL_COUNT;level++){
  if(!load_level(level))return 41;
  if(native_puzzle_stars()!=0)return 42;
  const char *solution=dragon_solutions[level];
  for(int i=0;i<dragon_solution_length[level];i++)
   if(!perform(solution[i]))return 43;
  if(!level_done()||native_puzzle_stars()!=3||
     native_puzzle_efficiency()!=100)return 44;
  /* Exercise the scored gameplay contract in the native binary; this
     also ensures the bonus function is never an unused C99 artifact. */
  if(native_puzzle_bonus()!=1300)return 45;
  printf("PUZZLE_CHALLENGE_PASS level=%d stars=%d optimal=%d\n",
         level+1,native_puzzle_stars(),dragon_solution_length[level]);
 }
 printf("DRAGON_NATIVE_CHALLENGE PASS stages=%d\n",LEVEL_COUNT);
 return 0;
}
'''
PRESENT=''' printf("Crates on goals: ");
 int placed=0;
 for(int i=0;i<state.count;i++)placed+=goals[state.boxes[i]]?1:0;
 printf("%d / %d\\n",placed,state.count);'''
STATS=''' printf("Crates on goals: ");
 int placed=0;
 for(int i=0;i<state.count;i++)placed+=goals[state.boxes[i]]?1:0;
 printf("%d / %d\\n",placed,state.count);
 printf("Optimal steps: %d | current: %d | stars: %d | efficiency: %d%%\\n",
        dragon_solution_length[chapter],state.moves,
        native_puzzle_stars(),native_puzzle_efficiency());'''


def enable_native_challenge(native_source:str)->str:
    if not isinstance(native_source,str) or native_source.count(MARKER)!=1:
        raise ValueError("original C99 challenge insertion target unavailable")
    if native_source.count(ENTRY)!=1 or native_source.count(PRESENT)!=1:
        raise ValueError("native original game progress display changed")
    source=native_source.replace(MARKER,NEW_C+"\n"+MARKER,1)
    source=source.replace(PRESENT,STATS,1)
    source=source.replace(
        ENTRY,ENTRY+"\n"
        ' if(argc==2&&!strcmp(argv[1],"--challenge-selftest"))return challenge_selftest();',1,
    )
    return source
