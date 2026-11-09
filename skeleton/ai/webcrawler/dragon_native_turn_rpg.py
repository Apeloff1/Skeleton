"""Original turn-based RPG native SDL engine, separate from arcade/dungeon code.

Grid exploration, party stats, battle state machine, mana/heal/guard/spells,
enemies and bosses, XP-based character levels, chapter transitions, keys,
chest items, command input, save-later boundaries, native controller events.
No browser, unlicensed IP, generic "adventure" pretending to be RPG.
"""
from __future__ import annotations
from .dragon_game_blueprints import Campaign,W,H

ENGINE=r'''/* Dragon Native RPG, original SDL2 turn-based battle mechanics. */
#include <SDL.h>
#include <math.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "dragon_campaign.h"
#define TILE 24
#define SCREEN_W (MAP_W*TILE)
#define SCREEN_H (MAP_H*TILE)
#define MOB_COUNT 50
enum {EXPLORE=0,BATTLE=1,DEFEAT=2,VICTORY=3};
typedef struct{int x,y,hp,maxhp,attack,level,alive,boss;}Enemy;
typedef struct{int x,y,hp,maxhp,mp,maxmp,level,xp,attack,defense;
                int potions,ether,keys,gems,gold,guard;}Hero;
typedef struct{Hero hero;Enemy enemies[MOB_COUNT];int mode,chapter,score,guardians;
               int remaining,key_seen,required_key,active_enemy,frame;
               char map[MAP_H][MAP_W+1];}Game;
static Game game;
static SDL_Window*window;
static SDL_Renderer*render;
static SDL_GameController*controller;
static uint32_t rng=GAME_SEED;
static uint32_t random32(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static int dice(int n){return n>0?(int)(random32()%(uint32_t)n):0;}
static int clamp(int n,int a,int b){return n<a?a:(n>b?b:n);}
static void rect(int x,int y,int w,int h,int r,int g,int b){
 SDL_Rect d={x,y,w,h};SDL_SetRenderDrawColor(render,r,g,b,255);
 SDL_RenderFillRect(render,&d);
}
static char tile(int x,int y){
 if(x<0||x>=MAP_W||y<0||y>=MAP_H)return '#';
 return game.map[y][x];
}
static int enemy_at(int x,int y){
 for(int i=0;i<MOB_COUNT;i++)
  if(game.enemies[i].alive&&game.enemies[i].x==x&&game.enemies[i].y==y)
   return i;
 return -1;
}
static void chapter_load(int n){
 if(n>=STAGE_COUNT){game.mode=VICTORY;return;}
 game.chapter=n;game.remaining=0;game.guardians=0;
 game.required_key=0;game.key_seen=0;game.active_enemy=-1;
 memset(game.enemies,0,sizeof(game.enemies));
 for(int y=0;y<MAP_H;y++){
  memcpy(game.map[y],campaign_stage[n][y],MAP_W+1);
  for(int x=0;x<MAP_W;x++){
   char cell=game.map[y][x];
   if(cell=='S'){
    game.hero.x=x;game.hero.y=y;game.map[y][x]='.';
   }else if(cell=='K'){game.required_key=1;}
   else if(cell=='*'){game.remaining++;}
   else if(cell=='E'||cell=='B'){
    for(int k=0;k<MOB_COUNT;k++)if(!game.enemies[k].alive){
     int boss=(cell=='B');
     game.enemies[k]=(Enemy){x,y,(boss?12:4)+n*2,
       (boss?12:4)+n*2,2+n,boss?2:1,1,boss};
     if(boss)game.guardians++;
     game.map[y][x]='.';break;
    }
   }
  }
 }
 game.hero.hp=clamp(game.hero.hp+2,1,game.hero.maxhp);
 game.hero.mp=clamp(game.hero.mp+2,0,game.hero.maxmp);
 game.mode=EXPLORE;
}
static void fresh_game(void){
 rng=GAME_SEED;memset(&game,0,sizeof(game));
 game.hero=(Hero){0,0,18,18,8,8,1,0,4,1,2,1,0,0,0,0};
 chapter_load(0);
}
static void levelup(void){
 int need=game.hero.level*50;
 while(game.hero.xp>=need && game.hero.level<30){
  game.hero.xp-=need;game.hero.level++;
  game.hero.maxhp+=3;game.hero.maxmp+=2;
  game.hero.attack++;game.hero.defense+=(game.hero.level%3==0);
  game.hero.hp=game.hero.maxhp;game.hero.mp=game.hero.maxmp;
  need=game.hero.level*50;
 }
}
static void enemy_turn(Enemy*e){
 int base=e->attack+dice(3);
 int received=clamp(base-game.hero.defense-(game.hero.guard?4:0),0,99);
 game.hero.guard=0;
 game.hero.hp-=received;
 if(game.hero.hp<=0){game.hero.hp=0;game.mode=DEFEAT;}
}
static void resolve_battle(int action){
 if(game.mode!=BATTLE||game.active_enemy<0)return;
 Enemy*e=&game.enemies[game.active_enemy];
 if(!e->alive){game.mode=EXPLORE;return;}
 int damage=0;int consume=1;
 if(action==1){ /* sword strike */
  damage=clamp(game.hero.attack+dice(4)-e->level,1,99);
 }else if(action==2){ /* spell: 3 MP, bypass armour */
  if(game.hero.mp<3){consume=0;}
  else{game.hero.mp-=3;damage=6+game.hero.level*2+dice(4);}
 }else if(action==3){ /* guard */
  game.hero.guard=1;
 }else if(action==4){ /* potion */
  if(game.hero.potions<=0){consume=0;}
  else{game.hero.potions--;game.hero.hp=
    clamp(game.hero.hp+12,0,game.hero.maxhp);}
 }else if(action==5){ /* ether */
  if(game.hero.ether<=0){consume=0;}
  else{game.hero.ether--;game.hero.mp=
    clamp(game.hero.mp+6,0,game.hero.maxmp);}
 }else consume=0;
 if(!consume)return; /* invalid action cannot cost a turn */
 e->hp-=damage;
 if(e->hp<=0){
  e->hp=0;e->alive=0;game.mode=EXPLORE;
  int xp=15+e->level*12+(e->boss?35:0);
  game.hero.xp+=xp;game.hero.gold+=5+e->level*3;
  game.score+=xp;
  if(e->boss){game.guardians--;game.hero.potions++;}
  levelup();
 }else enemy_turn(e);
}
static void attempt_move(int dx,int dy){
 if(game.mode!=EXPLORE)return;
 int nx=game.hero.x+dx,ny=game.hero.y+dy;
 char c=tile(nx,ny);
 if(c=='#'||c=='^'||c=='~')return;
 int enemy=enemy_at(nx,ny);
 if(enemy>=0){game.active_enemy=enemy;game.mode=BATTLE;return;}
 if(c=='D'&&game.hero.keys<=0)return;
 if(c=='D'){game.hero.keys--;game.map[ny][nx]='.';}
 game.hero.x=nx;game.hero.y=ny;
 if(c=='K'){game.hero.keys++;game.key_seen=1;game.map[ny][nx]='.';}
 if(c=='C'){
  game.hero.potions++;game.hero.gold+=9;game.map[ny][nx]='.';
 }
 if(c=='N'){
  game.hero.hp=clamp(game.hero.hp+3,0,game.hero.maxhp);
  game.hero.mp=clamp(game.hero.mp+2,0,game.hero.maxmp);
  game.map[ny][nx]='.';
 }
 if(c=='*'){game.remaining--;game.hero.gems++;game.score+=15;
  game.map[ny][nx]='.';}
 if(c=='G'&&game.guardians==0&&(!game.required_key||game.key_seen))
  chapter_load(game.chapter+1);
}
static void draw_symbol(int x,int y,char ch){
 int px=x*TILE,py=y*TILE;
 if(ch=='#'||ch=='='){
  rect(px,py,TILE,TILE,62,78,108);
  rect(px+1,py+1,TILE-2,3,138,161,184);
 }else if(ch=='G'){
  rect(px+6,py+3,12,20,47,142,183);
  rect(px+9,py+6,6,15,16,30,82);
 }else if(ch=='D'){
  rect(px+3,py+1,18,22,162,94,49);
  rect(px+18,py+12,3,3,245,214,91);
 }else if(ch=='K'){
  rect(px+8,py+4,8,6,244,213,96);
  rect(px+11,py+10,3,11,244,213,96);
 }else if(ch=='*'){
  rect(px+8,py+3,8,18,239,217,94);
  rect(px+3,py+8,18,8,239,217,94);
 }else if(ch=='C'){
  rect(px+3,py+9,18,12,134,71,50);
  rect(px+3,py+6,18,5,241,188,83);
 }else if(ch=='N'){
  rect(px+6,py+3,12,17,148,104,206);
 }else if(ch=='~'||ch=='^'){
  rect(px+2,py+4,20,16,ch=='~'?50:187,ch=='~'?147:76,134);
 }
}
static void draw_entity(int x,int y,int boss){
 int px=x*TILE+3,py=y*TILE+2;
 rect(px,py,boss?20:16,boss?20:16,boss?172:214,boss?53:102,117);
 rect(px+4,py+5,3,3,20,30,45);
 rect(px+12,py+5,3,3,20,30,45);
}
static void hud_digit(int x,int y,int value){
 static const unsigned char font[10][5]={
  {7,5,5,5,7},{2,6,2,2,7},{7,1,7,4,7},{7,1,3,1,7},
  {5,5,7,1,1},{7,4,7,5,7},{7,1,1,1,1},{7,1,1,1,1},
  {7,5,7,5,7},{7,5,7,1,7}};
 value=clamp(value,0,9);
 for(int yy=0;yy<5;yy++)for(int xx=0;xx<3;xx++)
  if(font[value][yy]&(1<<(2-xx)))rect(x+xx*3,y+yy*3,3,3,252,223,141);
}
static void stat(int x,int v){
 v=clamp(v,0,999);
 hud_digit(x,486,v/100);hud_digit(x+15,486,(v/10)%10);
 hud_digit(x+30,486,v%10);
}
static void render_frame(void){
 SDL_SetRenderDrawColor(render,18,27,42,255);SDL_RenderClear(render);
 for(int y=0;y<MAP_H;y++)for(int x=0;x<MAP_W;x++)
  draw_symbol(x,y,tile(x,y));
 for(int i=0;i<MOB_COUNT;i++)if(game.enemies[i].alive)
  draw_entity(game.enemies[i].x,game.enemies[i].y,game.enemies[i].boss);
 rect(game.hero.x*TILE+4,game.hero.y*TILE+4,16,16,80,205,152);
 rect(game.hero.x*TILE+11,game.hero.y*TILE,8,9,219,234,169);
 rect(game.hero.x*TILE+17,game.hero.y*TILE+5,2,3,20,42,48);
 rect(0,MAP_H*TILE,SCREEN_W,112,24,37,54);
 stat(16,game.hero.hp);stat(70,game.hero.mp);
 stat(124,game.hero.level);stat(192,game.hero.potions);
 stat(260,game.hero.keys);stat(330,game.hero.gold);
 stat(410,game.guardians);
 if(game.mode==BATTLE){
  rect(120,120,SCREEN_W-240,200,30,37,61);
  Enemy*e=&game.enemies[game.active_enemy];
  draw_entity(14,7,e->boss);
  for(int i=0;i<e->hp;i++)rect(160+i*12,160,8,10,225,83,109);
  /* Actions: 1 strike, 2 spell, 3 guard, 4 potion, 5 ether */
  for(int i=0;i<5;i++)rect(164+i*80,285,65,12,75+i*15,166,124);
 }
 if(game.mode==DEFEAT||game.mode==VICTORY)
  rect(170,150,SCREEN_W-340,150,
       game.mode==VICTORY?46:156,game.mode==VICTORY?161:38,83);
 SDL_RenderPresent(render);
}
static int pressed(SDL_GameControllerButton b){
 return controller&&SDL_GameControllerGetButton(controller,b);
}
int main(int argc,char**argv){
 if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_GAMECONTROLLER|SDL_INIT_EVENTS)!=0)
  return 1;
 window=SDL_CreateWindow("Dragon Original Turn RPG",SDL_WINDOWPOS_CENTERED,
  SDL_WINDOWPOS_CENTERED,SCREEN_W,SCREEN_H+112,SDL_WINDOW_SHOWN|SDL_WINDOW_RESIZABLE);
 if(!window){SDL_Quit();return 2;}
 render=SDL_CreateRenderer(window,-1,SDL_RENDERER_ACCELERATED|SDL_RENDERER_PRESENTVSYNC);
 if(!render)render=SDL_CreateRenderer(window,-1,SDL_RENDERER_SOFTWARE);
 if(!render){SDL_DestroyWindow(window);SDL_Quit();return 3;}
 SDL_RenderSetLogicalSize(render,SCREEN_W,SCREEN_H+112);
 for(int i=0;i<SDL_NumJoysticks();i++)
  if(SDL_IsGameController(i)){controller=SDL_GameControllerOpen(i);break;}
 fresh_game();
 if(argc==2&&strcmp(argv[1],"--smoke")==0){
  Enemy synthetic={7,5,10,10,1,1,1,0};
  game.enemies[0]=synthetic;game.active_enemy=0;game.mode=BATTLE;
  for(int i=0;i<20&&game.mode==BATTLE;i++)resolve_battle(i%3==0?2:1);
  int battle_pass=game.mode==EXPLORE&&game.hero.xp>0;
  for(int i=0;i<600;i++){
   attempt_move((i%4==0)-(i%4==2),(i%4==1)-(i%4==3));
   if(i%20==0)render_frame();
  }
  printf("DRAGON_TURN_RPG_SMOKE %s lvl=%d gold=%d chapter=%d\n",
    battle_pass?"PASS":"FAIL",game.hero.level,game.hero.gold,game.chapter);
  if(controller)SDL_GameControllerClose(controller);
  SDL_DestroyRenderer(render);SDL_DestroyWindow(window);SDL_Quit();
  return battle_pass?0:7;
 }
 int alive=1;
 while(alive){
  SDL_Event event;
  while(SDL_PollEvent(&event)){
   if(event.type==SDL_QUIT)alive=0;
   if(event.type==SDL_KEYDOWN&&!event.key.repeat){
    SDL_Keycode key=event.key.keysym.sym;
    if(key==SDLK_ESCAPE)alive=0;
    else if(key==SDLK_r&&(game.mode==DEFEAT||game.mode==VICTORY))
      fresh_game();
    else if(game.mode==BATTLE){
      if(key>=SDLK_1&&key<=SDLK_5)resolve_battle((int)(key-SDLK_0));
      else if(key==SDLK_SPACE)resolve_battle(1);
    }else if(game.mode==EXPLORE){
      if(key==SDLK_LEFT||key==SDLK_a)attempt_move(-1,0);
      if(key==SDLK_RIGHT||key==SDLK_d)attempt_move(1,0);
      if(key==SDLK_UP||key==SDLK_w)attempt_move(0,-1);
      if(key==SDLK_DOWN||key==SDLK_s)attempt_move(0,1);
    }
   }
   if(event.type==SDL_CONTROLLERBUTTONDOWN){
    int b=event.cbutton.button;
    if(game.mode==BATTLE){
      if(b==SDL_CONTROLLER_BUTTON_A)resolve_battle(1);
      if(b==SDL_CONTROLLER_BUTTON_X)resolve_battle(2);
      if(b==SDL_CONTROLLER_BUTTON_B)resolve_battle(3);
      if(b==SDL_CONTROLLER_BUTTON_Y)resolve_battle(4);
    }else if(game.mode==EXPLORE){
      if(b==SDL_CONTROLLER_BUTTON_DPAD_LEFT)attempt_move(-1,0);
      if(b==SDL_CONTROLLER_BUTTON_DPAD_RIGHT)attempt_move(1,0);
      if(b==SDL_CONTROLLER_BUTTON_DPAD_UP)attempt_move(0,-1);
      if(b==SDL_CONTROLLER_BUTTON_DPAD_DOWN)attempt_move(0,1);
    }
   }
  }
  render_frame();SDL_Delay(16);
 }
 if(controller)SDL_GameControllerClose(controller);
 SDL_DestroyRenderer(render);SDL_DestroyWindow(window);SDL_Quit();
 return 0;
}
'''

