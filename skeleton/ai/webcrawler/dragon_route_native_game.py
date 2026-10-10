"""Generate a genuinely playable, stand-alone C99 original route-exploration game.

Compiles a checked graph into C arrays with real cash, energy, clocks,
timetables, first-visit rewards, unlocked/secret paths and weather constraints.
The player's route selection changes real game state. The native selftest
executes known journeys and compares resulting time/money/risk to independent
Python route replay. It is not a vehicle physics or 3D flight simulator.
"""
from __future__ import annotations
from dataclasses import asdict
from hashlib import sha256
import json

from .dragon_route_world import (
    World,Traveller,validate_world,validate_traveller,
    replay,portfolio,route_dictionary,MAX_HOPS,
)
from .dragon_route_taxonomy import ENVIRONMENT_FLAGS,MODES
from .dragon_route_world_factory import (
    make_frontier,scenario_digest,structural_report,
)
SCHEMA="skeleton.ai.dragon.original_native_route_game.v1"

C_GAME=r'''/* Original world routes, not commercial transit/spaceflight simulation.
   Generated C99 source follows exact bounded graph state transition rules. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "dragon_route_world.h"
typedef struct {
 int at,clock,elapsed,energy,cash,hops,waited,movement,spent,danger,fatigue,sights;
 int fuel,oxygen,mana,spent_fuel,spent_oxygen,spent_mana;
 uint64_t acquired,visited;
} JourneyState;
static JourneyState player;
static void reset_world(void){
 memset(&player,0,sizeof(player));
 player.at=DRAGON_START;
 player.clock=DRAGON_START_CLOCK;
 player.energy=DRAGON_START_ENERGY;
 player.cash=DRAGON_START_CASH;
 player.fuel=DRAGON_START_FUEL;
 player.oxygen=DRAGON_START_OXYGEN;
 player.mana=DRAGON_START_MANA;
 player.acquired=DRAGON_START_TOKENS|dragon_places[player.at].gifts;
 player.visited=UINT64_C(1)<<player.at;
 player.energy+=dragon_places[player.at].refill;
 if(player.energy>DRAGON_MAX_ENERGY)player.energy=DRAGON_MAX_ENERGY;
 player.cash+=dragon_places[player.at].money;
 player.sights+=dragon_places[player.at].scenery;
}
static int departure_wait(const DragonConnection*edge){
 if(edge->departure_count==0)return 0;
 int current=player.clock%1440;
 int best=1440;
 for(int i=0;i<edge->departure_count;i++){
  int d=(edge->departures[i]-current+1440)%1440;
  if(d<best)best=d;
 }
 return best;
}
static int step_world(int number){
 if(number<0||number>=DRAGON_EDGE_COUNT)return 0;
 const DragonConnection*edge=&dragon_connections[number];
 if(edge->from!=player.at)return 0;
 if((player.acquired&edge->requires)!=edge->requires)return 0;
 if(edge->requires_one&&!(player.acquired&edge->requires_one))return 0;
 if(edge->secret&&(player.acquired&edge->secret)!=edge->secret)return 0;
 if(edge->resistance&&(player.acquired&edge->resistance)!=edge->resistance)return 0;
 if((player.acquired&edge->consumes)!=edge->consumes)return 0;
 if(edge->weather_any&&!(DRAGON_WEATHER&edge->weather_any))return 0;
 if(DRAGON_WEATHER&edge->weather_none)return 0;
 int waiting=departure_wait(edge);
 if(player.elapsed+waiting+edge->minutes>DRAGON_MAX_MINUTES ||
    player.cash<edge->price||player.energy<edge->fatigue||
    player.fuel<edge->fuel||player.oxygen<edge->oxygen||
    player.mana<edge->mana||
    player.hops>=DRAGON_MAX_HOPS)return 0;
 player.cash-=edge->price;
 player.energy-=edge->fatigue;
 player.fuel-=edge->fuel;
 player.oxygen-=edge->oxygen;
 player.mana-=edge->mana;
 player.spent_fuel+=edge->fuel;
 player.spent_oxygen+=edge->oxygen;
 player.spent_mana+=edge->mana;
 player.acquired=(player.acquired&~edge->consumes)|edge->grants;
 player.clock+=waiting+edge->minutes;
 player.elapsed+=waiting+edge->minutes;
 player.waited+=waiting;
 player.movement+=edge->minutes;
 player.spent+=edge->price;
 player.danger+=edge->danger;
 player.fatigue+=edge->fatigue;
 player.sights+=edge->spectacle;
 player.at=edge->to;
 player.hops++;
 uint64_t mark=UINT64_C(1)<<player.at;
 if(!(player.visited&mark)){
  const DragonPlace*destination=&dragon_places[player.at];
  player.acquired|=destination->gifts;
  player.energy+=destination->refill;
  if(player.energy>DRAGON_MAX_ENERGY)player.energy=DRAGON_MAX_ENERGY;
  player.cash+=destination->money;
  if(player.cash>100000)player.cash=100000;
  player.sights+=destination->scenery;
  player.visited|=mark;
 }
 return 1;
}
static int run_probes(void){
 for(int p=0;p<DRAGON_PROBE_COUNT;p++){
  reset_world();
  const DragonProof*check=&dragon_probes[p];
  for(int i=0;i<check->steps;i++){
   if(!step_world(check->edges[i]))return 50;
  }
  if(player.at!=DRAGON_GOAL||player.hops!=check->steps ||
     player.elapsed!=check->minutes||player.spent!=check->spent ||
     player.danger!=check->danger||
     player.spent_fuel!=check->fuel||
     player.spent_oxygen!=check->oxygen||
     player.spent_mana!=check->mana)return 51;
  printf("DRAGON_ORIGINAL_ROUTE_PASS name=%s hops=%d minutes=%d fare=%d risk=%d fuel=%d oxygen=%d mana=%d\n",
   check->name,player.hops,player.elapsed,player.spent,player.danger,
   player.spent_fuel,player.spent_oxygen,player.spent_mana);
 }
 printf("DRAGON_ORIGINAL_WORLD_PASS probes=%d places=%d routes=%d\n",
        DRAGON_PROBE_COUNT,DRAGON_PLACE_COUNT,DRAGON_EDGE_COUNT);
 return 0;
}
static void show_world(void){
 printf("\nORIGINAL ROUTE WORLD | %s | clock=%02d:%02d | stamina %d/%d | cash %d | fuel %d | O2 %d | mana %d\n",
  dragon_places[player.at].id,(player.clock/60)%24,player.clock%60,
  player.energy,DRAGON_MAX_ENERGY,player.cash,
  player.fuel,player.oxygen,player.mana);
 if(player.at==DRAGON_GOAL){
  printf("GOAL REACHED: original game world completed in %d minutes!\n",
         player.elapsed);
  printf("You may restart the world to try an alternate approach.\n");
  return;
 }
 printf("Available segments (others may need knowledge, fare or conditions):\n");
 int offered=0;
 for(int id=0;id<DRAGON_EDGE_COUNT;id++){
  const DragonConnection*e=&dragon_connections[id];
  if(e->from!=player.at)continue;
  /* Unknown secrets are not printed to the player until discovered. */
  if(e->secret&&(player.acquired&e->secret)!=e->secret)continue;
  printf("  [%d] %-22s via %-18s -> %-18s %3d min %3d fare\n",
   id+1,e->id,e->mode,dragon_places[e->to].id,e->minutes,e->price);
  offered++;
 }
 if(!offered)printf("No known outgoing path. Try a different route after restart.\n");
}
static int interactive(void){
 reset_world();
 char buffer[80];
 for(;;){
  show_world();
  printf("Choose a route number, R restart, L list, Q quit: ");
  if(!fgets(buffer,sizeof(buffer),stdin))return 0;
  if(buffer[0]=='q'||buffer[0]=='Q')return 0;
  if(buffer[0]=='r'||buffer[0]=='R'){reset_world();continue;}
  if(buffer[0]=='l'||buffer[0]=='L'){show_world();continue;}
  char*end=NULL;
  long option=strtol(buffer,&end,10);
  if(end==buffer||(*end!='\n'&&*end!=0)||option<1||
     option>DRAGON_EDGE_COUNT){
   puts("Unknown original route number.");continue;
  }
  if(!step_world((int)option-1)){
   puts("That route is blocked by cost, gear, time, weather or world knowledge.");
  }
 }
}
int main(int argc,char**argv){
 if(argc==2&&!strcmp(argv[1],"--selftest"))return run_probes();
 if(argc==1)return interactive();
 fprintf(stderr,"Use --selftest for original verified game journeys.\n");
 return 2;
}
'''

