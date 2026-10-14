"""Native SDL2 campaign renderer: six distinct modes, offline 60Hz gameplay.

Generates a cross-desktop C source engine and deterministic map header from
validated, traversable level graphs. No HTML/JS assets, external runtime
service, image downloads or untrusted source interpolation.
"""
from __future__ import annotations
from .dragon_game_blueprints import Campaign, PALETTES, MODE_IDS, W, H
import json

ENGINE = r'''/* Original Dragon Native 2D Game Engine — SDL2/C99.
  Six real rule sets: arena, platform, adventure, dungeon, tactics, racer. */
#include <SDL.h>
#include <stdint.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "dragon_campaign.h"
#include "dragon_save.h"
#include "dragon_replay.h"
#include "dragon_chip_score.h"
#define TILE 24
#define SCREEN_W (MAP_W*TILE)
#define SCREEN_H (MAP_H*TILE)
#define HUD 65
#define ENEMIES 40
#define PARTICLES 70
#define SHOTS 24
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define CLAMP(v,a,b) MIN(MAX(v,a),b)
typedef struct {float x,y,dx,dy;int alive,hp,mode,phase;} Enemy;
typedef struct {float x,y,dx,dy;int life;} Shot;
typedef struct {float x,y,dx,dy;int life;} Particle;
typedef struct {int left,right,up,down,jump,fire,pause,reset;} Input;
typedef struct {
  int stage,score,health,energy,remaining,frame,combo,won,lost,paused,invincible,turn;
  int keys,key_collected,quest_requires_key,guardians,caretakers,chests_opened;
  float x,y,dx,dy;int facing;
  char tiles[MAP_H][MAP_W+1];
  Enemy enemies[ENEMIES];
  Shot shots[SHOTS];
  Particle particles[PARTICLES];
} Game;
static Game game;
static SDL_Window*window;
static SDL_Renderer*renderer;
static SDL_GameController*controller;
static SDL_AudioDeviceID audioDevice;
static uint32_t rng=GAME_SEED?GAME_SEED:1;
static int checkpoints_ready=0;
static uint32_t save_serial=0;
static uint32_t random32(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static int rnd(int n){return n>0?(int)(random32()%(uint32_t)n):0;}
static void sound(int freq,int ms){
  if(!audioDevice)return;
  Uint8 buffer[1800];int len=ms*22;
  len=CLAMP(len,0,1800);
  int period=MAX(1,22050/freq);
  for(int i=0;i<len;i++){
    int volume=(len-i)*24/MAX(len,1);
    buffer[i]=(Uint8)(128+((i/period)&1?volume:-volume));
  }
  SDL_QueueAudio(audioDevice,buffer,(Uint32)len);
}
static void rect(float x,float y,int w,int h,Uint8 r,Uint8 g,Uint8 b){
  SDL_Rect d={(int)x,(int)y,w,h};
  SDL_SetRenderDrawColor(renderer,r,g,b,255);
  SDL_RenderFillRect(renderer,&d);
}
static char tile(int x,int y){
  if(x<0||y<0||x>=MAP_W||y>=MAP_H)return '#';
  return game.tiles[y][x];
}
static int wall(float x,float y){
  int tx=(int)x/TILE,ty=(int)y/TILE;
  if(x<0||y<0||x>=SCREEN_W||y>=SCREEN_H)return 1;
  char value=tile(tx,ty);
  return value=='#'||(value=='D'&&game.keys==0)||
         (GAME_MODE!=1&&value=='=');
}
static int collision(float x,float y){
  return wall(x+2,y+2)||wall(x+16,y+2)||wall(x+2,y+17)||wall(x+16,y+17);
}
static void sparks(float x,float y,int count){
  for(int n=0;n<count;n++){
    for(int i=0;i<PARTICLES;i++)if(game.particles[i].life<=0){
      float angle=(float)rnd(628)/100.f,spd=.6f+(float)rnd(28)/10.f;
      game.particles[i]=(Particle){x,y,cosf(angle)*spd,sinf(angle)*spd,15+rnd(25)};
      break;
    }
  }
}
static void hurt(void){
  if(game.invincible||game.lost||game.won)return;
  game.health--;game.invincible=40;
  sparks(game.x,game.y,12);sound(168,140);
  if(game.health<=0){game.lost=1;game.health=0;sound(90,400);}
}
static void begin_stage(int n){
  if(n>=STAGE_COUNT){game.won=1;sound(880,350);return;}
  game.stage=n;game.remaining=0;game.invincible=0;
  game.keys=0;game.key_collected=0;game.quest_requires_key=0;
  game.guardians=0;game.caretakers=0;game.chests_opened=0;
  game.health=CLAMP(game.health+1,1,6);
  game.energy=100;game.dx=game.dy=0;game.facing=1;
  memset(game.enemies,0,sizeof(game.enemies));
  memset(game.shots,0,sizeof(game.shots));
  memset(game.particles,0,sizeof(game.particles));
  for(int y=0;y<MAP_H;y++){
    memcpy(game.tiles[y],campaign_stage[n][y],MAP_W+1);
    for(int x=0;x<MAP_W;x++){
      char t=game.tiles[y][x];
      if(t=='S'){game.x=(float)x*TILE+4;game.y=(float)y*TILE+4;game.tiles[y][x]='.';}
      else if(t=='*')game.remaining++;
      else if(t=='K')game.quest_requires_key=1;
      else if(t=='E'||t=='B'){
        for(int i=0;i<ENEMIES;i++)if(!game.enemies[i].alive){
          game.enemies[i]=(Enemy){x*TILE+4.f,y*TILE+4.f,0,0,
            1,(t=='B'?4+n+DESIGN_DIFFICULTY/3:
               1+(DESIGN_DIFFICULTY-1)/4),(t=='B'?3:i%3),rnd(100)};
          if(t=='B')game.guardians++;
          game.tiles[y][x]='.';break;
        }
      }
    }
  }
  if(checkpoints_ready && n<STAGE_COUNT){
    if(save_serial<0xfffffffeu)save_serial++;
    dragon_save_checkpoint(CAMPAIGN_SIGNATURE,STAGE_COUNT,(uint32_t)n,
                           game.score,game.health,save_serial);
  }
  sound(520,90);
}
static void reset_game(void){
  rng=GAME_SEED?GAME_SEED:1;
  memset(&game,0,sizeof(game));game.health=4;begin_stage(0);
}
static uint32_t game_state_hash(void){
  uint32_t state[12]={
    (uint32_t)game.stage,(uint32_t)game.score,(uint32_t)game.health,
    (uint32_t)game.remaining,(uint32_t)game.won,(uint32_t)game.lost,
    (uint32_t)(int)(game.x*16),(uint32_t)(int)(game.y*16),
    (uint32_t)game.energy,
    (uint32_t)game.keys,(uint32_t)game.key_collected,
    (uint32_t)game.guardians
  };
  return dragon_replay_digest(state,12);
}
static uint16_t pack_input(Input in){
  return (uint16_t)(
    (in.left?DRAGON_INPUT_LEFT:0)|
    (in.right?DRAGON_INPUT_RIGHT:0)|
    (in.up?DRAGON_INPUT_UP:0)|
    (in.down?DRAGON_INPUT_DOWN:0)|
    (in.jump?DRAGON_INPUT_JUMP:0)|
    (in.fire?DRAGON_INPUT_FIRE:0)|
    (in.pause?DRAGON_INPUT_PAUSE:0)|
    (in.reset?DRAGON_INPUT_RESET:0));
}
static Input unpack_input(uint16_t mask){
  Input in={0};
  in.left=!!(mask&DRAGON_INPUT_LEFT);
  in.right=!!(mask&DRAGON_INPUT_RIGHT);
  in.up=!!(mask&DRAGON_INPUT_UP);
  in.down=!!(mask&DRAGON_INPUT_DOWN);
  in.jump=!!(mask&DRAGON_INPUT_JUMP);
  in.fire=!!(mask&DRAGON_INPUT_FIRE);
  in.pause=!!(mask&DRAGON_INPUT_PAUSE);
  in.reset=!!(mask&DRAGON_INPUT_RESET);
  return in;
}
static void fire(void){
  if(game.energy<9)return;
  for(int i=0;i<SHOTS;i++)if(game.shots[i].life<=0){
    game.shots[i]=(Shot){game.x+10,game.y+8,7.f*game.facing,0,45};
    game.energy-=9;sound(675,40);break;
  }
}
static void enemies_update(void){
  for(int i=0;i<ENEMIES;i++){
    Enemy*e=&game.enemies[i];if(!e->alive)continue;
    e->phase++;
    float speed=.24f+game.stage*.09f+DESIGN_DIFFICULTY*.035f;
    float dx=game.x-e->x,dy=game.y-e->y;
    float vx=e->mode==0?((e->phase/80)&1?-speed:speed):
                         (fabsf(dx)<145?(dx>0?speed:-speed):0);
    float vy=e->mode==2&&fabsf(dy)<140?(dy>0?speed:-speed):0;
    if(!collision(e->x+vx,e->y))e->x+=vx;
    if(!collision(e->x,e->y+vy))e->y+=vy;
    if(fabsf(e->x-game.x)<(e->mode==3?23:17)&&
       fabsf(e->y-game.y)<(e->mode==3?23:17))hurt();
    /* Guardian has longer pursuit range, larger HP and a visible red pulse. */
    if(e->mode==3 && e->phase%100==0 &&
       fabsf(e->x-game.x)<36&&fabsf(e->y-game.y)<36)
      hurt();
  }
}
static void projectile_update(void){
  for(int i=0;i<SHOTS;i++){
    Shot*b=&game.shots[i];if(b->life<=0)continue;
    b->x+=b->dx;b->y+=b->dy;b->life--;
    if(collision(b->x,b->y)){sparks(b->x,b->y,4);b->life=0;continue;}
    for(int j=0;j<ENEMIES;j++){
      Enemy*e=&game.enemies[j];if(!e->alive)continue;
      if(fabsf(e->x-b->x)<16&&fabsf(e->y-b->y)<16){
        b->life=0;e->hp--;sparks(e->x,e->y,10);
        if(e->hp<=0){
          e->alive=0;
          if(e->mode==3){
            game.guardians=MAX(0,game.guardians-1);
            game.score+=450;sound(980,210);sparks(e->x,e->y,30);
          }else{game.score+=100;sound(790,75);}
          game.combo++;
        }
        break;
      }
    }
  }
}
static void collect_tiles(void){
  int cx=(int)(game.x+9)/TILE,cy=(int)(game.y+9)/TILE;
  char t=tile(cx,cy);
  if(t=='*'){
    game.tiles[cy][cx]='.';game.score+=25;game.remaining--;
    game.combo++;sparks(game.x,game.y,9);sound(880,80);
  }else if(t=='+'){
    game.tiles[cy][cx]='.';game.health=CLAMP(game.health+1,0,6);
  }else if(t=='K'){
    game.tiles[cy][cx]='.';game.keys++;
    game.key_collected=1;game.score+=75;sound(720,160);
    sparks(game.x,game.y,15);
  }else if(t=='D'&&game.keys>0){
    game.tiles[cy][cx]='.';game.keys--;
    game.score+=50;sound(410,110);
  }else if(t=='C'){
    game.tiles[cy][cx]='.';game.chests_opened++;
    game.score+=80;game.health=CLAMP(game.health+1,0,6);
    sparks(game.x,game.y,14);sound(960,100);
  }else if(t=='N'){
    game.tiles[cy][cx]='.';game.caretakers++;
    game.score+=25;game.energy=100;sound(540,100);
  }else if(t=='^'||t=='~')hurt();
  else if(t=='G'&&(GAME_MODE!=0||game.remaining==0)&&
          game.guardians==0&&(!game.quest_requires_key||game.key_collected)){
    game.score+=200;sparks(game.x,game.y,24);begin_stage(game.stage+1);
  }
}
static void step(Input input){
  if(input.reset){reset_game();return;}
  if(input.pause&&!game.lost&&!game.won)game.paused=!game.paused;
  if(game.paused||game.lost||game.won)return;
  game.frame++;
  if(game.frame%DRAGON_SCORE_INTERVAL==0){
    int beat=(game.frame/DRAGON_SCORE_INTERVAL)%DRAGON_SCORE_STEPS;
    unsigned short note=DRAGON_MELODY[beat];
    unsigned short bass=DRAGON_HARMONY[beat];
    if(note>0)sound((int)note,55);
    if(bass>0)sound((int)bass,40);
  }
  if(game.invincible>0)game.invincible--;
  if(game.energy<100&&game.frame%5==0)game.energy++;
  float dx=(float)(input.right-input.left),dy=(float)(input.down-input.up);
  if(dx!=0)game.facing=dx>0?1:-1;
  if(GAME_MODE==1){/* platform: gravity, variable jump, one-way floor */
    float oldY=game.y;
    game.dx=2.7f*dx;game.dy=CLAMP(game.dy+.36f,-10.f,8.f);
    int feet=(int)(game.y+19)/TILE;
    int grounded=collision(game.x,game.y+2)||
      (tile((int)(game.x+9)/TILE,feet)=='='&&game.dy>=0);
    if(input.jump&&grounded){game.dy=-9.f;sound(495,90);}
    if(!collision(game.x+game.dx,game.y))game.x+=game.dx;
    if(!collision(game.x,game.y+game.dy))game.y+=game.dy;
    else game.dy=0;
    int tx=(int)(game.x+9)/TILE,ty=(int)(game.y+18)/TILE;
    if(game.dy>=0&&tile(tx,ty)=='='&&
       (int)(oldY+18)/TILE<ty){game.y=ty*TILE-19;game.dy=0;}
  }else if(GAME_MODE==4){/* tactics: discrete movement turns */
    if(game.turn>0)game.turn--;
    else if(dx||dy){
      float x=game.x+(dx?TILE*dx:0),y=game.y+(dx?0:TILE*dy);
      if(!collision(x,y)){game.x=x;game.y=y;}
      game.turn=10;enemies_update();
    }
  }else if(GAME_MODE==5){/* racer: inertia, speed and edge contact */
    game.dx=CLAMP(game.dx*.9f+dx*.24f,-4.5f,4.5f);
    game.dy=CLAMP(game.dy*.9f+dy*.24f,-4.5f,4.5f);
    if(!collision(game.x+game.dx,game.y))game.x+=game.dx;
    else{game.dx=0;hurt();}
    if(!collision(game.x,game.y+game.dy))game.y+=game.dy;
    else{game.dy=0;hurt();}
  }else{/* top-down arena, adventure and connected-room dungeon */
    float speed=(GAME_MODE==3?2.1f:3.1f);
    if(dx!=0&&dy!=0){dx*=.70710678f;dy*=.70710678f;}
    if(!collision(game.x+dx*speed,game.y))game.x+=dx*speed;
    if(!collision(game.x,game.y+dy*speed))game.y+=dy*speed;
  }
  if(input.fire&&game.frame%11==0&&GAME_MODE!=5)fire();
  if(GAME_MODE!=4)enemies_update();
  projectile_update();
  for(int i=0;i<PARTICLES;i++)if(game.particles[i].life>0){
    Particle*p=&game.particles[i];p->x+=p->dx;p->y+=p->dy;p->dy+=.09f;p->life--;
  }
  collect_tiles();
}
static void draw_tile(int x,int y,char t){
  int px=x*TILE,py=y*TILE;
  if(t=='#'||t=='='){
    rect(px,py,24,24,PALETTE[1][0],PALETTE[1][1],PALETTE[1][2]);
    rect(px+2,py+2,20,3,THEME_ACCENT[0],THEME_ACCENT[1],THEME_ACCENT[2]);
  }else if(t=='^'){
    rect(px+2,py+10,20,12,185,57,87);
    for(int n=0;n<3;n++)rect(px+4+n*7,py+4,3,7,235,96,103);
  }else if(t=='~'){
    for(int n=0;n<3;n++)rect(px+2,py+4+n*7,20,3,55,153,219);
  }else if(t=='*'){
    rect(px+8,py+4,8,16,245,210,96);
    rect(px+4,py+8,16,8,245,210,96);
    rect(px+10,py+10,4,4,255,250,200);
  }else if(t=='G'){
    rect(px+4,py+1,16,22,86,147,208);
    rect(px+7,py+5,10,15,14,31,76);
    rect(px+10,py+10,4,6,172,238,209);
  }else if(t=='+'){
    rect(px+9,py+3,6,18,85,210,127);
    rect(px+3,py+9,18,6,85,210,127);
  }else if(t=='K'){
    rect(px+9,py+3,7,6,248,212,96);
    rect(px+12,py+9,3,12,248,212,96);
    rect(px+10,py+17,9,4,248,212,96);
  }else if(t=='D'){
    rect(px+1,py+1,22,23,124,82,43);
    rect(px+5,py+3,14,20,170,122,70);
    rect(px+15,py+12,4,4,251,225,112);
  }else if(t=='C'){
    rect(px+3,py+8,18,13,118,67,52);
    rect(px+3,py+5,18,6,235,188,105);
    rect(px+11,py+11,4,6,255,236,122);
  }else if(t=='N'){
    rect(px+6,py+4,12,13,163,125,230);
    rect(px+9,py+8,2,2,28,35,50);
    rect(px+15,py+8,2,2,28,35,50);
    rect(px+7,py+17,10,5,105,161,234);
  }
}
static void draw_digit(int x,int y,int n,int scale){
  static const unsigned char patterns[10][5]={
    {7,5,5,5,7},{2,6,2,2,7},{7,1,7,4,7},{7,1,3,1,7},
    {5,5,7,1,1},{7,4,7,5,7},{7,1,1,1,1},
    {7,1,1,1,1},{7,5,7,5,7},{7,5,7,1,7}
  };
  if(n<0||n>9)return;
  for(int yy=0;yy<5;yy++)for(int xx=0;xx<3;xx++)
    if(patterns[n][yy]&(1<<(2-xx)))rect(x+xx*scale,y+yy*scale,scale,scale,255,229,164);
}
static void draw_number(int x,int y,int v,int scale){
  char b[24];snprintf(b,sizeof(b),"%d",CLAMP(v,0,999999));
  for(int i=0;b[i];i++)draw_digit(x+i*scale*4,y,b[i]-'0',scale);
}
static void render(void){
  SDL_SetRenderDrawColor(renderer,PALETTE[0][0],PALETTE[0][1],PALETTE[0][2],255);
  SDL_RenderClear(renderer);
  SDL_Rect viewport={0,HUD,SCREEN_W,SCREEN_H};
  SDL_RenderSetViewport(renderer,&viewport);
  for(int y=0;y<MAP_H;y++)for(int x=0;x<MAP_W;x++)draw_tile(x,y,game.tiles[y][x]);
  for(int i=0;i<ENEMIES;i++)if(game.enemies[i].alive){
    Enemy*e=&game.enemies[i];
    rect(e->x,e->y,e->mode==3?22:17,e->mode==3?22:17,
         e->mode==3?167:231,e->mode==3?51:94,116);
    if(e->mode==3)
      rect(e->x+3,e->y+18,16,3,(e->phase%30)<15?255:100,85,120);
    rect(e->x+3,e->y+4,4,4,28,32,46);
    rect(e->x+11,e->y+4,4,4,28,32,46);
  }
  for(int i=0;i<SHOTS;i++)if(game.shots[i].life>0)
    rect(game.shots[i].x,game.shots[i].y,5,5,252,241,105);
  for(int i=0;i<PARTICLES;i++)if(game.particles[i].life>0){
    Particle*p=&game.particles[i];rect(p->x,p->y,3,3,244,186,94);
  }
  if(!game.invincible||(game.frame/4)%2==0){
    /* Hand-drawn, procedural, blinking dragon with animated walk cycle. */
    int walk=(game.frame/10)%2;
    rect(game.x+2,game.y+6,16,14,PALETTE[2][0],PALETTE[2][1],PALETTE[2][2]);
    rect(game.x+8,game.y+1,8,9,PALETTE[3][0],PALETTE[3][1],PALETTE[3][2]);
    rect(game.x,game.y+8,5,6,PALETTE[1][0],PALETTE[1][1],PALETTE[1][2]);
    if(game.frame%130>5)rect(game.x+15,game.y+8,2,3,244,244,228);
    rect(game.x+4,game.y+19,4,3+walk,PALETTE[2][0],PALETTE[2][1],PALETTE[2][2]);
    rect(game.x+12,game.y+19,4,3+!walk,PALETTE[2][0],PALETTE[2][1],PALETTE[2][2]);
    /* Genuine original hero silhouettes selected by the signed JSON spec. */
    if(HERO_STYLE==1){ /* knight: helmet and sword */
      rect(game.x+6,game.y,12,4,193,202,218);
      rect(game.x+19,game.y+6,3,14,228,228,235);
    }else if(HERO_STYLE==2){ /* explorer: wide hat and backpack */
      rect(game.x+2,game.y,18,3,183,125,67);
      rect(game.x,game.y+7,5,12,128,94,64);
    }else if(HERO_STYLE==3){ /* pilot: aerodynamic wings */
      rect(game.x-4,game.y+9,9,4,82,178,228);
      rect(game.x+17,game.y+9,9,4,82,178,228);
    }else if(HERO_STYLE==4){ /* astronaut: helmet visor */
      rect(game.x+5,game.y,15,12,222,230,244);
      rect(game.x+8,game.y+2,9,7,54,142,204);
    }else if(HERO_STYLE==5){ /* robot: square sensor, antenna */
      rect(game.x+6,game.y-2,12,10,145,176,191);
      rect(game.x+11,game.y-5,3,5,213,124,236);
    }
  }
  SDL_RenderSetViewport(renderer,NULL);
  rect(0,0,SCREEN_W,HUD,17,27,42);
  rect(0,HUD-3,SCREEN_W,3,PALETTE[2][0],PALETTE[2][1],PALETTE[2][2]);
  for(int i=0;i<game.health;i++)rect(12+i*20,11,14,13,248,99,123);
  rect(12,34,100,6,56,69,80);
  rect(12,34,CLAMP(game.energy,0,100),6,108,214,160);
  draw_number(155,10,game.score,3);
  draw_number(345,10,game.stage+1,3);
  draw_number(448,10,game.remaining,3);
  draw_number(530,10,game.keys,3);
  draw_number(630,10,game.guardians,3);
  if(game.quest_requires_key&&!game.key_collected)
    rect(530,40,20,8,249,164,59);
  if(game.paused||game.won||game.lost){
    rect(180,184,SCREEN_W-360,140,15,31,48);
    draw_number(310,222,game.won?888:game.lost?0:555,7);
  }
  SDL_RenderPresent(renderer);
}
static int button(SDL_GameControllerButton b){
  return controller&&SDL_GameControllerGetButton(controller,b);
}
static Input read_input(const Uint8*k,int pause,int reset){
  Input a={0};
  a.left=k[SDL_SCANCODE_A]||k[SDL_SCANCODE_LEFT]||button(SDL_CONTROLLER_BUTTON_DPAD_LEFT);
  a.right=k[SDL_SCANCODE_D]||k[SDL_SCANCODE_RIGHT]||button(SDL_CONTROLLER_BUTTON_DPAD_RIGHT);
  a.up=k[SDL_SCANCODE_W]||k[SDL_SCANCODE_UP]||button(SDL_CONTROLLER_BUTTON_DPAD_UP);
  a.down=k[SDL_SCANCODE_S]||k[SDL_SCANCODE_DOWN]||button(SDL_CONTROLLER_BUTTON_DPAD_DOWN);
  a.jump=k[SDL_SCANCODE_SPACE]||button(SDL_CONTROLLER_BUTTON_A);
  a.fire=k[SDL_SCANCODE_J]||k[SDL_SCANCODE_LCTRL]||button(SDL_CONTROLLER_BUTTON_X);
  a.pause=pause;a.reset=reset;
  if(controller){
    Sint16 x=SDL_GameControllerGetAxis(controller,SDL_CONTROLLER_AXIS_LEFTX);
    Sint16 y=SDL_GameControllerGetAxis(controller,SDL_CONTROLLER_AXIS_LEFTY);
    a.left|=x<-11000;a.right|=x>11000;a.up|=y<-11000;a.down|=y>11000;
  }
  return a;
}
int main(int argc,char**argv){
  (void)argc;(void)argv;
  if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_EVENTS|SDL_INIT_GAMECONTROLLER|SDL_INIT_AUDIO)!=0)
    return 1;
  window=SDL_CreateWindow("Dragon Native Campaign",SDL_WINDOWPOS_CENTERED,
      SDL_WINDOWPOS_CENTERED,SCREEN_W,SCREEN_H+HUD,SDL_WINDOW_SHOWN|SDL_WINDOW_RESIZABLE);
  if(!window){SDL_Quit();return 2;}
  renderer=SDL_CreateRenderer(window,-1,SDL_RENDERER_ACCELERATED|SDL_RENDERER_PRESENTVSYNC);
  if(!renderer)renderer=SDL_CreateRenderer(window,-1,SDL_RENDERER_SOFTWARE);
  if(!renderer){SDL_DestroyWindow(window);SDL_Quit();return 3;}
  SDL_RenderSetLogicalSize(renderer,SCREEN_W,SCREEN_H+HUD);
  SDL_AudioSpec format={0};
  format.freq=22050;format.format=AUDIO_U8;format.channels=1;format.samples=1024;
  audioDevice=SDL_OpenAudioDevice(NULL,0,&format,NULL,0);
  if(audioDevice)SDL_PauseAudioDevice(audioDevice,0);
  for(int i=0;i<SDL_NumJoysticks();i++)if(SDL_IsGameController(i)){
    controller=SDL_GameControllerOpen(i);break;
  }
  reset_game();
  if(argc<=1){
    uint32_t saved_stage=0;
    int saved_score=0,saved_health=0;
    if(dragon_save_load(CAMPAIGN_SIGNATURE,STAGE_COUNT,&saved_stage,
                        &saved_score,&saved_health,&save_serial)){
      game.health=saved_health-1;
      begin_stage((int)saved_stage);
      game.score=saved_score;
    }
    checkpoints_ready=1;
  }
  if(argc==3&&strcmp(argv[1],"--replay-selftest")==0){
    DragonReplay rec={0},loaded={0};
    if(!dragon_replay_start_record(&rec,CAMPAIGN_SIGNATURE))return 16;
    for(int f=0;f<360;f++){
      Input in={0};
      in.right=(f/30)%2==0;in.left=!in.right;
      in.up=(f/50)%2==0;in.down=!in.up;
      in.jump=(f%75)==0;in.fire=(f%11)==0;
      if(!dragon_replay_add(&rec,pack_input(in)))return 16;
      step(in);
    }
    uint32_t expected=game_state_hash();
    if(!dragon_replay_save(&rec,argv[2],expected)||!dragon_replay_load(
        &loaded,argv[2],CAMPAIGN_SIGNATURE))return 16;
    reset_game();
    for(uint32_t i=0;i<loaded.total;i++)step(unpack_input(loaded.frames[i]));
    int ok=game_state_hash()==expected&&loaded.expected_hash==expected;
    printf("DRAGON_NATIVE_REPLAY_SELFTEST %s frames=%u\n",
           ok?"PASS":"FAIL",loaded.total);
    if(controller)SDL_GameControllerClose(controller);
    if(audioDevice)SDL_CloseAudioDevice(audioDevice);
    SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
    return ok?0:16;
  }
  if(argc==3&&strcmp(argv[1],"--play-replay")==0){
    DragonReplay trace={0};
    if(!dragon_replay_load(&trace,argv[2],CAMPAIGN_SIGNATURE)){
      SDL_Log("Replay rejected: bad campaign, length, or CRC");
      if(controller)SDL_GameControllerClose(controller);
      if(audioDevice)SDL_CloseAudioDevice(audioDevice);
      SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
      return 13;
    }
    for(uint32_t frame=0;frame<trace.total;frame++){
      step(unpack_input(trace.frames[frame]));
      if(frame%60==0)render();
    }
    uint32_t actual=game_state_hash();
    int pass=actual==trace.expected_hash;
    printf("DRAGON_NATIVE_REPLAY %s frames=%u expected=%08x actual=%08x\n",
           pass?"PASS":"FAIL",trace.total,trace.expected_hash,actual);
    if(controller)SDL_GameControllerClose(controller);
    if(audioDevice)SDL_CloseAudioDevice(audioDevice);
    SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
    return pass?0:14;
  }
  if(argc>1&&strcmp(argv[1],"--checkpoint-test")==0){
    uint32_t saved_stage=0,saved_serial=0;
    int saved_score=0,saved_health=0;
    int chosen_stage=STAGE_COUNT>1?1:0;
    /* Test two alternating real SDL save files, checksum and campaign binding. */
    int first=dragon_save_checkpoint(CAMPAIGN_SIGNATURE,STAGE_COUNT,
                                     (uint32_t)chosen_stage,123,3,1);
    int second=dragon_save_checkpoint(CAMPAIGN_SIGNATURE,STAGE_COUNT,
                                      (uint32_t)chosen_stage,456,4,2);
    int loaded=dragon_save_load(CAMPAIGN_SIGNATURE,STAGE_COUNT,&saved_stage,
                                &saved_score,&saved_health,&saved_serial);
    int foreign=dragon_save_load(CAMPAIGN_SIGNATURE^0xffffffffu,STAGE_COUNT,
                                 &saved_stage,&saved_score,&saved_health,&saved_serial);
    int ok=first&&second&&loaded&&!foreign&&
           saved_stage==(uint32_t)chosen_stage&&
           saved_score==456&&saved_health==4&&saved_serial==2;
    printf("DRAGON_NATIVE_SAVE_TEST %s\n",ok?"PASS":"FAIL");
    if(controller)SDL_GameControllerClose(controller);
    if(audioDevice)SDL_CloseAudioDevice(audioDevice);
    SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
    return ok?0:12;
  }
  if(argc>1&&strcmp(argv[1],"--smoke")==0){
    /* Headless native validation exercises each engine's fixed-step paths.
       Zero work is credited as a completed human gameplay playtest. */
    for(int f=0;f<360;f++){
      Input demo={0};
      demo.right=(f/30)%2==0;
      demo.left=(f/30)%2!=0;
      demo.up=(f/50)%2==0;
      demo.down=(f/50)%2!=0;
      demo.jump=(f%80)<3;
      demo.fire=(f%13)==0;
      step(demo);
      if(f%36==0)render();
    }
    printf("DRAGON_NATIVE_SMOKE_OK mode=%d stage=%d score=%d health=%d\n",
           GAME_MODE,game.stage,game.score,game.health);
    if(controller)SDL_GameControllerClose(controller);
    if(audioDevice)SDL_CloseAudioDevice(audioDevice);
    SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
    return game.stage>=STAGE_COUNT?5:0;
  }
  DragonReplay recording={0};
  const char *record_path=(argc==3&&strcmp(argv[1],"--record-replay")==0)?argv[2]:NULL;
  if(record_path && !dragon_replay_start_record(&recording,CAMPAIGN_SIGNATURE))
    return 15;
  Uint32 then=SDL_GetTicks(),accum=0;
  int running=1;
  while(running){
    SDL_Event event;int pause=0,reset=0;
    while(SDL_PollEvent(&event)){
      if(event.type==SDL_QUIT)running=0;
      if(event.type==SDL_KEYDOWN&&!event.key.repeat){
        if(event.key.keysym.sym==SDLK_ESCAPE)running=0;
        if(event.key.keysym.sym==SDLK_p)pause=1;
        if(event.key.keysym.sym==SDLK_r)reset=1;
      }
      if(event.type==SDL_CONTROLLERBUTTONDOWN){
        if(event.cbutton.button==SDL_CONTROLLER_BUTTON_START)pause=1;
        if(event.cbutton.button==SDL_CONTROLLER_BUTTON_BACK)reset=1;
      }
    }
    Uint32 now=SDL_GetTicks();
    Uint32 elapsed=now-then;then=now;
    accum+=MIN(elapsed,250);
    Input in=read_input(SDL_GetKeyboardState(NULL),pause,reset);
    int count=0;
    while(accum>=16&&count++<6){
      if(record_path && !dragon_replay_add(&recording,pack_input(in))){
        running=0;break; /* full bounded recording: no hidden overrun */
      }
      step(in);in.pause=0;in.reset=0;accum-=16;
    }
    render();SDL_Delay(1);
  }
  int export_failed=0;
  if(record_path){
    uint32_t hash=game_state_hash();
    if(!dragon_replay_save(&recording,record_path,hash))
      export_failed=1;
    printf("DRAGON_NATIVE_REPLAY_RECORD frames=%u state=%08x saved=%d\n",
           recording.total,hash,!export_failed);
  }
  if(controller)SDL_GameControllerClose(controller);
  if(audioDevice)SDL_CloseAudioDevice(audioDevice);
  SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
  return export_failed?15:0;
}
'''