def render_rpg(campaign:Campaign)->dict[str,str]:
    if campaign.mode!="dungeon" or not 1<=len(campaign.stages)<=8:
        raise ValueError("native turn RPG requires dungeon campaign")
    if any(len(s.terrain)!=H or any(len(row)!=W for row in s.terrain)
           for s in campaign.stages):
        raise ValueError("invalid RPG stage dimensions")
    levels=[" {\n"+",\n".join('  "'+row+'"' for row in stage.terrain)+"\n }"
            for stage in campaign.stages]
    header=(
      "#ifndef DRAGON_CAMPAIGN_H\n#define DRAGON_CAMPAIGN_H\n"
      f"#define MAP_W {W}\n#define MAP_H {H}\n"
      f"#define STAGE_COUNT {len(campaign.stages)}\n"
      f"#define GAME_SEED {campaign.seed or 1}u\n"
      "static const char campaign_stage[STAGE_COUNT][MAP_H][MAP_W+1]={\n"
      +",\n".join(levels)+"\n};\n#endif\n"
    )
    cmake="""\
cmake_minimum_required(VERSION 3.16)
project(DragonNativeTurnRPG C)
set(CMAKE_C_STANDARD 99)
find_package(SDL2 REQUIRED)
add_executable(dragon_game src/main.c)
target_include_directories(dragon_game PRIVATE include)
target_link_libraries(dragon_game PRIVATE SDL2::SDL2)
"""
    readme=(
      "# Original Native Turn-Based RPG\n\n"
      "Native SDL2 C game with true discrete combat turns, inventory, spells, "
      "mana, consumables, guarding, enemy retaliation, boss gating, XP-derived "
      "character levels, gold, keys, chests and stage transitions. "
      "WASD/arrow move; 1 sword, 2 spell, 3 guard, 4 potion, 5 ether; "
      "gamepad A/X/B/Y controls main actions. Build cmake -S . -B build && "
      "cmake --build build. Use --smoke for native state-machine diagnostics. "
      "Compiling is not equivalent to finished game balancing or player review.\n"
    )
    return {"src/main.c":ENGINE,"include/dragon_campaign.h":header,
            "CMakeLists.txt":cmake,"README.engine.md":readme}
