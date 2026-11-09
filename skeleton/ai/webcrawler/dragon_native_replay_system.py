"""Offline, bounded native gameplay replay source generator for SDL2.

Records controller actions per fixed simulation tick, never personal audio/video
or user account data. File header is campaign-bound, versioned and checksumed;
playback additionally compares the final integer gameplay state digest.
These are reproducibility receipts, not qualitative acceptance/XP evidence.
"""
from __future__ import annotations

HEADER=r"""#ifndef DRAGON_NATIVE_REPLAY_H
#define DRAGON_NATIVE_REPLAY_H
#include <stdint.h>
enum {
  DRAGON_INPUT_LEFT=1,DRAGON_INPUT_RIGHT=2,DRAGON_INPUT_UP=4,
  DRAGON_INPUT_DOWN=8,DRAGON_INPUT_JUMP=16,DRAGON_INPUT_FIRE=32,
  DRAGON_INPUT_PAUSE=64,DRAGON_INPUT_RESET=128
};
#define DRAGON_REPLAY_MAX_TICKS 7200
typedef struct {
  uint16_t frames[DRAGON_REPLAY_MAX_TICKS];
  uint32_t total, expected_hash, campaign_signature;
  int loaded, recording;
} DragonReplay;
int dragon_replay_start_record(DragonReplay*session,uint32_t signature);
int dragon_replay_add(DragonReplay*session,uint16_t buttons);
int dragon_replay_save(DragonReplay*session,const char*path,uint32_t state_hash);
int dragon_replay_load(DragonReplay*session,const char*path,uint32_t signature);
uint32_t dragon_replay_digest(const uint32_t*words,int count);
#endif
"""
SOURCE=r'''/* Original Dragon Replay v1. LE 24-byte header + 2 bytes per 60Hz tick.
   Replays preserve explicit controller events, not nondeterministic wall time.
   Files are bounded to 7200 frames and bound to exact campaign build.
   CRC32 defends against accidental corruption, not malicious tampering.
*/
#include "dragon_replay.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#define HEADER_SIZE 24
static void wr32(uint8_t*p,uint32_t n){
    p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);
    p[2]=(uint8_t)(n>>16);p[3]=(uint8_t)(n>>24);
}
static uint32_t rd32(const uint8_t*p){
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|
           ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint32_t crc32(const uint8_t*p,size_t n){
    uint32_t r=0xffffffffu;
    for(size_t i=0;i<n;i++){
        r^=p[i];
        for(int k=0;k<8;k++)r=(r>>1)^((r&1)?0xedb88320u:0);
    }
    return ~r;
}
uint32_t dragon_replay_digest(const uint32_t*words,int count){
    uint32_t h=2166136261u;
    if(!words||count<0||count>64)return 0;
    for(int i=0;i<count;i++){
        uint32_t v=words[i];
        for(int k=0;k<4;k++){
            h^=(uint8_t)(v>>(k*8));
            h*=16777619u;
        }
    }
    return h;
}
int dragon_replay_start_record(DragonReplay*session,uint32_t signature){
    if(!session)return 0;
    memset(session,0,sizeof(*session));
    session->campaign_signature=signature;session->recording=1;
    return 1;
}
int dragon_replay_add(DragonReplay*session,uint16_t buttons){
    if(!session||!session->recording||
       session->total>=DRAGON_REPLAY_MAX_TICKS)return 0;
    session->frames[session->total++]=(uint16_t)(buttons&0xFF);
    return 1;
}
int dragon_replay_save(DragonReplay*session,const char*path,uint32_t hash){
    if(!session||!session->recording||session->total<1||!path)return 0;
    size_t bytes=(size_t)session->total*2;
    uint8_t payload[DRAGON_REPLAY_MAX_TICKS*2];
    for(uint32_t i=0;i<session->total;i++){
        payload[i*2]=(uint8_t)session->frames[i];
        payload[i*2+1]=(uint8_t)(session->frames[i]>>8);
    }
    uint8_t header[HEADER_SIZE]={0};
    memcpy(header,"DRPL",4);
    wr32(header+4,1);wr32(header+8,session->campaign_signature);
    wr32(header+12,session->total);
    wr32(header+16,crc32(payload,bytes));
    wr32(header+20,hash);
    FILE*f=fopen(path,"wb");
    if(!f)return 0;
    int success=fwrite(header,1,HEADER_SIZE,f)==HEADER_SIZE&&
                fwrite(payload,1,bytes,f)==bytes;
    if(fclose(f)!=0)success=0;
    session->recording=0;
    return success;
}
int dragon_replay_load(DragonReplay*session,const char*path,uint32_t signature){
    if(!session||!path)return 0;
    memset(session,0,sizeof(*session));
    FILE*f=fopen(path,"rb");
    if(!f)return 0;
    uint8_t header[HEADER_SIZE];
    int ok=fread(header,1,HEADER_SIZE,f)==HEADER_SIZE;
    if(!ok||memcmp(header,"DRPL",4)||rd32(header+4)!=1||
       rd32(header+8)!=signature){fclose(f);return 0;}
    uint32_t total=rd32(header+12);
    if(total<1||total>DRAGON_REPLAY_MAX_TICKS){fclose(f);return 0;}
    size_t size=(size_t)total*2;
    uint8_t payload[DRAGON_REPLAY_MAX_TICKS*2];
    if(fread(payload,1,size,f)!=size||fgetc(f)!=EOF){
        fclose(f);return 0;
    }
    fclose(f);
    if(crc32(payload,size)!=rd32(header+16))return 0;
    session->campaign_signature=signature;
    session->total=total;
    session->expected_hash=rd32(header+20);
    for(uint32_t i=0;i<total;i++)
        session->frames[i]=(uint16_t)payload[i*2]|
                          (uint16_t)((uint16_t)payload[i*2+1]<<8);
    session->loaded=1;return 1;
}
'''

def emit_replay_system()->dict[str,str]:
    return {"include/dragon_replay.h":HEADER,"src/dragon_replay.c":SOURCE}