# Audited, distinct original route witnesses. Every path is replayed against
# Python's real state machine before embedding any native selftest evidence.
EXAMPLES:dict[str,tuple[str,...]]={
 "taxi":("walk_to_bazaar","market_to_taxi","taxi_to_goal"),
 "bus":("walk_to_bazaar","market_to_bus","bus_to_goal"),
 "rail":("walk_to_bazaar","market_to_train","train_to_goal"),
 "ferry":("walk_to_bazaar","harbor_path","ferry_to_goal"),
 "air":("walk_to_bazaar","airport_path","airplane_depart","airplane_arrive"),
 "freeroam":(
   "forest_entry","forest_to_meadow","meadow_to_river",
   "river_to_forest","forest_to_meadow","meadow_to_goal",
 ),
 "secret":(
   "forest_entry","forest_to_ruins","ruins_return",
   "mine_sidepath","mine_return","secret_from_clue",
   "grotto_to_tunnel","tunnel_to_citadel",
 ),
 "ocean_detour":(
   "walk_to_bazaar","harbor_path","harbor_to_reef",
   "reef_to_ocean","ocean_to_goal",
 ),
 "underwater":(
   "walk_to_bazaar","harbor_path","harbor_to_reef",
   "reef_to_gate","gate_to_goal",
 ),
 "outer_space":(
   "spaceport_access","shuttle_to_orbit","orbit_to_moon","moon_to_citadel",
 ),
 "interstellar":(
   "spaceport_access","shuttle_to_orbit","generation_ship_voyage",
   "deep_space_crossing","stellar_return",
 ),
 "magic":(
   "forest_entry","forest_to_ruins","magic_circle_entry","magic_gateway",
 ),
 "windy":("cable_approach","cable_up","wind_shortcut"),
 "rain":("walk_to_bazaar","market_to_rain","rain_flood_route"),
 "tide":("walk_to_bazaar","harbor_path","tidal_shortcut"),
}

