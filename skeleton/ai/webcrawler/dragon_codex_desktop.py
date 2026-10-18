"""Original interactive C99 Codex game source, no mandatory ending.

Unlike a mere hardware profile, this emits C99 that a normal C compiler can
compile as a real playable original console-terminal world: 128 skills,
sixteen time-gated alternate routes, movement, waiting, discoveries,
world-era progression and source-certified achievement tests.
Cartridge consoles use the separate bounded content projection instead:
C99 terminal I/O is not advertised as a playable Game Boy/PS1 ROM.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256

from .dragon_world_codex import CodexAddress,validate
from .dragon_world_codex_runtime import GATE_MODES,GATE_VECTORS,ALL_GATE_MODES,ALL_GATE_VECTORS
from .dragon_living_world import _sha

SCHEMA="skeleton.ai.dragon.codex_native_c99.v1"

@dataclass(frozen=True)
class CodexDesktopProject:
    schema:str
    source_name:str
    source:str
    source_sha256:str
    game_rules_sha256:str
    source_license_scope:str
    active_mechanics:tuple[str,...]
    actual_native_binary_produced:bool
    independently_compiled:bool
    compiled_game_selftest_passed:bool


C99=r'''/* ORIGINAL DRAGON LIVING-WORLD GAME — generated C99, no copied game IP.
 * Licensed original source design must be attested separately before release.
 * Commands: help, study N, wait, rest, gate N, explore, status, map, quit.
 * No mandatory final boss. The world remains explorable after any gateway.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#define AXES @AXES@
#define DOMAINS @DOMAINS@
#define MAX_TURNS 10000000
static const unsigned char world_levels[AXES] = {@LEVELS@};
static const int gx[DOMAINS] = {@GATE_X@};
static const int gy[DOMAINS] = {@GATE_Y@};
static const char* gate_names[DOMAINS] = {@GATE_NAMES@};
static const char* original_world_id = "@WORLD_DIGEST@";
static int skills[AXES],turns=0,x=0,y=0,era=0,opened[DOMAINS],visits=0;
static int world_risk=0;
@SKY_STATE@
static int gate_needs(int idx) {
 return 1+world_levels[idx]/64;
}
static int gate_earliest(int domain) {
 return 2+world_levels[domain*8]/16;
}
static int gate_period(int domain) {
 return 2+world_levels[domain*8+1]%7;
}
static int gate_open(int domain) {
 if (domain<0||domain>=DOMAINS)return 0;
 int first=domain*8;
@SKY_GATE_CONDITION@
 return skills[first]>=gate_needs(first) &&
        skills[first+1]>=gate_needs(first+1) &&
        turns>=gate_earliest(domain) &&
        turns%gate_period(domain)==0;
}
static void reset_world(void) {
 memset(skills,0,sizeof skills);
 memset(opened,0,sizeof opened);
 turns=0;x=0;y=0;era=0;visits=0;world_risk=0;
@SKY_RESET@
}
static int study_skill(int index) {
 if (index<0||index>=AXES||turns>=MAX_TURNS)return 0;
 if (skills[index]<100000)skills[index]++;
 turns++;
 if (((index/8)==11||(index/8)==15) && skills[index]%4==0)era++;
 return 1;
}
static int wait_world(void) {
 if (turns>=MAX_TURNS)return 0;
 turns++;
 return 1;
}
static int use_gate(int domain) {
 if (!gate_open(domain)||turns>=MAX_TURNS)return 0;
 x+=gx[domain];y+=gy[domain];
 turns++;visits++;
 opened[domain]=1;
@SKY_TRAVEL@
 world_risk+=world_levels[domain*8+1]/48;
 if(domain==9||domain==11||domain==15)era++;
 return 1;
}
static int explore(void) {
 if(turns>=MAX_TURNS)return 0;
 x+=(turns%3)-1;
 y+=((turns+1)%3)-1;
 turns++;
 return 1;
}
static void status(void) {
 printf("World %s\n",original_world_id);
 printf("Turn %d  Era %d  Position (%d,%d)  Journeys %d  Risk %d\n",
         turns,era,x,y,visits,world_risk);
 printf("No mandatory ending; explore, learn, wait, revisit, or quit.\n");
@SKY_STATUS@
 for(int d=0;d<DOMAINS;d++) {
  int a=d*8;
  int period=gate_period(d);
  int earliest=gate_earliest(d);
  int next=turns>earliest?turns:earliest;
  next+=((period-(next%period))%period);
  printf("%2d %-28s mastery %d/%d,%d/%d next window %d open=%d visited=%d\n",
   d,gate_names[d],skills[a],gate_needs(a),
   skills[a+1],gate_needs(a+1),next,gate_open(d),opened[d]);
 }
}
static int check_all_gates(void) {
 for(int d=0;d<DOMAINS;d++){
  reset_world();
  if(gate_open(d))return 10;
  int a=d*8;
  for(int i=0;i<gate_needs(a);i++)if(!study_skill(a))return 11;
  for(int i=0;i<gate_needs(a+1);i++)if(!study_skill(a+1))return 12;
@SKY_SELFTEST@
  for(int i=0;i<48 && !gate_open(d);i++)if(!wait_world())return 13;
  if(!gate_open(d))return 14;
  if(!use_gate(d))return 15;
  if(x!=gx[d] || y!=gy[d] || !opened[d] || visits!=1)return 16;
  if(!explore())return 17;
  if(!wait_world())return 18;
  printf("PROVED %02d %-28s turns=%d arrived=%d,%d era=%d\n",
         d,gate_names[d],turns,x,y,era);
 }
 reset_world();
 printf("DRAGON_CODEX_SELFTEST_PASS @DOMAINS@ actual gate unlocks and real journeys\n");
 return 0;
}
static void help(void) {
 puts("Original World Codex: @AXES@ trained axes and @DOMAINS@ earned travel gates.");
 puts("study <0..@LAST_AXIS@> — train one skill and advance actual world time");
 puts("wait — advance a world turn; all gates have periodic openings");
 puts("rest — recover attention; advance time without erasing progress");
 puts("gate <0..@LAST_GATE@> — require BOTH relevant trained skills and time window");
 puts("explore — wander the original no-final-boss world");
 puts("map — show all gateway statuses; status — report current world");
 puts("quit — leave session; selftest is separate executable --selftest");
}
int main(int argc,char**argv) {
 if(argc==2 && strcmp(argv[1],"--selftest")==0)return check_all_gates();
 if(argc==2 && strcmp(argv[1],"--list")==0){status();return 0;}
 if(argc!=1){fputs("Usage: dragon-codex [--selftest|--list]\n",stderr);return 2;}
 reset_world();
 puts("Dragon World Codex — original playable endless world. Type help.");
 char line[160];
 while(fgets(line,sizeof line,stdin)){
  int id=-1;char more=0;
  if(strcmp(line,"quit\n")==0||strcmp(line,"quit")==0)break;
  if(strcmp(line,"help\n")==0){help();continue;}
  if(strcmp(line,"status\n")==0||strcmp(line,"map\n")==0) {
   status();continue;
  }
  if(strcmp(line,"wait\n")==0||strcmp(line,"rest\n")==0){
   if(!wait_world())puts("World clock exhausted");
   continue;
  }
  if(strcmp(line,"explore\n")==0){if(!explore())puts("Clock exhausted");continue;}
  if(sscanf(line,"study %d %c",&id,&more)==1) {
   if(study_skill(id))printf("Skill %d learned at turn %d\n",id,turns);
   else puts("Invalid skill or exhausted timeline");
   continue;
  }
  if(sscanf(line,"gate %d %c",&id,&more)==1) {
   if(use_gate(id))printf("Earned journey %d reached %d,%d at turn %d\n",
                          id,x,y,turns);
   else puts("Passage locked: train both skills and await its next window");
   continue;
  }
  puts("Unknown action; type help.");
 }
 return 0;
}
'''

def emit_codex_c99(address:CodexAddress)->CodexDesktopProject:
    _,genes=validate(address)
    extended=any(genes.extension_values)
    count=192 if extended else 128
    modes=ALL_GATE_MODES if extended else GATE_MODES
    vectors=ALL_GATE_VECTORS if extended else GATE_VECTORS
    levels=",".join(str(value) for value in
                    genes.values+(genes.extension_values if extended else ()))
    xs=",".join(str(x) for x,_ in vectors)
    ys=",".join(str(y) for _,y in vectors)
    names=",".join('"'+name+'"' for name in modes)
    # Only include aerial rules in v3 source. Legacy C99 does not access
    # out-of-bounds controls and preserves its sixteen-domain behavior.
    aerial={
        "@SKY_STATE@":"static int sky_altitude=0;",
        "@SKY_GATE_CONDITION@":(
            " if(domain==16 && world_levels[128]>=96 && "
            "world_levels[131]<128 && skills[160]<2)return 0;"
        ),
        "@SKY_RESET@":" sky_altitude=0;",
        "@SKY_TRAVEL@":" if(domain==16)sky_altitude++;",
        "@SKY_STATUS@":(
            ' printf("Sky-island density %d  Cloud ocean %d  Altitude %d\\n",'
            'world_levels[128],world_levels[129],sky_altitude);'
        ),
        "@SKY_SELFTEST@":(
            "  if(d==16 && world_levels[128]>=96 && world_levels[131]<128)"
            "for(int k=0;k<2;k++)if(!study_skill(160))return 19;"
        ),
    } if extended else {token:"" for token in (
        "@SKY_STATE@","@SKY_GATE_CONDITION@","@SKY_RESET@",
        "@SKY_TRAVEL@","@SKY_STATUS@","@SKY_SELFTEST@",
    )}
    source=(C99.replace("@AXES@",str(count))
                 .replace("@DOMAINS@",str(len(modes)))
                 .replace("@LAST_AXIS@",str(count-1))
                 .replace("@LAST_GATE@",str(len(modes)-1))
                 .replace("@LEVELS@",levels)
                 .replace("@GATE_X@",xs)
                 .replace("@GATE_Y@",ys)
                 .replace("@GATE_NAMES@",names)
                 .replace("@WORLD_DIGEST@",address.codex_digest))
    for token,value in aerial.items():
        source=source.replace(token,value)
    if "@" in source:
        # Source may legitimately have @ in original game comments, but
        # unresolved template slots are always at-token sentinels.
        for token in ("@AXES@","@DOMAINS@","@LAST_AXIS@","@LAST_GATE@",
                      "@LEVELS@","@GATE_X@","@GATE_Y@",
                      "@GATE_NAMES@","@WORLD_DIGEST@",*aerial):
            if token in source:
                raise ValueError("incomplete original world C99 source")
    return CodexDesktopProject(
        schema=SCHEMA,source_name="dragon_codex_game.c",
        source=source,source_sha256=sha256(source.encode()).hexdigest(),
        game_rules_sha256=_sha([genes.values,*([genes.extension_values] if extended else []),modes,vectors]),
        source_license_scope="Original source; source production only. "
                             "Commercial redistribution requires rights review.",
        active_mechanics=(
            f"{count}_real_trainable_axes",f"{len(modes)}_time_gated_passages",
            "independent_gateway_selftest","persistent_world_clock",
            "multiple_routes","no_mandatory_ending","exploration",
            "world_era_progression",
            *(("sky_island_altitude","glider_or_skybridge_access") if extended else ()),
        ),
        actual_native_binary_produced=False,
        independently_compiled=False,
        compiled_game_selftest_passed=False,
    )


def inspect_c99_source(address:CodexAddress,project:CodexDesktopProject)->dict:
    verified=emit_codex_c99(address)
    if verified!=project:
        raise ValueError("original world desktop source or build claims were modified")
    return {
        "verified_source":True,
        "compiler_execution_not_claimed":True,
        "source_sha256":verified.source_sha256,
        "mechanics":list(verified.active_mechanics),
        "actual_c99_game":True,
        "claims":"native C99 source with genuinely playable game rules, "
                 "needs host compile and on-device review",
    }
