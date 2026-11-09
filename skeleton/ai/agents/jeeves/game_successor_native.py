"""Original portable C99 SDL2 successor source and exact authored data emitter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _number(value: float) -> str:
    return format(float(value), ".17g")


def _header(spec: Mapping[str, Any]) -> str:
    from .game_successor_runtime import _digest, resolved_fidelity

    world, mechanics = spec["world"], spec["mechanics"]
    rows = [
        "/* Exact original authored recipe. No source game assets or code. */",
        "#ifndef SUCCESSOR_SPEC_H",
        "#define SUCCESSOR_SPEC_H",
        "#define GAME_TITLE " + _string(spec["title"]),
        "#define SPEC_DIGEST " + _string(_digest(spec)),
        "#define GAME_SEED " + str(spec["seed"]) + "ULL",
    ]
    constants = {
        "WORLD_W": world["width"],
        "WORLD_H": world["height"],
        "TILE": world["tile_size"],
        "SPAWN_X": world["spawn"][0],
        "SPAWN_Y": world["spawn"][1],
        "GOAL_X": world["goal"][0],
        "GOAL_Y": world["goal"][1],
        "CAMERA_SMOOTH": spec.get("camera", {}).get("smoothing", 0.15),
        "CAMERA_AHEAD": spec.get("camera", {}).get("lookahead", 40),
    }
    for group in ("movement", "combat", "adventure", "fishing", "farming", "resources"):
        for name, value in mechanics[group].items():
            if type(value) in (int, float):
                constants[group.upper() + "_" + name.upper()] = value
    for name, value in constants.items():
        rows.append("#define " + name + " " + _number(value))
    fidelity = resolved_fidelity(spec)
    for name, value in {
        "FIDELITY_LEVEL": fidelity["level"],
        "FIDELITY_PARTICLES": fidelity["particles"],
        "FIDELITY_LAYERS": fidelity["layers"],
        "FIDELITY_LIGHTING": fidelity["lighting"],
        "FIDELITY_TINT_R": fidelity["tint"][0],
        "FIDELITY_TINT_G": fidelity["tint"][1],
        "FIDELITY_TINT_B": fidelity["tint"][2],
    }.items():
        rows.append("#define " + name + " " + _number(value))
    rules = mechanics["progression"].get("unlock_rules", {})
    for name, value in {
        "UNLOCK_ENABLED": int(bool(rules)),
        "UNLOCK_SOLD_HARVEST": rules.get("tackle_requires_sold_harvest", 0),
        "UNLOCK_KEY_ROD": rules.get("key_requires_rod_level", 1),
        "UNLOCK_KEY_RARE": rules.get("key_requires_rare_fish", 0),
        "UNLOCK_RARE_DIFFICULTY": rules.get("rare_fish_difficulty", 2),
    }.items():
        rows.append("#define " + name + " " + _number(value))
    rows.append(
        "static const unsigned int palette[6]={"
        + ",".join(
            "0x" + spec["palette"][key][1:]
            for key in ("background", "terrain", "player", "enemy", "accent", "collectible")
        )
        + "};"
    )
    terrain = world.get("terrain") or [
        "0" * int(world["width"] / world["tile_size"])
        for _ in range(int(world["height"] / world["tile_size"]))
    ]
    rows.extend(
        [
            "#define TERRAIN_ROWS " + str(len(terrain)),
            "#define TERRAIN_COLS " + str(len(terrain[0])),
            "static const char *terrain[TERRAIN_ROWS]={" + ",\n".join(_string(row) for row in terrain) + "};",
        ]
    )

    def rectangles(name, values):
        rows.append("#define " + name.upper() + "_COUNT " + str(len(values)))
        values = values or [{"x": 0, "y": 0, "w": 0, "h": 0}]
        rows.append(
            "static const Rect "
            + name
            + "[]={"
            + ",".join(
                "{" + ",".join(_number(row.get(key, 0)) for key in ("x", "y", "w", "h")) + "}"
                for row in values
            )
            + "};"
        )

    rectangles("obstacles", [*world.get("obstacles_rects", []), *world.get("platforms", [])])
    rectangles("ponds", world.get("ponds", []))
    rectangles("farms", world.get("farm_plots", []))
    rectangles("dungeons", world.get("dungeons", []))
    rows.append(
        "static const int dungeon_locked[]={"
        + (",".join(str(int(row.get("requires") == "key")) for row in world.get("dungeons", [])) or "0")
        + "};"
    )
    rectangles("checkpoints", world.get("checkpoints", []))
    landmarks = world.get("landmarks", [])
    rows.append("#define LANDMARK_COUNT " + str(len(landmarks)))
    rows.append(
        "static const LandmarkSpec landmarks[]={"
        + (
            ",".join(
                "{"
                + ",".join(_number(row[key]) for key in ("x", "y", "w", "h"))
                + ","
                + str(row["sprite_index"])
                + ","
                + _string(row.get("name", ""))
                + "}"
                for row in landmarks
            )
            or '{0,0,0,0,0,""}'
        )
        + "};"
    )
    doors = world.get("doors", [])
    rows.append("#define DOOR_COUNT " + str(len(doors)))
    rows.append(
        "static const DoorSpec doors[]={"
        + (
            ",".join(
                "{"
                + ",".join(_number(row[key]) for key in ("x", "y", "w", "h", "target_x", "target_y"))
                + ","
                + str(int(bool(row.get("requires"))))
                + "}"
                for row in doors
            )
            or "{0,0,0,0,0,0,0}"
        )
        + "};"
    )
    fishes = world.get("fish_variants", mechanics["fishing"].get("fish_variants"))
    crops = world.get("crop_variants", mechanics["farming"].get("crop_variants"))
    rows.append("#define FISH_COUNT " + str(len(fishes)))
    rows.append(
        "static const FishSpec fishes[]={"
        + ",".join(
            "{" + _string(row["name"]) + "," + str(row["value"]) + "," + _number(row["difficulty"]) + "}"
            for row in fishes
        )
        + "};"
    )
    rows.append("#define CROP_COUNT " + str(len(crops)))
    seasons = {"spring": 0, "summer": 1, "autumn": 2, "winter": 3, "any": 4}
    rows.append(
        "static const CropSpec crops[]={"
        + ",".join(
            "{"
            + _string(row["name"])
            + ","
            + ",".join(_number(row[key]) for key in ("growth_days", "value", "seed_cost"))
            + ","
            + str(seasons[row["season"]])
            + "}"
            for row in crops
        )
        + "};"
    )
    npcs = world.get("villagers", [])
    rows.append("#define NPC_COUNT " + str(len(npcs)))
    rows.append(
        "static const NpcSpec npcs[]={"
        + (
            ",".join(
                "{"
                + _number(row["x"])
                + ","
                + _number(row["y"])
                + ","
                + str({"quest": 0, "shop": 1, "crafter": 2}[row.get("role", "quest")])
                + ","
                + _string(row["id"])
                + ","
                + _string(row.get("dialogue", ""))
                + "}"
                for row in npcs
            )
            or '{0,0,0,"",""}'
        )
        + "};"
    )
    enemies = [*world.get("enemies", []), *([world["boss"]] if world.get("boss") else [])]
    rows.append("#define ENEMY_COUNT " + str(len(enemies)))
    rows.append(
        "static const EnemySpec enemy_specs[]={"
        + (
            ",".join(
                "{"
                + ",".join(
                    _number(row.get(key, default))
                    for key, default in (
                        ("x", 0),
                        ("y", 0),
                        ("hp", 16 if row is world.get("boss") else 3),
                        ("speed", 32 if row is world.get("boss") else 40),
                        ("attack_interval", 1.5),
                    )
                )
                + ","
                + str(int(row is world.get("boss")))
                + ","
                + str(int(row.get("kind") == "shooter" or row is world.get("boss")))
                + "}"
                for row in enemies
            )
            or "{0,0,0,0,1,0,0}"
        )
        + "};"
    )
    items = world.get("collectibles", [])
    rows.append("#define ITEM_COUNT " + str(len(items)))
    rows.append(
        "static const ItemSpec items[]={"
        + (
            ",".join(
                "{"
                + _number(row["x"])
                + ","
                + _number(row["y"])
                + ","
                + str({"key": 0, "relic": 1, "shard": 1, "health": 2, "energy": 3}.get(row.get("kind"), 4))
                + ","
                + str(row.get("value", 1))
                + "}"
                for row in items
            )
            or "{0,0,0,0}"
        )
        + "};"
    )
    quests = mechanics["progression"].get("quests", [])
    rows.append("#define QUEST_COUNT " + str(len(quests)))
    rows.append(
        "static const QuestSpec quests[]={"
        + (
            ",".join(
                "{"
                + _string(row["text"])
                + ","
                + str({"fish": 0, "harvest": 1, "defeat": 2, "relic": 3}[row["kind"]])
                + ","
                + str(row["count"])
                + ","
                + str(row["reward"])
                + "}"
                for row in quests
            )
            or '{"",0,0,0}'
        )
        + "};"
    )
    rows.append("#define QUEST_TEXT " + _string(mechanics["progression"]["quest_text"]))
    rows.append("#endif")
    return "\n".join(rows) + "\n"


_C = r"""/* Original authored game engine. SDL2 renders actual gameplay state. */
#include <SDL.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#define DT (1.0/60.0)
#define VW 640
#define VH 360
#define BW 18
#define BH 20
typedef struct{double x,y,w,h;}Rect;
typedef struct{const char*name;int value;double difficulty;}FishSpec;
typedef struct{const char*name;double days,value,cost;int season;}CropSpec;
typedef struct{double x,y;int role;const char*name;const char*dialogue;}NpcSpec;
typedef struct{double x,y,hp,speed,interval;int boss,shooter;}EnemySpec;
typedef struct{double x,y;int kind,value;}ItemSpec;
typedef struct{const char*text;int kind,count,reward;}QuestSpec;
typedef struct{double x,y,w,h,target_x,target_y;int requires;}DoorSpec;
typedef struct{double x,y,w,h;int sprite;const char*name;}LandmarkSpec;
#include "game_spec.h"
typedef struct{double x,y,hp,maxhp,w,h,home_x,home_y,speed,cooldown,interval;int boss,shooter;}Enemy;
typedef struct{double x,y,vx,vy,life;int friendly;}Bullet;
typedef struct{double x,y,soil,water,growth;int crop;}Plot;
typedef struct{int phase,species,casts,pond;double timer,bite_at,progress,tension;}Fishing;
typedef struct{double x,y,vx,vy,fx,fy,energy,clock,camera_x,camera_y,attack_cd,shot_cd,invulnerable,dialogue_time;int health,coins,xp,kills,fish_caught,harvested,sold_harvest,rare_fish,granted_key,relics,keys,day,season,weather,tool,crop,rod_level,watering_level,mode,scene,checkpoint,previous_input,steps,plot_count,bullet_count;int seeds[8],fish_inventory[8],crop_inventory[8],collected[64],quest_done[16];unsigned char visited[4096];Plot plots[64];Enemy enemies[33];Bullet bullets[128];Fishing fish;char dialogue[300];}State;
static State S;static SDL_Window*window;static SDL_Renderer*renderer;static SDL_GameController*controller;static SDL_AudioDeviceID audio_device;static int paused=1,sound_enabled=1,map_visible=0,menu_page=0,rebind_index=-1;
static SDL_Keycode bindings[14]={SDLK_LEFT,SDLK_RIGHT,SDLK_UP,SDLK_DOWN,SDLK_j,SDLK_k,SDLK_e,SDLK_1,SDLK_2,SDLK_3,SDLK_4,SDLK_5,SDLK_TAB,SDLK_r};
static const int bits[14]={1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192};
static const char*actions[14]={"left","right","up","down","attack","fire","interact","fish","hoe","water","plant","harvest","tool_next","rest"};
typedef struct{double phase,freq,remaining,music_phase;int sample_rate;}Audio;static Audio A={0,0,0,0,48000};
static double clamp(double x,double a,double b){return fmax(a,fmin(b,x));}
static double noise(unsigned long long seed,int n){return (double)(((seed%2147483647ULL+(unsigned long long)n*48271ULL+12345ULL)*16807ULL)%2147483647ULL)/2147483647.0;}
static int overlap(double x,double y,double w,double h,Rect r){return x<r.x+r.w&&x+w>r.x&&y<r.y+r.h&&y+h>r.y;}
static void say(const char*text){snprintf(S.dialogue,sizeof(S.dialogue),"%s",text);S.dialogue_time=5;}
static void audio_callback(void*userdata,Uint8*stream,int length){Audio*a=(Audio*)userdata;int16_t*out=(int16_t*)stream;int frames=length/4;for(int i=0;i<frames;i++){double value=0;if(a->remaining>0){value=sin(a->phase)*.08*fmin(1,a->remaining*10);a->phase+=6.283185307*a->freq/a->sample_rate;a->remaining-=1.0/a->sample_rate;}a->music_phase+=1.0/a->sample_rate;double note=110.0*pow(2.0,(int)(a->music_phase/1.5)%5/12.0);value+=sin(a->music_phase*note*6.283185307)*.014;int16_t sample=(int16_t)(clamp(value,-1,1)*32767);out[i*2]=out[i*2+1]=sample;}}
static void tone(double frequency){if(!audio_device||!sound_enabled)return;SDL_LockAudioDevice(audio_device);A.freq=frequency;A.remaining=.16;A.phase=0;SDL_UnlockAudioDevice(audio_device);}
static int blocked(double x,double y){if(x<0||y<0||x+BW>WORLD_W||y+BH>WORLD_H)return 1;for(int i=0;i<OBSTACLES_COUNT;i++)if(overlap(x,y,BW,BH,obstacles[i]))return 1;for(int i=0;i<PONDS_COUNT;i++)if(overlap(x,y,BW,BH,ponds[i]))return 1;if(!S.keys)for(int i=0;i<DUNGEONS_COUNT;i++)if(dungeon_locked[i]&&overlap(x,y,BW,BH,dungeons[i]))return 1;double pts[4][2]={{x,y},{x+BW-.01,y},{x,y+BH-.01},{x+BW-.01,y+BH-.01}};for(int i=0;i<4;i++){int tx=(int)(pts[i][0]/TILE),ty=(int)(pts[i][1]/TILE);if(tx<0||ty<0||tx>=TERRAIN_COLS||ty>=TERRAIN_ROWS)return 1;if(terrain[ty][tx]=='1'||terrain[ty][tx]=='2')return 1;}return 0;}
static double distance_rect(Rect r){double x=S.x+9,y=S.y+10;return hypot(x-clamp(x,r.x,r.x+r.w),y-clamp(y,r.y,r.y+r.h));}
static void reset_game(void){memset(&S,0,sizeof(S));S.x=SPAWN_X;S.y=SPAWN_Y;S.fy=1;S.health=(int)RESOURCES_MAX_HEALTH;S.energy=RESOURCES_MAX_ENERGY;S.coins=20;S.day=1;S.rod_level=S.watering_level=1;S.checkpoint=-1;S.fish.pond=-1;S.camera_x=clamp(S.x-VW/2,0,WORLD_W-VW);S.camera_y=clamp(S.y-VH/2,0,WORLD_H-VH);for(int i=0;i<CROP_COUNT;i++)S.seeds[i]=5;for(int i=0;i<ENEMY_COUNT;i++){EnemySpec r=enemy_specs[i];S.enemies[i]=(Enemy){r.x,r.y,r.hp,r.hp,r.boss?36:22,r.boss?36:22,r.x,r.y,r.speed,r.interval,r.interval,r.boss,r.shooter};}say("Welcome. Fish the ponds, grow your garden, and find the lost beacons.");}
static void shot(double x,double y,double vx,double vy,int friendly){if(S.bullet_count<128)S.bullets[S.bullet_count++]=(Bullet){x,y,vx,vy,2,friendly};}
static void hit(Enemy*e,double amount){e->hp=fmax(0,e->hp-amount);tone(130);if(e->hp==0){S.kills++;S.xp+=3;S.coins+=e->boss?25:5;tone(540);}}
static void damage(void){if(S.invulnerable<=0){S.health=(int)fmax(0,S.health-COMBAT_ENEMY_DAMAGE);S.invulnerable=COMBAT_INVULNERABILITY_SECONDS;tone(90);}}
static void fish_step(int mask,int pressed){Fishing*f=&S.fish;if(f->phase==0&&(pressed&128)){int found=-1;double dist=1e20;for(int i=0;i<PONDS_COUNT;i++){double d=distance_rect(ponds[i]);if(d<dist){dist=d;found=i;}}if(found>=0&&dist<=FISHING_CAST_RANGE){f->phase=1;f->timer=f->progress=f->tension=0;f->pond=found;f->casts++;f->bite_at=FISHING_BITE_MIN_SECONDS+noise(GAME_SEED,f->casts)*(FISHING_BITE_MAX_SECONDS-FISHING_BITE_MIN_SECONDS);f->species=(int)fmin(FISH_COUNT-1,floor(noise(GAME_SEED,f->casts+97)*FISH_COUNT));if(S.rod_level<UNLOCK_KEY_ROD){int available[8],count=0;for(int n=0;n<FISH_COUNT;n++)if(fishes[n].difficulty<UNLOCK_RARE_DIFFICULTY)available[count++]=n;if(count)f->species=available[f->species%count];}say("Cast. Wait for a bite, then hold reel while tension is low.");tone(420);}else say("Move closer to a pond to cast your line.");}if(f->phase==0)return;f->timer+=DT;if(f->phase==1&&f->timer>=f->bite_at){f->phase=2;f->timer=0;say("A bite! Hold fish to reel; release when tension rises.");tone(900);}if(f->phase==2){double safe=.45+.2*sin(f->timer*4);if(mask&128){f->progress=fmin(1,f->progress+FISHING_REEL_SPEED*DT*FISHING_ROD_STRENGTH*S.rod_level);f->tension=clamp(f->tension+FISHING_TENSION_GAIN*fishes[f->species].difficulty*DT*(safe<.4?1.4:.65),0,1);}else{f->tension=fmax(0,f->tension-FISHING_TENSION_RELEASE*DT);f->progress=fmax(0,f->progress-DT*.03);}if(f->progress>=1&&f->tension<1){S.fish_inventory[f->species]++;S.fish_caught++;if(fishes[f->species].difficulty>=UNLOCK_RARE_DIFFICULTY)S.rare_fish++;S.xp+=2;f->phase=0;char text[250];snprintf(text,sizeof(text),"Caught %s! Sell fish in town or keep them.",fishes[f->species].name);say(text);tone(1100);}else if(f->tension>=1||f->timer>=FISHING_CATCH_WINDOW_SECONDS){f->phase=0;say("The fish escaped. Relax the line and try again.");tone(180);}}}
static void farm_action(int action){double x=floor((S.x+9+S.fx*28)/TILE)*TILE,y=floor((S.y+10+S.fy*28)/TILE)*TILE;int zone=0;for(int i=0;i<FARMS_COUNT;i++)if(x>=farms[i].x&&x<farms[i].x+farms[i].w&&y>=farms[i].y&&y<farms[i].y+farms[i].h)zone=1;if(!zone){say("Use farming tools in a marked garden plot.");return;}Plot*p=NULL;for(int i=0;i<S.plot_count;i++)if(S.plots[i].x==x&&S.plots[i].y==y)p=&S.plots[i];if(action==256){if(!p&&S.plot_count<64){p=&S.plots[S.plot_count++];*p=(Plot){x,y,FARMING_SOIL_QUALITY,0,0,-1};tone(240);}say("Soil prepared. Plant a seed, then water it.");}else if(!p)say("Prepare this soil with the hoe first.");else if(action==512){p->water=fmin(1,p->water+.6*S.watering_level);tone(350);}else if(action==1024&&p->crop<0){if(S.seeds[S.crop]>0){S.seeds[S.crop]--;p->crop=S.crop;p->growth=0;say("Seed planted. Water helps it grow through the seasons.");tone(520);}else say("You need more seeds. Visit the town shop.");}else if(action==2048&&p->crop>=0){if(p->growth>=1){S.crop_inventory[p->crop]++;S.harvested++;S.xp+=2;p->crop=-1;p->growth=0;say("Harvested. Visit town to sell your crops.");tone(760);}else say("This crop is still growing. Keep the soil watered.");}}
static void advance_time(double delta){S.clock+=delta;if(S.clock>=FARMING_DAY_SECONDS){S.clock-=FARMING_DAY_SECONDS;S.day++;S.season=((int)floor((S.day-1)/FARMING_SEASON_DAYS))%4;S.weather=noise(GAME_SEED,S.day)<FARMING_WEATHER_WET_PROBABILITY;tone(640);}for(int i=0;i<S.plot_count;i++){Plot*p=&S.plots[i];p->water=clamp(p->water+(S.weather?delta*.2:-FARMING_WATER_DECAY*delta/FARMING_DAY_SECONDS),0,1);if(p->crop>=0){CropSpec v=crops[p->crop];if(p->water>.1&&(v.season==4||v.season==S.season))p->growth=fmin(1,p->growth+delta/(FARMING_DAY_SECONDS*v.days)*(.5+p->soil*.5));}}}
static void interact(void){int npc=-1;double distance=1e20;for(int i=0;i<NPC_COUNT;i++){double d=hypot(S.x+9-npcs[i].x,S.y+10-npcs[i].y);if(d<distance){npc=i;distance=d;}}if(npc>=0&&distance<=ADVENTURE_INTERACT_RADIUS){NpcSpec n=npcs[npc];if(n.role==1){for(int c=0;c<CROP_COUNT;c++)S.sold_harvest+=S.crop_inventory[c];int proceeds=0;for(int i=0;i<FISH_COUNT;i++){proceeds+=S.fish_inventory[i]*fishes[i].value;S.fish_inventory[i]=0;}for(int i=0;i<CROP_COUNT;i++){proceeds+=(int)(S.crop_inventory[i]*crops[i].value);S.crop_inventory[i]=0;}S.coins+=proceeds;if(S.coins>=crops[S.crop].cost){S.coins-=(int)crops[S.crop].cost;S.seeds[S.crop]++;}char text[240];snprintf(text,sizeof(text),"Sold goods for %d coins. A fresh seed is ready for your garden.",proceeds);say(text);tone(620);}else if(n.role==2){if(S.sold_harvest<UNLOCK_SOLD_HARVEST)say("Trade a homegrown crop in town before crafting improved tackle.");else if(S.coins>=15&&S.rod_level<3){S.coins-=15;S.rod_level++;S.watering_level=(int)fmin(3,S.watering_level+1);say("Crafted stronger tackle and an improved watering can.");tone(720);}else say("Bring 15 coins to improve your rod and watering can.");}else{if(UNLOCK_ENABLED&&!S.granted_key&&S.rod_level>=UNLOCK_KEY_ROD&&S.rare_fish>=UNLOCK_KEY_RARE){S.keys++;S.granted_key=1;say("Your rare catch earned a shrine key. The adventure trail is open.");tone(850);}else if(UNLOCK_ENABLED&&!S.granted_key)say("Improve your tackle with crop trade, then land a rare fish to earn a shrine key.");else say(n.dialogue);}return;}for(int i=0;i<DOOR_COUNT;i++){DoorSpec d=doors[i];if(overlap(S.x,S.y,BW,BH,(Rect){d.x,d.y,d.w,d.h})&&(!d.requires||S.keys>0)){S.x=d.target_x;S.y=d.target_y;S.vx=S.vy=0;tone(700);return;}}say(QUEST_TEXT);}
static void tick(int mask){if(S.mode)return;S.steps++;S.attack_cd=fmax(0,S.attack_cd-DT);S.shot_cd=fmax(0,S.shot_cd-DT);S.invulnerable=fmax(0,S.invulnerable-DT);S.dialogue_time=fmax(0,S.dialogue_time-DT);S.energy=fmin(RESOURCES_MAX_ENERGY,S.energy+DT*2);double dx=!!(mask&2)-!!(mask&1),dy=!!(mask&8)-!!(mask&4),length=hypot(dx,dy);if(length){dx/=length;dy/=length;S.fx=dx;S.fy=dy;}S.vx=dx?clamp(S.vx+dx*MOVEMENT_ACCELERATION*DT,-MOVEMENT_MAX_SPEED,MOVEMENT_MAX_SPEED):copysign(fmax(0,fabs(S.vx)-MOVEMENT_FRICTION*DT),S.vx);S.vy=dy?clamp(S.vy+dy*MOVEMENT_ACCELERATION*DT,-MOVEMENT_MAX_SPEED,MOVEMENT_MAX_SPEED):copysign(fmax(0,fabs(S.vy)-MOVEMENT_FRICTION*DT),S.vy);double speed=hypot(S.vx,S.vy);if(speed>MOVEMENT_MAX_SPEED){S.vx=S.vx/speed*MOVEMENT_MAX_SPEED;S.vy=S.vy/speed*MOVEMENT_MAX_SPEED;}if(S.fish.phase==0){if(!blocked(S.x+S.vx*DT,S.y))S.x+=S.vx*DT;else S.vx=0;if(!blocked(S.x,S.y+S.vy*DT))S.y+=S.vy*DT;else S.vy=0;}int pressed=mask&~S.previous_input;if(pressed&4096)S.tool=(S.tool+1)%5;if(mask&16&&S.attack_cd<=0){S.attack_cd=ADVENTURE_MELEE_COOLDOWN;double x=S.x+9+S.fx*28,y=S.y+10+S.fy*28;for(int i=0;i<ENEMY_COUNT;i++){Enemy*e=&S.enemies[i];if(e->hp>0&&hypot(e->x+e->w/2-x,e->y+e->h/2-y)<36)hit(e,ADVENTURE_MELEE_DAMAGE);}tone(160);}if(mask&32&&S.shot_cd<=0&&S.energy>=1){shot(S.x+9,S.y+10,S.fx*COMBAT_PROJECTILE_SPEED,S.fy*COMBAT_PROJECTILE_SPEED,1);S.energy--;S.shot_cd=COMBAT_COOLDOWN;tone(320);}fish_step(mask,pressed);for(int bit=256;bit<=2048;bit*=2)if(pressed&bit)farm_action(bit);if(pressed&64)interact();if(pressed&8192){int close=0;for(int i=0;i<CHECKPOINTS_COUNT;i++)if(distance_rect(checkpoints[i])<=96)close=1;if(close){advance_time(FARMING_DAY_SECONDS-S.clock+1e-8);S.energy=RESOURCES_MAX_ENERGY;S.health=(int)RESOURCES_MAX_HEALTH;say("Rested at a waystone. A new day begins in the valley.");}else say("Rest beside a village or a discovered waystone.");}advance_time(DT);
for(int i=0;i<ENEMY_COUNT;i++){Enemy*e=&S.enemies[i];if(e->hp<=0)continue;double dx=S.x-e->x,dy=S.y-e->y,d=hypot(dx,dy),phase=e->boss&&e->hp<=e->maxhp*.5?1.5:1,mx,my;if(d<(e->boss?380:240)&&d>20){mx=dx/d;my=dy/d;}else{mx=sin((S.steps%360)/60.0);my=cos((S.steps%360)/60.0);double h=hypot(e->x-e->home_x,e->y-e->home_y);if(h>80){mx=(e->home_x-e->x)/fmax(1,h);my=(e->home_y-e->y)/fmax(1,h);}}double x=e->x+mx*e->speed*phase*DT,y=e->y+my*e->speed*phase*DT;if(!blocked(x,e->y))e->x=x;if(!blocked(e->x,y))e->y=y;e->cooldown-=DT;if(e->shooter&&d<420&&e->cooldown<=0){double speed=COMBAT_PROJECTILE_SPEED*.6;shot(e->x+e->w/2,e->y+e->h/2,dx/fmax(1,d)*speed,dy/fmax(1,d)*speed,0);e->cooldown=e->interval/phase;}if(overlap(S.x,S.y,BW,BH,(Rect){e->x,e->y,e->w,e->h}))damage();}
int count=0;for(int i=0;i<S.bullet_count;i++){Bullet b=S.bullets[i];b.x+=b.vx*DT;b.y+=b.vy*DT;b.life-=DT;int h=b.life<=0||blocked(b.x,b.y);if(!h&&b.friendly){for(int n=0;n<ENEMY_COUNT;n++){Enemy*e=&S.enemies[n];if(e->hp>0&&overlap(b.x-3,b.y-3,6,6,(Rect){e->x,e->y,e->w,e->h})){hit(e,COMBAT_DAMAGE);h=1;break;}}}else if(!h&&overlap(b.x-3,b.y-3,6,6,(Rect){S.x,S.y,BW,BH})){damage();h=1;}if(!h)S.bullets[count++]=b;}S.bullet_count=count;
for(int i=0;i<ITEM_COUNT;i++)if(!S.collected[i]&&hypot(S.x-items[i].x,S.y-items[i].y)<28){S.collected[i]=1;ItemSpec v=items[i];if(v.kind<2){if(v.kind==0)S.keys+=v.value;else S.relics+=v.value;}else if(v.kind==2)S.health=(int)fmin(RESOURCES_MAX_HEALTH,S.health+v.value);else if(v.kind==3)S.energy=fmin(RESOURCES_MAX_ENERGY,S.energy+v.value);else S.coins+=v.value;tone(820);}for(int i=0;i<CHECKPOINTS_COUNT;i++)if(hypot(S.x-checkpoints[i].x,S.y-checkpoints[i].y)<40&&S.checkpoint!=i){S.checkpoint=i;S.health=(int)RESOURCES_MAX_HEALTH;tone(700);}for(int i=0;i<QUEST_COUNT;i++){QuestSpec q=quests[i];int value=q.kind==0?S.fish_caught:q.kind==1?S.harvested:q.kind==2?S.kills:S.relics;if(!S.quest_done[i]&&value>=q.count){S.quest_done[i]=1;S.coins+=q.reward;S.xp+=q.reward;char text[300];snprintf(text,sizeof(text),"Quest complete: %s",q.text);say(text);tone(980);}}int zone=(int)(S.y/128)*64+(int)(S.x/128);if(zone>=0&&zone<4096)S.visited[zone]=1;S.scene=0;for(int i=0;i<DUNGEONS_COUNT;i++)if(overlap(S.x,S.y,BW,BH,dungeons[i]))S.scene=i+1;if(S.health<=0){S.mode=1;tone(80);}int complete=!(UNLOCK_ENABLED&&!S.keys);for(int i=0;i<QUEST_COUNT;i++)if(!S.quest_done[i])complete=0;for(int i=0;i<ENEMY_COUNT;i++)if(S.enemies[i].boss&&S.enemies[i].hp>0)complete=0;if(!S.mode&&hypot(S.x-GOAL_X,S.y-GOAL_Y)<48&&complete){S.mode=2;say("The valley is restored. Your fishing, farming and adventure brought it back to life.");tone(1200);}S.camera_x+=(clamp(S.x+9-VW/2+S.fx*CAMERA_AHEAD,0,WORLD_W-VW)-S.camera_x)*CAMERA_SMOOTH;S.camera_y+=(clamp(S.y+10-VH/2+S.fy*CAMERA_AHEAD,0,WORLD_H-VH)-S.camera_y)*CAMERA_SMOOTH;S.previous_input=mask;}
static void colour(unsigned int c){SDL_SetRenderDrawColor(renderer,(c>>16)&255,(c>>8)&255,c&255,255);}
static void rect(double x,double y,double w,double h,unsigned int c){if(x+w<S.camera_x||y+h<S.camera_y||x>S.camera_x+VW||y>S.camera_y+VH)return;colour(c);SDL_Rect r={(int)round(x-S.camera_x),(int)round(y-S.camera_y),(int)ceil(w),(int)ceil(h)};SDL_RenderFillRect(renderer,&r);}
static const unsigned char glyphs[36][7]={{14,17,17,31,17,17,17},{30,17,17,30,17,17,30},{14,17,16,16,16,17,14},{30,17,17,17,17,17,30},{31,16,16,30,16,16,31},{31,16,16,30,16,16,16},{14,17,16,23,17,17,15},{17,17,17,31,17,17,17},{31,4,4,4,4,4,31},{7,2,2,2,18,18,12},{17,18,20,24,20,18,17},{16,16,16,16,16,16,31},{17,27,21,21,17,17,17},{17,25,21,19,17,17,17},{14,17,17,17,17,17,14},{30,17,17,30,16,16,16},{14,17,17,17,21,18,13},{30,17,17,30,20,18,17},{15,16,16,14,1,1,30},{31,4,4,4,4,4,4},{17,17,17,17,17,17,14},{17,17,17,17,17,10,4},{17,17,17,21,21,21,10},{17,17,10,4,10,17,17},{17,17,10,4,4,4,4},{31,1,2,4,8,16,31},{14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},{30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},{14,16,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},{14,17,17,15,1,1,14}};
static void text(int x,int y,const char*value,unsigned int c,int scale){colour(c);for(int n=0;value[n]&&n<128;n++){unsigned char ch=(unsigned char)value[n];if(ch>='a'&&ch<='z')ch-=32;int index=ch>='A'&&ch<='Z'?ch-'A':ch>='0'&&ch<='9'?26+ch-'0':-1;if(ch=='\n'){y+=9*scale;x=8;continue;}if(index>=0)for(int r=0;r<7;r++)for(int p=0;p<5;p++)if(glyphs[index][r]&(1<<(4-p))){SDL_Rect box={x+p*scale,y+r*scale,scale,scale};SDL_RenderFillRect(renderer,&box);}x+=6*scale;}}
static void box(int x,int y,int w,int h,unsigned int c){colour(c);SDL_Rect r={x,y,w,h};SDL_RenderFillRect(renderer,&r);}
static void render(void){static const unsigned int colours[8]={0x34694c,0x3274a3,0x647078,0xc9ae6e,0xac9570,0x527446,0x745236,0x41424f};colour(palette[0]);SDL_RenderClear(renderer);int left=(int)(S.camera_x/TILE),top=(int)(S.camera_y/TILE);for(int y=top;y<(int)fmin(TERRAIN_ROWS,top+ceil(VH/TILE)+2);y++)for(int x=left;x<(int)fmin(TERRAIN_COLS,left+ceil(VW/TILE)+2);x++){int kind=terrain[y][x]-'0';rect(x*TILE,y*TILE,TILE,TILE,colours[kind]);if(kind==0||kind==3||kind==5)rect(x*TILE+(x*7+y*3)%24,y*TILE+7,2,4,palette[1]);if(kind==1)rect(x*TILE+3,y*TILE+5+(S.steps/20)%7,16,2,palette[4]);}for(int i=0;i<PONDS_COUNT;i++){Rect p=ponds[i];rect(p.x,p.y,p.w,p.h,colours[1]);for(int n=0;n<4;n++)rect(p.x+8+n*22,p.y+8+(S.steps/20+n*7)%(int)fmax(1,p.h-12),15,2,palette[4]);}for(int i=0;i<FARMS_COUNT;i++){Rect f=farms[i];rect(f.x,f.y,f.w,f.h,colours[6]);}for(int i=0;i<OBSTACLES_COUNT;i++){Rect o=obstacles[i];rect(o.x,o.y,o.w,o.h,palette[1]);rect(o.x+3,o.y+3,o.w-6,4,palette[4]);}for(int i=0;i<S.plot_count;i++){Plot p=S.plots[i];rect(p.x+2,p.y+2,TILE-4,TILE-4,p.water>.5?0x4a6571:0x8e6446);if(p.crop>=0){double g=5+p.growth*18;rect(p.x+TILE/2-2,p.y+TILE-g-3,4,g,p.growth>=1?palette[5]:palette[2]);rect(p.x+TILE/2-7,p.y+TILE-g,14,4,palette[4]);}}for(int i=0;i<NPC_COUNT;i++){NpcSpec n=npcs[i];rect(n.x+3,n.y-9,12,10,palette[5]);rect(n.x,n.y,18,20,palette[4]);text((int)(n.x-S.camera_x-6),(int)(n.y-S.camera_y-18),n.name,0xffffff,1);}for(int i=0;i<ITEM_COUNT;i++)if(!S.collected[i])rect(items[i].x,items[i].y,10,14,palette[5]);for(int i=0;i<ENEMY_COUNT;i++){Enemy e=S.enemies[i];if(e.hp<=0)continue;rect(e.x,e.y,e.w,e.h,palette[3]);rect(e.x+4,e.y+4,e.w-8,3,palette[0]);rect(e.x,e.y-6,e.w*e.hp/e.maxhp,3,palette[5]);}for(int i=0;i<S.bullet_count;i++){Bullet b=S.bullets[i];rect(b.x-3,b.y-3,6,6,b.friendly?palette[4]:palette[3]);}if(S.invulnerable<=0||S.steps%8<4){rect(S.x+3,S.y-8,12,10,palette[5]);rect(S.x,S.y,18,20,palette[2]);rect(S.x+3,S.y+16,4,4,palette[4]);rect(S.x+11,S.y+16,4,4,palette[4]);}if(S.attack_cd>ADVENTURE_MELEE_COOLDOWN-.1)rect(S.x+9+S.fx*28-4,S.y+10+S.fy*28-4,8,8,palette[5]);double night=.22*(1-cos(S.clock/FARMING_DAY_SECONDS*6.283185307))/2;SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND);SDL_SetRenderDrawColor(renderer,7,12,45,(Uint8)(night*255));SDL_Rect sky={0,0,VW,VH};SDL_RenderFillRect(renderer,&sky);SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_NONE);if(S.weather)for(int i=0;i<80;i++)box((i*73+S.steps*2)%VW,(i*29+S.steps*3)%VH,1,5,0xa4d6e9);
box(0,0,VW,28,0x13253d);box(8,7,90,6,palette[3]);box(8,7,(int)(90*S.health/RESOURCES_MAX_HEALTH),6,palette[2]);box(8,17,(int)(90*S.energy/RESOURCES_MAX_ENERGY),4,palette[4]);char line[160];static const char*seasons[]={"SPRING","SUMMER","AUTUMN","WINTER"};snprintf(line,sizeof(line),"%d COINS  DAY %d %s %s",S.coins,S.day,seasons[S.season],S.weather?"RAIN":"CLEAR");text(116,9,line,0xeef5e8,1);snprintf(line,sizeof(line),"FISH %d  CROPS %d  STONES %d",S.fish_caught,S.harvested,S.relics);text(430,9,line,0xffe19b,1);if(S.dialogue_time>0){box(0,VH-23,VW,23,0x13253d);text(8,VH-16,S.dialogue,0xffe19b,1);}static const char*tools[]={"FISH","HOE","WATER","PLANT","HARVEST"};for(int i=0;i<5;i++){box(10+i*70,VH-50,64,20,i==S.tool?0x736446:0x203940);text(15+i*70,VH-43,tools[i],0xffffff,1);}text(380,VH-43,crops[S.crop].name,palette[5],1);if(S.fish.phase){box(170,274,300,60,0x172d3e);box(178,294,(int)(284*S.fish.progress),10,palette[5]);box(178,314,(int)(284*S.fish.tension),8,palette[3]);text(178,282,S.fish.phase==1?"WAIT FOR THE BITE":"REEL AND RELEASE TO BALANCE TENSION",0xffffff,1);}if(map_visible){box(400,34,232,160,0x13253d);for(int y=0;y<TERRAIN_ROWS;y+=3)for(int x=0;x<TERRAIN_COLS;x+=3)box(405+x*220/TERRAIN_COLS,39+y*145/TERRAIN_ROWS,4,4,colours[terrain[y][x]-'0']);box(405+(int)(S.x/WORLD_W*220),39+(int)(S.y/WORLD_H*145),4,4,palette[2]);}
if(paused){box(80,56,480,245,0x20313e);text(100,73,GAME_TITLE,palette[5],2);text(100,104,S.mode==1?"JOURNEY PAUSED AT YOUR WAYSTONE":S.mode==2?"THE VALLEY IS RESTORED":"EXPLORE FISH FARM AND RESTORE THE VALLEY",0xeef5e8,1);text(100,126,"ENTER PLAY  S SAVE  L LOAD  N NEW GAME",0xeef5e8,1);text(100,145,"I INVENTORY  C CONTROLS  ESC RETURN",0xeef5e8,1);if(menu_page==1){int y=165;for(int i=0;i<QUEST_COUNT;i++){snprintf(line,sizeof(line),"%s %s",S.quest_done[i]?"DONE":"TODO",quests[i].text);text(100,y,line,palette[5],1);y+=17;}snprintf(line,sizeof(line),"SEEDS %d  TACKLE %d  WATERING CAN %d",S.seeds[S.crop],S.rod_level,S.watering_level);text(100,255,line,0xeef5e8,1);}else if(menu_page==2){text(100,168,"PRESS A DIGIT 1 TO 9 THEN A NEW KEY",palette[5],1);text(100,188,"1 LEFT 2 RIGHT 3 UP 4 DOWN 5 ATTACK",0xffffff,1);text(100,208,"6 BOW 7 TALK 8 FISH 9 HOE",0xffffff,1);text(100,230,"SPACE TOOL TAB NEXT R REST M MAP",0xffffff,1);if(rebind_index>=0)text(100,253,"PRESS THE NEW CONTROL KEY",palette[5],1);}else{text(100,168,"ARROWS WASD MOVE J SWORD K BOW E TALK",0xffffff,1);text(100,188,"SPACE CURRENT TOOL TAB NEXT R REST",0xffffff,1);text(100,208,"1 FISH 2 HOE 3 WATER 4 PLANT 5 HARVEST",0xffffff,1);text(100,230,"GAMEPAD STICK A TALK B SWORD X TOOL",0xffffff,1);}}SDL_RenderPresent(renderer);}
typedef struct{char magic[16],digest[65];uint32_t size,checksum;}SaveHeader;
static uint32_t checksum(const void*data,size_t size){const unsigned char*p=data;uint32_t h=2166136261u;for(size_t i=0;i<size;i++)h=(h^p[i])*16777619u;return h;}
static void save_game(const char*path){char temporary[1024];if(strlen(path)>900){say("Save path is too long.");return;}snprintf(temporary,sizeof(temporary),"%s.tmp",path);FILE*f=fopen(temporary,"wb");if(!f){say("Save storage is unavailable.");return;}SaveHeader h={0};snprintf(h.magic,sizeof(h.magic),"ORIGINALSAVEV1");snprintf(h.digest,sizeof(h.digest),"%s",SPEC_DIGEST);h.size=sizeof(S);h.checksum=checksum(&S,sizeof(S));int ok=fwrite(&h,sizeof(h),1,f)==1&&fwrite(&S,sizeof(S),1,f)==1;ok=fclose(f)==0&&ok;if(ok&&rename(temporary,path)==0)say("Saved your exact original recipe on this device.");else{remove(temporary);say("The save could not be completed.");}}
static int valid_state(const State*s){
 if(!isfinite(s->x)||!isfinite(s->y)||s->x<0||s->x>WORLD_W-BW||s->y<0||s->y>WORLD_H-BH||s->plot_count<0||s->plot_count>64||s->bullet_count<0||s->bullet_count>128||s->crop<0||s->crop>=CROP_COUNT||s->tool<0||s->tool>4||s->fish.species<0||s->fish.species>=FISH_COUNT||s->fish.phase<0||s->fish.phase>2||s->season<0||s->season>3||s->day<1||s->day>1000000||s->health<0||s->health>RESOURCES_MAX_HEALTH||s->mode<0||s->mode>2||s->checkpoint< -1||s->checkpoint>=CHECKPOINTS_COUNT||s->rod_level<1||s->rod_level>3||s->watering_level<1||s->watering_level>3||s->scene<0||s->scene>DUNGEONS_COUNT||!memchr(s->dialogue,0,sizeof(s->dialogue)))return 0;
 const double finite_values[]={s->vx,s->vy,s->fx,s->fy,s->energy,s->clock,s->camera_x,s->camera_y,s->attack_cd,s->shot_cd,s->invulnerable,s->dialogue_time,s->fish.timer,s->fish.bite_at,s->fish.progress,s->fish.tension};for(size_t i=0;i<sizeof(finite_values)/sizeof(finite_values[0]);i++)if(!isfinite(finite_values[i]))return 0;
 if(s->energy<0||s->energy>RESOURCES_MAX_ENERGY||s->clock<0||s->clock>=FARMING_DAY_SECONDS||s->camera_x<0||s->camera_x>WORLD_W-VW||s->camera_y<0||s->camera_y>WORLD_H-VH||s->fish.progress<0||s->fish.progress>1||s->fish.tension<0||s->fish.tension>1||s->fish.pond< -1||s->fish.pond>=PONDS_COUNT||(s->fish.phase&&s->fish.pond<0)||s->coins<0||s->xp<0||s->fish_caught<0||s->harvested<0||s->rare_fish<0||s->sold_harvest<0)return 0;
 for(int i=0;i<s->plot_count;i++){Plot p=s->plots[i];if(p.crop< -1||p.crop>=CROP_COUNT||!isfinite(p.x)||!isfinite(p.y)||!isfinite(p.soil)||!isfinite(p.water)||!isfinite(p.growth)||p.x<0||p.y<0||p.x>=WORLD_W||p.y>=WORLD_H||p.growth<0||p.growth>1||p.water<0||p.water>1)return 0;}
 for(int i=0;i<ENEMY_COUNT;i++){Enemy e=s->enemies[i];if(!isfinite(e.x)||!isfinite(e.y)||!isfinite(e.hp)||!isfinite(e.cooldown)||e.x<0||e.y<0||e.x>WORLD_W||e.y>WORLD_H||e.hp<0||e.hp>enemy_specs[i].hp||e.maxhp!=enemy_specs[i].hp||e.boss!=enemy_specs[i].boss||e.speed!=enemy_specs[i].speed||e.interval!=enemy_specs[i].interval||e.home_x!=enemy_specs[i].x||e.home_y!=enemy_specs[i].y||e.w!=(e.boss?36:22)||e.h!=(e.boss?36:22))return 0;}
 for(int i=0;i<s->bullet_count;i++){Bullet b=s->bullets[i];if(!isfinite(b.x)||!isfinite(b.y)||!isfinite(b.vx)||!isfinite(b.vy)||!isfinite(b.life)||fabs(b.vx)>COMBAT_PROJECTILE_SPEED||fabs(b.vy)>COMBAT_PROJECTILE_SPEED||b.life<0||b.life>2||(b.friendly!=0&&b.friendly!=1))return 0;}for(int i=0;i<CROP_COUNT;i++)if(s->seeds[i]<0||s->seeds[i]>1000000||s->crop_inventory[i]<0||s->crop_inventory[i]>1000000)return 0;for(int i=0;i<FISH_COUNT;i++)if(s->fish_inventory[i]<0||s->fish_inventory[i]>1000000)return 0;
 return 1;
}
static void load_game(const char*path){FILE*f=fopen(path,"rb");if(!f){say("No local save is available.");return;}SaveHeader h;State replacement;int ok=fread(&h,sizeof(h),1,f)==1&&fread(&replacement,sizeof(replacement),1,f)==1&&fgetc(f)==EOF;fclose(f);if(!ok||memcmp(h.magic,"ORIGINALSAVEV1",14)||memcmp(h.digest,SPEC_DIGEST,65)||h.size!=sizeof(S)||h.checksum!=checksum(&replacement,sizeof(replacement))||!valid_state(&replacement)){say("Save belongs to a different recipe or is corrupt.");return;}S=replacement;S.previous_input=0;say("Loaded your exact original recipe save.");}
static int input_mask(void){const Uint8*keys=SDL_GetKeyboardState(NULL);int mask=0;for(int i=0;i<14;i++)if(keys[SDL_GetScancodeFromKey(bindings[i])])mask|=bits[i];if(keys[SDL_SCANCODE_A])mask|=1;if(keys[SDL_SCANCODE_D])mask|=2;if(keys[SDL_SCANCODE_W])mask|=4;if(keys[SDL_SCANCODE_S])mask|=8;if(keys[SDL_SCANCODE_SPACE])mask|=128<<S.tool;if(controller){Sint16 x=SDL_GameControllerGetAxis(controller,SDL_CONTROLLER_AXIS_LEFTX),y=SDL_GameControllerGetAxis(controller,SDL_CONTROLLER_AXIS_LEFTY);if(x<-10000||SDL_GameControllerGetButton(controller,SDL_CONTROLLER_BUTTON_DPAD_LEFT))mask|=1;if(x>10000||SDL_GameControllerGetButton(controller,SDL_CONTROLLER_BUTTON_DPAD_RIGHT))mask|=2;if(y<-10000||SDL_GameControllerGetButton(controller,SDL_CONTROLLER_BUTTON_DPAD_UP))mask|=4;if(y>10000||SDL_GameControllerGetButton(controller,SDL_CONTROLLER_BUTTON_DPAD_DOWN))mask|=8;if(SDL_GameControllerGetButton(controller,SDL_CONTROLLER_BUTTON_A))mask|=64;if(SDL_GameControllerGetButton(controller,SDL_CONTROLLER_BUTTON_B))mask|=16;if(SDL_GameControllerGetButton(controller,SDL_CONTROLLER_BUTTON_X))mask|=128<<S.tool;if(SDL_GameControllerGetButton(controller,SDL_CONTROLLER_BUTTON_Y))mask|=4096;}return mask;}
static int action_mask(const char*name){for(int i=0;i<14;i++)if(!strcmp(name,actions[i]))return bits[i];if(!strcmp(name,"noop"))return 0;if(!strcmp(name,"up_left"))return 5;if(!strcmp(name,"up_right"))return 6;if(!strcmp(name,"down_left"))return 9;if(!strcmp(name,"down_right"))return 10;return -1;}
static int capture(const char*path){int width=0,height=0;if(SDL_GetRendererOutputSize(renderer,&width,&height)||width<1||height<1||width>4096||height>4096||(long long)width*height>4194304)return 0;SDL_Surface*surface=SDL_CreateRGBSurfaceWithFormat(0,width,height,32,SDL_PIXELFORMAT_ARGB8888);if(!surface)return 0;int ok=SDL_RenderReadPixels(renderer,NULL,SDL_PIXELFORMAT_ARGB8888,surface->pixels,surface->pitch)==0&&SDL_SaveBMP(surface,path)==0;SDL_FreeSurface(surface);return ok;}
int main(int argc,char**argv){int headless=0,frames=0,metrics=0;const char*save_path="successor-save.bin",*capture_path=NULL;char script[4097]={0};for(int i=1;i<argc;i++){if(!strcmp(argv[i],"--headless"))headless=1;else if(!strncmp(argv[i],"--frames=",9))frames=atoi(argv[i]+9);else if(!strcmp(argv[i],"--metrics"))metrics=1;else if(!strncmp(argv[i],"--actions=",10)){if(strlen(argv[i]+10)>4096)return 2;snprintf(script,sizeof(script),"%s",argv[i]+10);}else if(!strncmp(argv[i],"--capture=",10))capture_path=argv[i]+10;else if(!strncmp(argv[i],"--save-path=",12))save_path=argv[i]+12;else{fprintf(stderr,"Unknown game option\n");return 2;}}if(frames<0||frames>1000000)return 2;if(headless){SDL_setenv("SDL_VIDEODRIVER","dummy",0);SDL_setenv("SDL_AUDIODRIVER","dummy",0);}if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_AUDIO|SDL_INIT_GAMECONTROLLER|SDL_INIT_TIMER)){fprintf(stderr,"SDL initialization: %s\n",SDL_GetError());return 3;}window=SDL_CreateWindow(GAME_TITLE,SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,1280,720,headless?SDL_WINDOW_HIDDEN:SDL_WINDOW_RESIZABLE);renderer=window?SDL_CreateRenderer(window,-1,SDL_RENDERER_SOFTWARE):NULL;if(!renderer){fprintf(stderr,"SDL renderer: %s\n",SDL_GetError());SDL_Quit();return 3;}SDL_RenderSetLogicalSize(renderer,VW,VH);SDL_AudioSpec want={0},have={0};want.freq=48000;want.format=AUDIO_S16SYS;want.channels=2;want.samples=1024;want.callback=audio_callback;want.userdata=&A;audio_device=SDL_OpenAudioDevice(NULL,0,&want,&have,0);if(audio_device){A.sample_rate=have.freq;SDL_PauseAudioDevice(audio_device,0);}for(int i=0;i<SDL_NumJoysticks();i++)if(SDL_IsGameController(i)){controller=SDL_GameControllerOpen(i);break;}reset_game();paused=!headless;int script_masks[512],script_frames[512],script_count=0,script_index=0,script_remaining=0;char*token=strtok(script,",");while(token){if(script_count>=512){SDL_Quit();return 2;}char*colon=strchr(token,':');if(!colon){SDL_Quit();return 2;}*colon=0;int mask=action_mask(token),duration=atoi(colon+1);if(mask<0||duration<1||duration>1000000){SDL_Quit();return 2;}script_masks[script_count]=mask;script_frames[script_count++]=duration;token=strtok(NULL,",");}if(script_count)script_remaining=script_frames[0];Uint64 begin=SDL_GetPerformanceCounter(),last=begin;double accumulator=0;int running=1,rendered=0;while(running){SDL_Event event;while(SDL_PollEvent(&event)){if(event.type==SDL_QUIT)running=0;if(event.type==SDL_CONTROLLERDEVICEADDED&&!controller)controller=SDL_GameControllerOpen(event.cdevice.which);if(event.type==SDL_CONTROLLERDEVICEREMOVED&&controller&&!SDL_GameControllerGetAttached(controller)){SDL_GameControllerClose(controller);controller=NULL;}if(event.type==SDL_WINDOWEVENT&&event.window.event==SDL_WINDOWEVENT_FOCUS_LOST){paused=1;S.previous_input=0;}if(event.type==SDL_KEYDOWN&&!event.key.repeat){SDL_Keycode key=event.key.keysym.sym;if(rebind_index>=0){bindings[rebind_index]=key;rebind_index=-1;}else if(key==SDLK_ESCAPE){paused=!paused;S.previous_input=0;}else if(key==SDLK_m)map_visible=!map_visible;else if(paused){if(key==SDLK_RETURN){if(S.mode==1){S.x=S.checkpoint<0?SPAWN_X:checkpoints[S.checkpoint].x;S.y=S.checkpoint<0?SPAWN_Y:checkpoints[S.checkpoint].y;S.health=(int)RESOURCES_MAX_HEALTH;S.mode=0;S.fish.phase=0;}paused=0;S.previous_input=0;}else if(key==SDLK_s)save_game(save_path);else if(key==SDLK_l)load_game(save_path);else if(key==SDLK_n){reset_game();paused=0;}else if(key==SDLK_i)menu_page=1;else if(key==SDLK_c)menu_page=2;else if(menu_page==2&&key>=SDLK_1&&key<=SDLK_9)rebind_index=key-SDLK_1;}else if(key==SDLK_F5)save_game(save_path);else if(key==SDLK_F9)load_game(save_path);else if(key==SDLK_LEFTBRACKET)S.crop=(S.crop+CROP_COUNT-1)%CROP_COUNT;else if(key==SDLK_RIGHTBRACKET)S.crop=(S.crop+1)%CROP_COUNT;else if(key==SDLK_F10){sound_enabled=!sound_enabled;if(audio_device)SDL_PauseAudioDevice(audio_device,!sound_enabled);}}}
Uint64 now=SDL_GetPerformanceCounter();double elapsed=(double)(now-last)/SDL_GetPerformanceFrequency();last=now;accumulator+=headless?DT:fmin(.2,elapsed);int count=0;while(accumulator>=DT&&count++<12){if(!paused){int mask=input_mask();if(script_index<script_count){mask=script_masks[script_index];if(--script_remaining<=0){script_index++;if(script_index<script_count)script_remaining=script_frames[script_index];}}tick(mask);if(S.mode&&!headless)paused=1;}accumulator-=DT;}render();rendered++;if(frames&&rendered>=frames)running=0;if(!headless)SDL_Delay(1);}if(capture_path&&!capture(capture_path)){fprintf(stderr,"Actual frame capture failed\n");running=-1;}double seconds=(double)(SDL_GetPerformanceCounter()-begin)/SDL_GetPerformanceFrequency();if(metrics)printf("{\"spec_digest\":\"%s\",\"frames\":%d,\"steps\":%d,\"seconds\":%.9f,\"render_fps\":%.3f,\"player_x\":%.9f,\"player_y\":%.9f,\"health\":%d,\"day\":%d,\"fish_caught\":%d,\"harvested\":%d,\"coins\":%d,\"mode\":%d,\"physics_hz\":60}\n",SPEC_DIGEST,rendered,S.steps,seconds,rendered/fmax(.000001,seconds),S.x,S.y,S.health,S.day,S.fish_caught,S.harvested,S.coins,S.mode);if(controller)SDL_GameControllerClose(controller);if(audio_device)SDL_CloseAudioDevice(audio_device);SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();return running==-1?4:0;}
"""


_RENDERER = r"""
static SDL_Texture*art_texture=NULL;static double previous_render_camera_x=-1,previous_render_camera_y=-1;
static void sprite(int index,double x,double y,double w,double h){SDL_Rect source={(index%8)*16,(index/8)*16,16,16},target={(int)round(x-S.camera_x),(int)round(y-S.camera_y),(int)ceil(w),(int)ceil(h)};if(!art_texture||target.x+target.w<0||target.y+target.h<0||target.x>VW||target.y>VH)return;SDL_RenderCopy(renderer,art_texture,&source,&target);}
static void icon(int index,int x,int y,int size){SDL_Rect source={(index%8)*16,(index/8)*16,16,16},target={x,y,size,size};if(art_texture)SDL_RenderCopy(renderer,art_texture,&source,&target);}
static void shadow(double x,double y,double w,double h){SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND);SDL_SetRenderDrawColor(renderer,8,24,25,FIDELITY_LEVEL==0?0:FIDELITY_LEVEL==1?80:110);SDL_Rect r={(int)(x-S.camera_x),(int)(y-S.camera_y),(int)w,(int)h};SDL_RenderFillRect(renderer,&r);SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_NONE);}
static void render(void){
 double actual_camera_x=S.camera_x,actual_camera_y=S.camera_y;if(FIDELITY_LEVEL>=2&&previous_render_camera_x>=0){S.camera_x=(S.camera_x+previous_render_camera_x)/2;S.camera_y=(S.camera_y+previous_render_camera_y)/2;}
 static const unsigned int colours[8]={0x34694c,0x3274a3,0x647078,0xc9ae6e,0xac9570,0x527446,0x745236,0x41424f};colour(palette[0]);SDL_RenderClear(renderer);
 int left=(int)(S.camera_x/TILE),top=(int)(S.camera_y/TILE);
 for(int y=top;y<(int)fmin(TERRAIN_ROWS,top+ceil(VH/TILE)+2);y++)for(int x=left;x<(int)fmin(TERRAIN_COLS,left+ceil(VW/TILE)+2);x++){int kind=terrain[y][x]-'0',variation=(x*17+y*31+(int)(GAME_SEED%97))%4,tile=kind==1?4+(S.steps/20)%4:kind==2?10:kind==3?8:kind==4?9:kind==5?13:kind==6?11:kind==7?14:variation;sprite(tile,x*TILE,y*TILE,TILE,TILE);if((kind==0||kind==5)&&variation==0&&(x*31+y*7)%11==0)sprite(15,x*TILE+3,y*TILE+4,24,24);if(kind==5&&(x*13+y*19)%9==0){shadow(x*TILE-3,y*TILE+8,38,22);sprite(28,x*TILE-7,y*TILE-20,46,52);}}
 for(int i=0;i<PONDS_COUNT;i++){Rect p=ponds[i];for(double y=p.y;y<p.y+p.h;y+=TILE)for(double x=p.x;x<p.x+p.w;x+=TILE)sprite(4+(S.steps/20)%4,x,y,fmin(TILE,p.x+p.w-x),fmin(TILE,p.y+p.h-y));if(distance_rect(p)<FISHING_CAST_RANGE+64){sprite(36,p.x+8,p.y+8,24,24);text((int)(p.x-S.camera_x+38),(int)(p.y-S.camera_y+14),"FISHING WATER",0xe6f9ef,1);}}
 for(int i=0;i<FARMS_COUNT;i++){Rect f=farms[i];for(double y=f.y;y<f.y+f.h;y+=TILE)for(double x=f.x;x<f.x+f.w;x+=TILE)sprite(11,x,y,fmin(TILE,f.x+f.w-x),fmin(TILE,f.y+f.h-y));if(i%6==0)sprite(31,f.x-8,f.y-8,24,24);}
 for(int i=0;i<LANDMARK_COUNT;i++){LandmarkSpec l=landmarks[i];shadow(l.x+3,l.y+l.h*.65,l.w,l.h*.28);sprite(l.sprite,l.x,l.y,l.w,l.h);if(hypot(S.x-l.x,S.y-l.y)<140)text((int)(l.x-S.camera_x),(int)(l.y-S.camera_y-13),l.name,0xe6f9ef,1);}
 for(int i=0;i<OBSTACLES_COUNT;i++){Rect o=obstacles[i];shadow(o.x+4,o.y+o.h-10,o.w,14);for(double y=o.y;y<o.y+o.h;y+=TILE)for(double x=o.x;x<o.x+o.w;x+=TILE)sprite(10,x,y,fmin(TILE,o.x+o.w-x),fmin(TILE,o.y+o.h-y));}
 for(int i=0;i<DOOR_COUNT;i++){DoorSpec d=doors[i];sprite(43,d.x,d.y,d.w,d.h);if(overlap(S.x-20,S.y-20,BW+40,BH+40,(Rect){d.x,d.y,d.w,d.h}))text((int)(d.x-S.camera_x-8),(int)(d.y-S.camera_y-16),d.requires&&!S.keys?"SHRINE KEY":"E ENTER",0xffe19b,1);}
 for(int i=0;i<CHECKPOINTS_COUNT;i++){Rect p=checkpoints[i];sprite(44,p.x-7,p.y-19,32,40);}
 for(int i=0;i<S.plot_count;i++){Plot p=S.plots[i];sprite(p.water>.3?12:11,p.x,p.y,TILE,TILE);if(p.crop>=0){int stage=(int)fmin(3,floor(p.growth*4));sprite(stage==3?48+(p.crop%8):32+stage,p.x+2,p.y-6,TILE-4,TILE+4);if(p.growth>=1)sprite(56,p.x+TILE-12,p.y-10,12,12);}}
 for(int i=0;i<ITEM_COUNT;i++)if(!S.collected[i]){ItemSpec item=items[i];shadow(item.x-2,item.y+10,16,6);sprite(item.kind==0?45:46,item.x-4,item.y-8,24,24);}
 for(int i=0;i<NPC_COUNT;i++){NpcSpec n=npcs[i];shadow(n.x-2,n.y+15,22,8);sprite(20+i%4,n.x-7,n.y-12,32,36);if(hypot(S.x-n.x,S.y-n.y)<100){text((int)(n.x-S.camera_x-10),(int)(n.y-S.camera_y-24),n.name,0xffffff,1);if(hypot(S.x-n.x,S.y-n.y)<ADVENTURE_INTERACT_RADIUS+12)sprite(56,n.x+18,n.y-16,14,14);}}
 for(int i=0;i<ENEMY_COUNT;i++){Enemy e=S.enemies[i];if(e.hp<=0)continue;shadow(e.x-3,e.y+e.h-4,e.w+6,10);sprite(e.boss?27:24+i%3,e.x-5,e.y-10,e.w+10,e.h+12);rect(e.x,e.y-16,e.w,4,0x372a2a);rect(e.x,e.y-16,e.w*e.hp/e.maxhp,4,palette[3]);}
 for(int i=0;i<S.bullet_count;i++){Bullet b=S.bullets[i];rect(b.x-4,b.y-4,8,8,b.friendly?palette[4]:palette[3]);rect(b.x-1,b.y-1,3,3,0xffffff);}shadow(S.x-4,S.y+14,26,10);int facing=fabs(S.fx)>fabs(S.fy)?(S.fx<0?18:19):(S.fy<0?17:16);if(S.invulnerable<=0||S.steps%8<4)sprite(facing,S.x-7,S.y-12,32,36);if(S.attack_cd>ADVENTURE_MELEE_COOLDOWN-.1)sprite(61,S.x+9+S.fx*24-10,S.y+10+S.fy*24-10,24,24);
 if(S.fish.phase&&S.fish.pond>=0){double target_x=ponds[S.fish.pond].x+18,target_y=clamp(S.y+10,ponds[S.fish.pond].y+8,ponds[S.fish.pond].y+ponds[S.fish.pond].h-8);colour(0xffeac1);SDL_RenderDrawLine(renderer,(int)(S.x+9-S.camera_x),(int)(S.y+5-S.camera_y),(int)(target_x-S.camera_x),(int)(target_y-S.camera_y));sprite(36,target_x-7,target_y-7,14,14);}
 double night=FIDELITY_LIGHTING*(1-cos(S.clock/FARMING_DAY_SECONDS*6.283185307))/2;SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND);SDL_SetRenderDrawColor(renderer,7,12,45,(Uint8)(night*255));SDL_Rect sky={0,0,VW,VH};SDL_RenderFillRect(renderer,&sky);SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_NONE);if(S.weather)for(int i=0;i<80;i++)box((i*73+S.steps*2)%VW,(i*29+S.steps*3)%VH,1,5,0xa4d6e9);
 for(int layer=1;layer<FIDELITY_LAYERS;layer++)for(int i=0;i<(int)FIDELITY_PARTICLES/FIDELITY_LAYERS;i++){int x=(i*73+layer*41+S.steps/(3+layer)-(int)(S.camera_x*.1*layer))%VW,y=(i*29+layer*37-S.steps/(7+layer))%VH;if(x<0)x+=VW;if(y<0)y+=VH;box(x,y,layer==2?2:1,1,palette[5]);}if(FIDELITY_LEVEL>=2){SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND);for(int band=0;band<12;band++){SDL_SetRenderDrawColor(renderer,14,18,38,(Uint8)((12-band)*2));SDL_Rect left={band*4,0,4,VH},right={VW-band*4-4,0,4,VH};SDL_RenderFillRect(renderer,&left);SDL_RenderFillRect(renderer,&right);}SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_NONE);}
 box(0,0,VW,46,0x152c35);box(0,45,VW,2,0x80baa3);char line[180];static const char*seasons[]={"SPRING","SUMMER","AUTUMN","WINTER"};for(int i=0;i<(int)RESOURCES_MAX_HEALTH;i++)icon(i<S.health?57:56,8+i*17,7,16);box(8,28,94,5,0x375162);box(8,28,(int)(94*S.energy/RESOURCES_MAX_ENERGY),5,0x83ced0);icon(58,122,7,22);snprintf(line,sizeof(line),"%d",S.coins);text(150,10,line,0xffe19b,2);snprintf(line,sizeof(line),"DAY %d %s",S.day,seasons[S.season]);text(250,8,line,0xeef5e8,2);snprintf(line,sizeof(line),"%s  FISH %d  CROPS %d  STONES %d",S.weather?"RAIN":"CLEAR",S.fish_caught,S.harvested,S.relics);text(250,29,line,0xbdd5c7,1);
 box(0,VH-48,VW,48,0x152c35);box(0,VH-49,VW,1,0x80baa3);static const char*tools[]={"FISH","HOE","WATER","PLANT","HARVEST"};static const int tool_icons[]={37,39,38,59,48};for(int i=0;i<5;i++){int x=7+i*100;box(x,VH-40,94,34,i==S.tool?0x6c6350:0x29434a);icon(tool_icons[i],x+4,VH-36,24);text(x+31,VH-31,tools[i],0xffffff,1);snprintf(line,sizeof(line),"%d",i+1);text(x+78,VH-19,line,0xcdddbd,1);}icon(48+S.crop%8,515,VH-39,25);text(545,VH-33,crops[S.crop].name,0xffe19b,1);snprintf(line,sizeof(line),"%d SEEDS",S.seeds[S.crop]);text(545,VH-18,line,0xcdddbd,1);
 if(S.dialogue_time>0){box(8,VH-98,VW-16,42,0x17313b);char first[96],second[96];size_t length=strlen(S.dialogue),split=length>94?94:length;memcpy(first,S.dialogue,split);first[split]=0;text(18,VH-89,first,0xffe8b2,1);snprintf(second,sizeof(second),"%.94s",S.dialogue+split);text(18,VH-74,second,0xffe8b2,1);}else{int next=-1;for(int i=0;i<QUEST_COUNT;i++)if(!S.quest_done[i]){next=i;break;}if(next>=0){box(8,54,280,28,0x17313b);icon(56,13,59,16);text(36,63,quests[next].text,0xe6f0d3,1);}}
 if(S.fish.phase){box(162,234,316,65,0x15313b);text(178,243,S.fish.phase==1?"WAIT FOR A BITE":"REEL HOLD AND RELEASE",0xffe19b,2);box(178,265,284,9,0x39555e);box(178,265,(int)(284*S.fish.progress),9,0x8bd899);box(178,282,284,7,0x39555e);box(178,282,(int)(284*S.fish.tension),7,0xe68d75);}
 if(map_visible){box(392,54,240,190,0x152c35);text(404,62,"VALLEY MAP",0xffe19b,2);for(int y=0;y<TERRAIN_ROWS;y+=3)for(int x=0;x<TERRAIN_COLS;x+=3)box(404+x*214/TERRAIN_COLS,85+y*145/TERRAIN_ROWS,4,4,colours[terrain[y][x]-'0']);for(int i=0;i<CHECKPOINTS_COUNT;i++)icon(44,400+(int)(checkpoints[i].x/WORLD_W*214),80+(int)(checkpoints[i].y/WORLD_H*145),10);box(404+(int)(S.x/WORLD_W*214),85+(int)(S.y/WORLD_H*145),5,5,0xffe19b);}
 if(paused){box(62,51,516,256,0x203540);box(65,54,510,2,0x80baa3);text(86,73,GAME_TITLE,0xffe19b,2);text(86,103,S.mode==1?"RESTORE AT YOUR WAYSTONE":S.mode==2?"THE VALLEY IS RESTORED":"A NEW VALLEY AWAITS",0xeef5e8,2);text(86,130,"ENTER PLAY  S SAVE  L LOAD",0xffffff,2);text(86,153,"N NEW  I INVENTORY  C CONTROLS",0xc7decd,1);if(menu_page==1){int y=175;for(int i=0;i<QUEST_COUNT;i++){snprintf(line,sizeof(line),"%s %s",S.quest_done[i]?"DONE":"TODO",quests[i].text);text(86,y,line,0xe8ddb3,1);y+=16;}snprintf(line,sizeof(line),"TACKLE %d  WATERING %d  RARE FISH %d",S.rod_level,S.watering_level,S.rare_fish);text(86,257,line,0xffffff,1);}else if(menu_page==2){text(86,179,"1 TO 9 THEN NEW KEY TO REBIND",0xffe19b,1);text(86,202,"1 LEFT 2 RIGHT 3 UP 4 DOWN 5 SWORD",0xffffff,1);text(86,224,"6 BOW 7 TALK 8 FISH 9 HOE",0xffffff,1);if(rebind_index>=0)text(86,255,"PRESS A NEW KEY",0xffe19b,2);}else{text(86,180,"ARROWS WASD MOVE J SWORD K BOW E TALK",0xffffff,1);text(86,203,"SPACE TOOL TAB NEXT R REST M MAP",0xffffff,1);text(86,226,"GAMEPAD STICK A TALK B SWORD X TOOL",0xffffff,1);text(86,250,"F5 SAVE F9 LOAD F10 SOUND",0xffe19b,1);}}
 SDL_RenderPresent(renderer);S.camera_x=actual_camera_x;S.camera_y=actual_camera_y;previous_render_camera_x=actual_camera_x;previous_render_camera_y=actual_camera_y;
}
"""


def emit_native(spec: Mapping[str, Any]) -> dict[str, str]:
    from .game_successor_assets import emit_successor_assets
    from .game_successor_runtime import _canonical, _digest

    if spec.get("gameplay_mode") != "top_down":
        raise ValueError("the full native successor currently requires a topdown recipe")
    prefix = "game/generated/native/pc_linux/"
    start = _C.index("static void render(void)")
    end = _C.index("\ntypedef struct{char magic", start)
    source = _C[:start] + _RENDERER + _C[end:]
    source = source.replace('#include "game_spec.h"', '#include "game_spec.h"\n#include "../game_art.h"')
    source = source.replace(
        "SDL_RenderSetLogicalSize(renderer,VW,VH);",
        'SDL_RenderSetLogicalSize(renderer,VW,VH);SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY,FIDELITY_LEVEL>=2?"1":"0");SDL_RenderSetIntegerScale(renderer,FIDELITY_LEVEL<2?SDL_TRUE:SDL_FALSE);SDL_Surface*atlas=SDL_CreateRGBSurfaceWithFormatFrom((void*)SUCCESSOR_ART_PIXELS,SUCCESSOR_ART_WIDTH,SUCCESSOR_ART_HEIGHT,16,SUCCESSOR_ART_WIDTH*2,SDL_PIXELFORMAT_RGB565);if(!atlas){SDL_Quit();return 3;}SDL_SetColorKey(atlas,SDL_TRUE,0xf81f);art_texture=SDL_CreateTextureFromSurface(renderer,atlas);SDL_FreeSurface(atlas);if(!art_texture){SDL_Quit();return 3;}SDL_SetTextureColorMod(art_texture,(Uint8)FIDELITY_TINT_R,(Uint8)FIDELITY_TINT_G,(Uint8)FIDELITY_TINT_B);',
    )
    source = source.replace(
        "SDL_DestroyRenderer(renderer);", "SDL_DestroyTexture(art_texture);SDL_DestroyRenderer(renderer);"
    )
    files = {
        prefix + "src/main.c": source,
        prefix + "include/game_spec.h": _header(spec),
        prefix
        + "project.json": json.dumps(
            {
                "schema_version": "skeleton.original_successor_native.v1",
                "target_id": "pc_linux",
                "language": "c99",
                "runtime": "sdl2",
                "spec_digest": _digest(spec),
                "fixed_step_hz": 60,
                "output_status": "source_not_compiled",
                "hardware_compatibility_verified": False,
            },
            sort_keys=True,
            indent=2,
        ),
        prefix + "spec.json": _canonical(spec).decode(),
        prefix
        + "README.md": "Portable original C99 / SDL2 game. Use the existing governed console-build pipeline for an actual Linux binary. Menus: Enter play, Esc pause, S/L save/load, I inventory, C controls. Arrows/WASD move; J sword, K bow, E talk, Space tool, Tab next, R rest near a waystone, 1-5 direct tools, [/] crop selection, M map, F10 sound. Gamepad: stick/D-pad, A talk, B sword, X tool, Y next. --headless --frames=N --metrics --actions=right:120,down:120 executes actual gameplay and renderer; --capture=frame.bmp writes an actual frame. No automated tests or hardware claims.\n",
    }
    files.update(emit_successor_assets(spec))
    return files
