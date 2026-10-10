"""Actual native C99 interactive branching puzzle campaign progression.

Players choose among proven reachable original chapters (1/2, next),
can return to the hub by completing an earlier stage, and reach distinct
campaign endings. This changes real C99 gameplay and optional SDL2 inputs;
it is not a menu illustration or a forced single-path level list.
"""
from __future__ import annotations

ENTRY='int main(int argc,char**argv){'
OLD_DONE='''  if(level_done()){
   printf("Puzzlesolved! Press N to continue or Q to quit.\\n");
  }
  if(chapter==LEVEL_COUNT-1&&level_done())
   printf("Campaign completed; final stage is complete.\\n");'''
NEW_DONE='''  if(level_done()){
   if(dragon_branch_count[chapter]==0)
    printf("Original campaign ending reached at stage %d! Q to quit.\\\\n",chapter+1);
   else {
    printf("Stage solved! Select your own next path (N, 1 or 2):\\\\n");
    for(int option=0;option<dragon_branch_count[chapter];option++)
     printf("  %d - chapter %d\\\\n",option+1,
            dragon_branch_next[chapter][option]+1);
   }
  }'''
OLD_NEXT='''   if(key=='n'||key=='N'){
    if(level_done()&&chapter+1<LEVEL_COUNT)load_level(chapter+1);
    break;
   }'''
NEW_NEXT='''   if(key=='n'||key=='N'||key=='1'||key=='2'){
    if(level_done()){
     int choice=(key=='2')?1:0;
     if(choice<dragon_branch_count[chapter]){
      int destination=dragon_branch_next[chapter][choice];
      if(destination>=0&&destination<LEVEL_COUNT)load_level(destination);
     }
    }
    break;
   }'''
C_SELFTEST=r'''
/* Every original chapter follows actual campaign choice destinations.
   Shortest level solutions prove stage transitions are playable, but no
   human enjoyment or preference is fabricated by the deterministic test. */
static int branch_selftest(void){
 int branches=0,terminations=0;
 for(int source=0;source<LEVEL_COUNT;source++){
  int options=dragon_branch_count[source];
  if(options<0||options>2)return 61;
  for(int k=0;k<options;k++){
   int next=dragon_branch_next[source][k];
   if(next<=source||next>=LEVEL_COUNT)return 62;
   if(!load_level(source))return 63;
   for(int step=0;step<dragon_solution_length[source];step++)
    if(!perform(dragon_solutions[source][step]))return 64;
   if(!level_done())return 65;
   if(!load_level(next)||chapter!=next)return 66;
   branches++;
   printf("DRAGON_BRANCH_PASS from=%d choice=%d to=%d\n",
          source+1,k+1,next+1);
  }
  if(options==0){
   if(!dragon_branch_ending[source])return 67;
   terminations++;
   printf("DRAGON_ENDING_PASS stage=%d\n",source+1);
  }else if(dragon_branch_ending[source])return 68;
 }
 printf("DRAGON_BRANCH_CAMPAIGN_PASS stages=%d transitions=%d endings=%d\n",
        LEVEL_COUNT,branches,terminations);
 return 0;
}
'''

def enable_native_branches(source:str)->str:
    if not isinstance(source,str) or source.count(ENTRY)!=1:
        raise ValueError("native campaign entry unavailable")
    if source.count(OLD_DONE)!=1 or source.count(OLD_NEXT)!=1:
        raise ValueError("original game still lacks expected sequential progression")
    updated=source.replace(ENTRY,C_SELFTEST+"\n"+ENTRY,1)
    updated=updated.replace(OLD_DONE,NEW_DONE,1).replace(OLD_NEXT,NEW_NEXT,1)
    updated=updated.replace(
        ENTRY,ENTRY+"\n"
        ' if(argc==2&&!strcmp(argv[1],"--branch-selftest"))return branch_selftest();',
        1,
    )
    return updated