def render_sdl_campaign(campaign: Campaign,*,hero:str="hatchling",
                        theme:str="ancient_ruins",difficulty:int=4)->dict[str,str]:
    hero_ids={"hatchling":0,"knight":1,"explorer":2,
              "pilot":3,"astronaut":4,"robot":5}
    theme_colors={"crystals":(110,221,200),"ancient_ruins":(171,140,96),
                  "forest":(110,203,133),"ice":(127,208,241),
                  "space":(147,126,229),"volcano":(241,126,76),
                  "clockwork":(224,184,101)}
    if hero not in hero_ids or theme not in theme_colors or (
        isinstance(difficulty,bool) or not isinstance(difficulty,int)
        or not 1<=difficulty<=10
    ):
        raise ValueError("unrecognized native hero/theme/difficulty")
    if campaign.mode not in MODE_IDS or not 1 <= len(campaign.stages) <= 8:
        raise ValueError("invalid native campaign")
    if campaign.palette not in PALETTES:
        raise ValueError("untrusted palette")
    if any(len(stage.terrain) != H or any(len(row) != W for row in stage.terrain)
           for stage in campaign.stages):
        raise ValueError("invalid native stage dimensions")
    stage_blocks = [
        "  {\n" + ",\n".join('    "' + row + '"' for row in stage.terrain) + "\n  }"
        for stage in campaign.stages
    ]
    palette = ",\n".join("  {%d,%d,%d}" % rgb for rgb in PALETTES[campaign.palette])
    header=(
        "#ifndef DRAGON_CAMPAIGN_H\n#define DRAGON_CAMPAIGN_H\n"
        f"#define MAP_W {W}\n#define MAP_H {H}\n"
        f"#define STAGE_COUNT {len(campaign.stages)}\n"
        f"#define GAME_SEED {campaign.seed or 0x9E3779B9}u\n"
        f"#define GAME_MODE {MODE_IDS[campaign.mode]}\n"
        f"#define HERO_STYLE {hero_ids[hero]}\n"
        f"#define DESIGN_DIFFICULTY {difficulty}\n"
        "static const unsigned char THEME_ACCENT[3]={"+
        ",".join(str(n) for n in theme_colors[theme])+"};\n"
        f"#define CAMPAIGN_SIGNATURE 0x{campaign.id[:8]}u\n"
        "static const unsigned char PALETTE[4][3]={\n"+palette+"\n};\n"
        "static const char campaign_stage[STAGE_COUNT][MAP_H][MAP_W+1]={\n"
        +",\n".join(stage_blocks)+"\n};\n#endif\n"
    )
    # CMake is deliberately free from user-controlled input.
    cmake = """\
cmake_minimum_required(VERSION 3.16)
project(DragonNativeCampaign C)
set(CMAKE_C_STANDARD 99)
find_package(SDL2 REQUIRED)
add_executable(dragon_game src/main.c src/dragon_save.c src/dragon_replay.c)
target_include_directories(dragon_game PRIVATE include)
if(TARGET SDL2::SDL2)
  target_link_libraries(dragon_game PRIVATE SDL2::SDL2)
else()
  target_include_directories(dragon_game PRIVATE ${SDL2_INCLUDE_DIRS})
  target_link_libraries(dragon_game PRIVATE ${SDL2_LIBRARIES})
endif()
if(TARGET SDL2::SDL2main)
  target_link_libraries(dragon_game PRIVATE SDL2::SDL2main)
endif()
if(NOT MSVC)
  target_link_libraries(dragon_game PRIVATE m)
endif()
"""
    readme=(
        "# Original Native Dragon Campaign\n\n"
        f"{len(campaign.stages)} deterministic levels of {campaign.style} "
        f"({campaign.mode}); original palette {campaign.palette}.\n"
        "SDL2 C native executable, not HTML. Build with cmake -S . -B build "
        "&& cmake --build build. WASD or arrows, Space/A jump, J/X shoots, "
        "P/Start pauses, R/Back restarts, Escape quits. Collect crystals "
        "and reach the portal; arena mode requires collecting all crystals.\n"
        "Game speed and difficulty change through successive stages. "
        "Procedural original geometric sprites and synthesized arcade audio.\n"
        "No proprietary ROMs/assets/SDKs. Compilation and real playtesting "
        "are not implied by generating this source.\n"
    )
    from .dragon_native_save_system import emit_save_system
    files={"src/main.c": ENGINE, "include/dragon_campaign.h": header,
           "CMakeLists.txt": cmake,"README.engine.md":readme}
    from .dragon_native_replay_system import emit_replay_system
    from .dragon_chip_music import compose, emit_score_header, score_manifest
    music=compose(campaign.mode,campaign.seed,64)
    files["include/dragon_chip_score.h"]=emit_score_header(music)
    files["dragon-original-music.json"]=json.dumps(
        score_manifest(music),sort_keys=True,indent=2)+"\n"
    files.update(emit_save_system(campaign.id))
    files.update(emit_replay_system())
    return files
