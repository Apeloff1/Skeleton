"""Native C99 original-game save/restore with exact level provenance.

One tiny local save slot in the game's working directory. Numeric fields,
frame/state limits and hashed original map identity are checked before loading.
No scripts, external asset paths or user-identifying data are stored.
A selftest proves resume of a modified board and rejection of corrupt saves.
"""
from __future__ import annotations

SCHEMA="skeleton.ai.dragon.original_native_save_v1"
SOURCE='''/* Bounded local puzzle save slot: never loads code or remote data.
   This state fingerprint detects accidents/foreign saves; not authentication.
   The game itself does not grant AI memory or learning XP. */
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif
#define DRAGON_SAVE_NAME "dragon-save-v1.dat"
#define DRAGON_TEMP_NAME "dragon-save-v1.tmp"
static uint32_t game_map_fingerprint(void){
 uint32_t h=2166136261u;
 for(int level=0;level<LEVEL_COUNT;level++){
  for(int row=0;row<LEVEL_H;row++)
   for(int col=0;col<LEVEL_W;col++){
    uint8_t ch=(uint8_t)dragon_levels[level][row][col];
    h=(h^ch)*16777619u;
   }
 }
 return h;
}
static uint32_t save_state_digest(int level,State st,uint32_t game_id){
 uint32_t h=game_id;
 h=trace_word(h,(uint32_t)level);
 h=trace_word(h,(uint32_t)st.player);
 h=trace_word(h,(uint32_t)st.count);
 for(int n=0;n<st.count;n++)
  h=trace_word(h,(uint32_t)st.boxes[n]);
 h=trace_word(h,(uint32_t)st.moves);
 return trace_word(h,(uint32_t)st.pushes);
}
static int replace_local_original_save(const char*temp,const char*target){
#ifdef _WIN32
 /* Windows C runtime rename() cannot reliably overwrite a previous file.
    MoveFileExA replaces the bounded fixed-name slot on the same volume. */
 return MoveFileExA(temp,target,MOVEFILE_REPLACE_EXISTING|
                               MOVEFILE_WRITE_THROUGH)!=0;
#else
 return rename(temp,target)==0;
#endif
}
static int write_local_original_save(void){
 FILE*handle=fopen(DRAGON_TEMP_NAME,"wb");
 if(!handle)return 0;
 uint32_t map=game_map_fingerprint();
 uint32_t state_digest=save_state_digest(chapter,state,map);
 int bytes=fprintf(handle,
  "DRAGON_SAVE_1 %08x %d %d %d %d %d %d %d %d %d %08x\\n",
  (unsigned)map,chapter,state.player,state.count,
  state.boxes[0],state.boxes[1],state.boxes[2],
  state.moves,state.pushes,LEVEL_COUNT,(unsigned)state_digest);
 int fine=bytes>0&&bytes<160&&fflush(handle)==0&&!ferror(handle);
 if(fclose(handle)!=0)fine=0;
 if(!fine){remove(DRAGON_TEMP_NAME);return 0;}
 /* Move only the fixed-name bounded local save slot into place after
    flushing. Filesystem crash durability is not independently certified. */
 if(!replace_local_original_save(DRAGON_TEMP_NAME,DRAGON_SAVE_NAME)){
  remove(DRAGON_TEMP_NAME);return 0;
 }
 return 1;
}
static int read_local_original_save(void){
 FILE*handle=fopen(DRAGON_SAVE_NAME,"rb");
 if(!handle)return 0;
 char data[180];
 size_t len=fread(data,1,sizeof(data),handle);
 int extra=fgetc(handle);
 int closed=fclose(handle);
 if(closed!=0||extra!=EOF||len==0||len>=sizeof(data))return 0;
 data[len]=0;
 unsigned old_map=0,check=0;
 int level=0,hero=0,count=0,box0=0,box1=0,box2=0;
 int moves=0,pushes=0,stages=0,consumed=0;
 if(sscanf(data,
  "DRAGON_SAVE_1 %x %d %d %d %d %d %d %d %d %d %x%n",
  &old_map,&level,&hero,&count,&box0,&box1,&box2,
  &moves,&pushes,&stages,&check,&consumed)!=11)return 0;
 if(consumed<=0||data[consumed]!='\\n'||data[consumed+1]!=0)return 0;
 if(old_map!=game_map_fingerprint()||stages!=LEVEL_COUNT||
    level<0||level>=LEVEL_COUNT||count<1||count>3||
    hero<0||hero>=N||moves<0||moves>1024||
    pushes<0||pushes>moves)return 0;
 State replay;
 memset(&replay,0,sizeof(replay));
 replay.player=hero;
 replay.count=count;
 replay.boxes[0]=box0;
 replay.boxes[1]=box1;
 replay.boxes[2]=box2;
 replay.moves=moves;
 replay.pushes=pushes;
 if(check!=(unsigned)save_state_digest(level,replay,old_map))return 0;
 /* Validate every coordinate against the exact target campaign grid,
    without altering active state until all checks pass. */
 for(int idx=0;idx<count;idx++){
  int spot=replay.boxes[idx];
  if(spot<0||spot>=N||spot==hero||
     dragon_levels[level][spot/LEVEL_W][spot%LEVEL_W]=='#')return 0;
  for(int j=0;j<idx;j++)if(replay.boxes[j]==spot)return 0;
 }
 if(dragon_levels[level][hero/LEVEL_W][hero%LEVEL_W]=='#')return 0;
 if(!load_level(level))return 0;
 state=replay;
 undo_count=0;
 return 1;
}
static int original_save_selftest(void){
 if(!load_level(0))return 51;
 /* Authored worlds may start against any wall or crate. Follow the exact
    solver's first proven legal move rather than hard-coding rightward input. */
 if(!dragon_solutions[0][0]||!perform(dragon_solutions[0][0]))return 52;
 State reference=state;
 if(!write_local_original_save())return 53;
 if(!load_level(0))return 54;
 if(!read_local_original_save())return 55;
 if(state.player!=reference.player||
    state.moves!=reference.moves||
    state.pushes!=reference.pushes||
    state.count!=reference.count)return 56;
 for(int i=0;i<state.count;i++)
  if(state.boxes[i]!=reference.boxes[i])return 57;
 FILE*corrupt=fopen(DRAGON_SAVE_NAME,"wb");
 if(!corrupt)return 58;
 fputs("FOREIGN_ROM_SOURCE",corrupt);
 fclose(corrupt);
 if(read_local_original_save())return 59;
 remove(DRAGON_SAVE_NAME);
 printf("DRAGON_NATIVE_SAVE_SELFTEST PASS\\n");
 return 0;
}
'''
ENTRY='int main(int argc,char**argv){'
CONTROL="   if(key=='h'||key=='H'){"
CONTROL_ACTION='''   if(key=='k'||key=='K'){
    printf("Local original game saved: %s\\n",
           write_local_original_save()?"yes":"no");break;
   }
   if(key=='l'||key=='L'){
    printf("Local original game resumed: %s\\n",
           read_local_original_save()?"yes":"no");break;
   }
'''


def enable_native_save(source:str)->str:
    if not isinstance(source,str) or source.count(ENTRY)!=1 or source.count(CONTROL)!=1:
        raise ValueError("original C99 save insertion points missing")
    if "static uint32_t trace_word" not in source:
        raise ValueError("original C99 state trace is required for saved-game identity")
    result=source.replace(ENTRY,SOURCE+"\n"+ENTRY,1)
    result=result.replace(CONTROL,CONTROL_ACTION+CONTROL,1)
    result=result.replace(
        ENTRY,ENTRY+"\n"
        ' if(argc==2&&!strcmp(argv[1],"--save-selftest"))return original_save_selftest();',1,
    )
    return result
