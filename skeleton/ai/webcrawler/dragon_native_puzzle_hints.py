"""Embed bounded current-position Sokoban BFS into the original C99 game.

The initial exact Python proof remains the authoritative generated level proof.
This new in-game C99 solver computes a fresh shortest path from the ACTUAL
player + crate configuration, not a misleading opening move. Its hashtable and
node pools have explicit limits, and no third-party code or network access.
"""
from __future__ import annotations

MARKER = 'static void draw(void){'
MAIN = 'int main(int argc,char**argv){'
OLD_HINT = """   if(key=='h'||key=='H'){
    if(state.moves==0)
     printf("Canonical first input: %c\\n",dragon_solutions[chapter][0]);
    else printf("Restart to view canonical opening move.\\n");
    break;
   }"""
NEW_HINT = """   if(key=='h'||key=='H'){
    char next=shortest_hint();
    if(next)printf("Next shortest move from current position: %c\\n",next);
    else if(level_done())printf("This stage is already complete.\\n");
    else printf("No solution found inside the bounded live hint search.\\n");
    break;
   }"""

SOLVER = r'''
/* Native C99 live Sokoban shortest-path search.
   Open-addressing hash table holds at most 50k unique states. Every state
   encodes the ACTUAL player and 1..3 crates on the generated 120-cell map.
   Hash collisions are checked by exact state equality before deduplication.
   Returned move is first move of a shortest BFS path; no remote AI call. */
#define HINT_NODES 50000
#define HINT_BUCKETS 131071
typedef struct {
 unsigned char player, crates[3];
 int parent;
 char action;
} HintNode;
static int hint_same(const HintNode*a,const HintNode*b,int crates){
 if(a->player!=b->player)return 0;
 for(int k=0;k<crates;k++)if(a->crates[k]!=b->crates[k])return 0;
 return 1;
}
static unsigned hint_hash(const HintNode*n,int crates){
 unsigned result=2166136261u;
 result=(result^n->player)*16777619u;
 for(int k=0;k<crates;k++)result=(result^n->crates[k])*16777619u;
 return result;
}
static int hint_is_solved(const HintNode*n,int count){
 if(count==0)return 0;
 for(int k=0;k<count;k++)if(!goals[n->crates[k]])return 0;
 return 1;
}
static void hint_sort(HintNode*n,int count){
 for(int a=0;a<count;a++)for(int b=a+1;b<count;b++)
  if(n->crates[a]>n->crates[b]){
   unsigned char tmp=n->crates[a];
   n->crates[a]=n->crates[b];
   n->crates[b]=tmp;
  }
}
static int hint_insert(const HintNode*n, HintNode*nodes,int*bucket,int current){
 unsigned key=hint_hash(n,state.count)%HINT_BUCKETS;
 for(unsigned tries=0;tries<HINT_BUCKETS;tries++){
  int seen=bucket[key];
  if(seen<0){
   if(current>=HINT_NODES)return -2;
   nodes[current]=*n;
   bucket[key]=current;
   return current;
  }
  if(hint_same(n,&nodes[seen],state.count))return -1;
  key=(key+1u)%HINT_BUCKETS;
 }
 return -2;
}
static char shortest_hint(void){
 if(level_done())return 0;
 HintNode *nodes=(HintNode*)calloc(HINT_NODES,sizeof(HintNode));
 int *visited=(int*)malloc(sizeof(int)*HINT_BUCKETS);
 if(!nodes||!visited){
  free(nodes);free(visited);return 0;
 }
 for(int j=0;j<HINT_BUCKETS;j++)visited[j]=-1;
 HintNode start;
 memset(&start,0,sizeof(start));
 start.player=(unsigned char)state.player;
 for(int i=0;i<state.count;i++)start.crates[i]=(unsigned char)state.boxes[i];
 hint_sort(&start,state.count);
 start.parent=-1;
 int count=1,head=0,solution=-1;
 nodes[0]=start;
 visited[hint_hash(&start,state.count)%HINT_BUCKETS]=0;
 const char keys[4]={'a','d','w','s'};
 const int dxs[4]={-1,1,0,0},dys[4]={0,0,-1,1};
 while(head<count&&count<HINT_NODES){
  HintNode current=nodes[head];
  if(hint_is_solved(&current,state.count)){solution=head;break;}
  int px=current.player%LEVEL_W,py=current.player/LEVEL_W;
  for(int direction=0;direction<4;direction++){
   int nx=px+dxs[direction],ny=py+dys[direction];
   if(nx<0||nx>=LEVEL_W||ny<0||ny>=LEVEL_H)continue;
   int dest=ny*LEVEL_W+nx;
   if(is_wall(dest))continue;
   HintNode next=current;
   next.player=(unsigned char)dest;
   next.parent=head;
   next.action=keys[direction];
   int moving=-1;
   for(int k=0;k<state.count;k++)
    if(current.crates[k]==dest)moving=k;
   if(moving>=0){
    int bx=nx+dxs[direction],by=ny+dys[direction];
    if(bx<0||bx>=LEVEL_W||by<0||by>=LEVEL_H)continue;
    int ahead=by*LEVEL_W+bx;
    if(is_wall(ahead))continue;
    int occupied=0;
    for(int k=0;k<state.count;k++)
     if(current.crates[k]==ahead)occupied=1;
    if(occupied)continue;
    next.crates[moving]=(unsigned char)ahead;
    hint_sort(&next,state.count);
   }
   int id=hint_insert(&next,nodes,visited,count);
   if(id>=0)count++;
  }
  head++;
 }
 char first=0;
 if(solution>=0){
  int cursor=solution;
  while(nodes[cursor].parent>0)cursor=nodes[cursor].parent;
  if(nodes[cursor].parent==0)first=nodes[cursor].action;
 }
 free(visited);free(nodes);
 return first;
}
/* Selftest native hint correctness in every actual generated campaign stage,
   including starting state, post-first-move position and finished stage. */
static int hints_selftest(void){
 for(int level=0;level<LEVEL_COUNT;level++){
  if(!load_level(level))return 10;
  char step=shortest_hint();
  if(!step||step!=dragon_solutions[level][0])return 11;
  if(!perform(step))return 12;
  if(!level_done()&&!shortest_hint())return 13;
  if(!load_level(level))return 14;
  const char*proof=dragon_solutions[level];
  for(int i=0;i<dragon_solution_length[level];i++)
   if(!perform(proof[i]))return 15;
  if(!level_done()||shortest_hint()!=0)return 16;
  printf("PUZZLE_HINT_PASS level=%d\n",level+1);
 }
 printf("DRAGON_NATIVE_PUZZLE_HINTS PASS stages=%d\n",LEVEL_COUNT);
 return 0;
}
'''


def enable_live_hints(native_source: str) -> str:
    if not isinstance(native_source, str):
        raise ValueError("C99 puzzle source must be text")
    if native_source.count(MARKER) != 1 or native_source.count(MAIN) != 1:
        raise ValueError("puzzle runtime structure unexpectedly changed")
    if native_source.count(OLD_HINT) != 1:
        raise ValueError("previous hint implementation no longer matches")
    source = native_source.replace(MARKER, SOLVER + "\n" + MARKER, 1)
    source = source.replace(OLD_HINT, NEW_HINT, 1)
    source = source.replace(
        ' if(argc==2&&!strcmp(argv[1],"--selftest"))return selftest();',
        ' if(argc==2&&!strcmp(argv[1],"--selftest"))return selftest();\n'
        ' if(argc==2&&!strcmp(argv[1],"--hint-selftest"))return hints_selftest();',
        1,
    )
    if source == native_source or "shortest_hint" not in source:
        raise ValueError("native shortest hint source not installed")
    return source