def _canonical(data)->str:
    return json.dumps(data,sort_keys=True,separators=(",",":"))+"\n"

def _id_map(world:World)->dict[str,int]:
    return {item.id:index for index,item in enumerate(world.places)}

def _masks(world:World,traveller:Traveller):
    tokens=set(traveller.tokens)
    for site in world.places:tokens.update(site.gifts)
    for path in world.connections:
        tokens.update(path.requires);tokens.update(path.requires_one)
        tokens.update(path.grants);tokens.update(path.consumes)
        if path.secret_token:tokens.add(path.secret_token)
        if path.hazard_resistance:tokens.add(path.hazard_resistance)
    tokens=sorted(tokens)
    if len(tokens)>60:
        raise ValueError("native original game inventory exceeds 60 bit slots")
    mapping={token:1<<index for index,token in enumerate(tokens)}
    return mapping,tokens

def _bit(values,mapping):
    value=0
    for token in values:
        value|=mapping[token]
    return value

def _u(value:int)->str:
    return f"UINT64_C({value})"

def emit_route_game(world:World,traveller:Traveller,*,authorized:bool)->dict[str,str]:
    if authorized is not True:
        raise PermissionError("original world C99 source export requires explicit approval")
    validate_world(world);validate_traveller(traveller)
    if len(world.places)>48 or len(world.connections)>192:
        raise ValueError("native route game cap exceeded")
    names=_id_map(world)
    tokens,token_list=_masks(world,traveller)
    edge_numbers={edge.id:index for index,edge in enumerate(world.connections)}
    weather_mask={name:1<<number for number,name in enumerate(
        sorted(set(ENVIRONMENT_FLAGS)))}
    active=_bit(world.environment,weather_mask)

    places=[]
    for p in world.places:
        places.append(
            f'  {{"{p.id}",{_u(_bit(p.gifts,tokens))},'
            f'{p.energy_refill},{p.money_pickup},{p.scenic_value}}},'
        )
    routes=[]
    for edge in world.connections:
        departures=[*edge.departures]+[-1]*(24-len(edge.departures))
        departures="{"+",".join(str(x) for x in departures)+"}"
        routes.append(
            f'  {{"{edge.id}","{edge.mode}",{names[edge.origin]},'
            f'{names[edge.destination]},{edge.minutes},{edge.price},'
            f'{edge.fatigue},{edge.danger},{edge.spectacle},'
        f'{edge.fuel},{edge.oxygen},{edge.mana},'
            f'{_u(_bit(edge.requires,tokens))},'
            f'{_u(_bit(edge.requires_one,tokens))},'
            f'{_u(_bit(edge.grants,tokens))},'
            f'{_u(_bit(edge.consumes,tokens))},'
            f'{_u(_bit((edge.secret_token,) if edge.secret_token else (),tokens))},'
            f'{_u(_bit((edge.hazard_resistance,) if edge.hazard_resistance else (),tokens))},'
            f'{_u(_bit(edge.weather_any,weather_mask))},'
            f'{_u(_bit(edge.weather_none,weather_mask))},'
            f'{len(edge.departures)},{departures}}},'
        )
    proofs=[]
    probes=[]
    for name,route in EXAMPLES.items():
        try:
            verified=replay(world,route,traveller,objective="native_witness")
        except ValueError:
            continue
        indices=tuple(edge_numbers[x] for x in route)
        probes.append({
            "name":name,
            "route":list(route),
            "indices":list(indices),
            "elapsed":verified.elapsed_minutes,
            "spent":verified.money_spent,
            "danger":verified.risk,
            "fuel":verified.fuel_used,
            "oxygen":verified.oxygen_used,
            "mana":verified.mana_used,
            "digest":verified.digest,
        })
        proofs.append((name,indices,verified))
    if len(proofs)<6:
        raise ValueError("original game route world lacks six truly playable witness routes")
    tests=[]
    for index,(name,indices,result) in enumerate(proofs):
        tests.append(
            f"static const int dragon_probe_route_{index}[]={{"+
            ",".join(str(x) for x in indices)+"};"
        )
    proof_data=[]
    for index,(name,indices,result) in enumerate(proofs):
        proof_data.append(
            f'  {{"{name}",{len(indices)},dragon_probe_route_{index},'
            f'{result.elapsed_minutes},{result.money_spent},{result.risk},'
            f'{result.fuel_used},{result.oxygen_used},{result.mana_used}}},'
        )
    header=(
        "#ifndef DRAGON_ORIGINAL_WORLD_ROUTE_H\n#define DRAGON_ORIGINAL_WORLD_ROUTE_H\n"
        "#include <stdint.h>\n"
        f"#define DRAGON_PLACE_COUNT {len(world.places)}\n"
        f"#define DRAGON_EDGE_COUNT {len(world.connections)}\n"
        f"#define DRAGON_PROBE_COUNT {len(proofs)}\n"
        f"#define DRAGON_MAX_HOPS {80}\n"
        f"#define DRAGON_MAX_MINUTES {world.max_minutes}\n"
        f"#define DRAGON_MAX_ENERGY {traveller.max_energy}\n"
        f"#define DRAGON_START {names[world.start]}\n"
        f"#define DRAGON_GOAL {names[world.goal]}\n"
        f"#define DRAGON_START_CASH {traveller.cash}\n"
        f"#define DRAGON_START_ENERGY {traveller.energy}\n"
        f"#define DRAGON_START_CLOCK {traveller.start_minute}\n"
        f"#define DRAGON_START_FUEL {traveller.fuel}\n"
        f"#define DRAGON_START_OXYGEN {traveller.oxygen}\n"
        f"#define DRAGON_START_MANA {traveller.mana}\n"
        f"#define DRAGON_START_TOKENS {_u(_bit(traveller.tokens,tokens))}\n"
        f"#define DRAGON_WEATHER {_u(active)}\n"
        "typedef struct { const char*id; uint64_t gifts;"
        " int refill,money,scenery; } DragonPlace;\n"
        "typedef struct { const char*id; const char*mode;"
        " int from,to,minutes,price,fatigue,danger,spectacle,fuel,oxygen,mana;"
        " uint64_t requires,requires_one,grants,consumes,secret,resistance,"
        "weather_any,weather_none;"
        " int departure_count; int departures[24]; } DragonConnection;\n"
        "typedef struct { const char*name; int steps; const int*edges;"
        " int minutes,spent,danger,fuel,oxygen,mana; } DragonProof;\n"
        "static const DragonPlace dragon_places[DRAGON_PLACE_COUNT]={\n"+
        "\n".join(places)+"\n};\n"
        "static const DragonConnection dragon_connections[DRAGON_EDGE_COUNT]={\n"+
        "\n".join(routes)+"\n};\n"+
        "\n".join(tests)+"\n"
        "static const DragonProof dragon_probes[DRAGON_PROBE_COUNT]={\n"+
        "\n".join(proof_data)+"\n};\n#endif\n"
    )
    from .dragon_route_world_assurance import demand_viable_world
    from .dragon_route_legal_provenance import (
        SourceRights,assess_route_originality,
        assert_original_game_candidate,review_json,
    )
    quality=demand_viable_world(world,traveller)
    rights=assess_route_originality(
        world,rights=SourceRights(
            owner_reference="Dragon generated original world route source",
            original_creation=True,
            individual_clearance=("authored_route_graph_source",),
            human_reviewer_approved=False,
        ),
    )
    assert_original_game_candidate(rights)
    analysis=structural_report(world)
    manifest={
        "schema":SCHEMA,
        "source":"strictly original generated game-world graph",
        "simulation_scope":"actual C99 game graph traversal, no mode-specific physics",
        "world":asdict(world),
        "world_digest":scenario_digest(world),
        "traveller":{
            "cash":traveller.cash,"energy":traveller.energy,
            "fuel":traveller.fuel,"oxygen":traveller.oxygen,
            "mana":traveller.mana,
            "max_energy":traveller.max_energy,
            "start_minute":traveller.start_minute,
            "tokens":sorted(traveller.tokens),
        },
        "token_registry":token_list,
        "abstract_graph_audit":analysis,
        "full_route_world_assurance":quality,
        "originality_screen":review_json(rights),
        "probes":probes,
        "original_work_attested":world.original_work_attested,
        "rights_claim":"originality attested; not independent copyright/patent/trademark clearance",
    }
    source={
        "src/main.c":C_GAME,
        "include/dragon_route_world.h":header,
        "dragon-original-route-proof.json":_canonical(manifest),
        "CMakeLists.txt":(
            "cmake_minimum_required(VERSION 3.16)\n"
            "project(DragonOriginalRouteWorld C)\n"
            "set(CMAKE_C_STANDARD 99)\n"
            "set(CMAKE_C_STANDARD_REQUIRED ON)\n"
            "add_executable(dragon_route_game src/main.c)\n"
            "target_include_directories(dragon_route_game PRIVATE include)\n"
            "if(MSVC)\n"
            "  target_compile_options(dragon_route_game PRIVATE /W4)\n"
            "else()\n"
            "  target_compile_options(dragon_route_game PRIVATE -Wall -Wextra -Wpedantic)\n"
            "endif()\n"
        ),
        "Makefile":(
            "CC ?= cc\n"
            "CFLAGS ?= -O2 -std=c99 -Wall -Wextra -pedantic\n"
            "all: dragon_route_game\n"
            "dragon_route_game: src/main.c include/dragon_route_world.h\n"
            "\t$(CC) $(CFLAGS) -Iinclude src/main.c -o dragon_route_game\n"
            "selftest: dragon_route_game\n"
            "\t./dragon_route_game --selftest\n"
        ),
        "README.md":(
            "# Original Dragon Free-Roam Route Game\n\n"
            "Build with make on a trusted original local C99 system. "
            "Run ./dragon_route_game; choose numbered actual route edges, "
            "obtain clue/key/vehicle rights, pay fares, navigate opening hours, "
            "watch weather and reach the goal. Restart to try alternatives. "
            "Run ./dragon_route_game --selftest to execute independent "
            "source-verified real journeys. Not a vehicle physics engine, "
            "not commercial game data, no arbitrary executable user scripts.\n"
        ),
    }
    return source
