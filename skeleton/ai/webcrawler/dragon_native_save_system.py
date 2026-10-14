"""Crash-resistant two-slot native SDL2 checkpoint system for generated games.

This module produces original C source. Each checkpoint is bound to the exact
campaign SHA fingerprint, has explicit little-endian fields and CRC-32,
records only stable stage-entry progress, and alternates A/B slots so an
interrupted write cannot destroy the previous valid checkpoint. No JSON,
browser, external service, or platform credential is involved.
"""
from __future__ import annotations

HEADER=r"""#ifndef DRAGON_NATIVE_SAVE_H
#define DRAGON_NATIVE_SAVE_H
#include <stdint.h>
int dragon_save_load(uint32_t campaign_signature, int stage_count,
                     uint32_t *stage, int *score, int *health,
                     uint32_t *serial);
int dragon_save_checkpoint(uint32_t campaign_signature, int stage_count,
                           uint32_t stage, int score, int health,
                           uint32_t serial);
#endif
"""
SOURCE=r'''/* Dragon Native Save v1. 36-byte portable records, CRC-32, 2 slots.
     A corrupt or partial save is ignored; old campaigns cannot be loaded.
     Files are written only at a campaign stage boundary, not during play. */
#include "dragon_save.h"
#include <SDL.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define RECORD_BYTES 36
#define VERSION 1
typedef struct {
    uint32_t serial, stage, score, health;
    int valid;
} SaveRecord;

static uint32_t rd32(const uint8_t*p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|
           ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void wr32(uint8_t*p,uint32_t value) {
    p[0]=(uint8_t)value;p[1]=(uint8_t)(value>>8);
    p[2]=(uint8_t)(value>>16);p[3]=(uint8_t)(value>>24);
}
static uint32_t crc32(const uint8_t*data,int length) {
    uint32_t crc=0xffffffffu;
    for(int i=0;i<length;i++){
        crc^=(uint32_t)data[i];
        for(int j=0;j<8;j++)crc=(crc>>1)^((crc&1)?0xedb88320u:0u);
    }
    return ~crc;
}
static int file_path(char*dest,size_t capacity,const char*slot) {
    char*dir=SDL_GetPrefPath("Skeleton","DragonNativeGame");
    if(!dir)return 0;
    size_t len=strlen(dir),tail=strlen(slot);
    int ok=len+tail+1<=capacity;
    if(ok){memcpy(dest,dir,len);memcpy(dest+len,slot,tail+1);}
    SDL_free(dir);return ok;
}
static SaveRecord read_slot(const char*slot,uint32_t signature,int total) {
    SaveRecord result={0};
    char path[1024];uint8_t bytes[RECORD_BYTES];
    if(!file_path(path,sizeof(path),slot))return result;
    SDL_RWops*f=SDL_RWFromFile(path,"rb");
    if(!f)return result;
    size_t n=SDL_RWread(f,bytes,1,RECORD_BYTES);
    Sint64 size=SDL_RWsize(f);
    SDL_RWclose(f);
    if(n!=RECORD_BYTES||size!=RECORD_BYTES)return result;
    if(memcmp(bytes,"DRGN",4)!=0||
       rd32(bytes+4)!=VERSION||rd32(bytes+8)!=signature||
       rd32(bytes+32)!=crc32(bytes,32))return result;
    result.serial=rd32(bytes+12);result.stage=rd32(bytes+16);
    result.score=rd32(bytes+20);result.health=rd32(bytes+24);
    if(result.serial==0||result.stage>=(uint32_t)total||
       result.score>9999999||result.health<1||result.health>6)return result;
    if(rd32(bytes+28)!=0)return result;
    result.valid=1;return result;
}
int dragon_save_load(uint32_t signature,int stage_count,uint32_t*stage,
                     int*score,int*health,uint32_t*serial){
    if(stage_count<1||stage_count>8||!stage||!score||!health||!serial)return 0;
    SaveRecord a=read_slot("save-a.dat",signature,stage_count);
    SaveRecord b=read_slot("save-b.dat",signature,stage_count);
    if(!a.valid&&!b.valid)return 0;
    SaveRecord best=!a.valid?b:(!b.valid?a:(b.serial>a.serial?b:a));
    *stage=best.stage;*score=(int)best.score;*health=(int)best.health;
    *serial=best.serial;
    return 1;
}
int dragon_save_checkpoint(uint32_t signature,int stage_count,uint32_t stage,
                           int score,int health,uint32_t serial){
    if(stage_count<1||stage_count>8||stage>=(uint32_t)stage_count||
       score<0||score>9999999||health<1||health>6||serial==0)return 0;
    uint8_t bytes[RECORD_BYTES]={0};
    memcpy(bytes,"DRGN",4);
    wr32(bytes+4,VERSION);wr32(bytes+8,signature);
    wr32(bytes+12,serial);wr32(bytes+16,stage);
    wr32(bytes+20,(uint32_t)score);wr32(bytes+24,(uint32_t)health);
    wr32(bytes+28,0);wr32(bytes+32,crc32(bytes,32));
    char path[1024];
    /* Alternation: failed write can only damage one slot. */
    if(!file_path(path,sizeof(path),(serial&1)?"save-a.dat":"save-b.dat"))
        return 0;
    SDL_RWops*f=SDL_RWFromFile(path,"wb");
    if(!f)return 0;
    size_t n=SDL_RWwrite(f,bytes,1,RECORD_BYTES);
    SDL_RWclose(f);
    return n==RECORD_BYTES;
}
'''

def emit_save_system(campaign_id:str)->dict[str,str]:
    if not isinstance(campaign_id,str) or len(campaign_id)!=64 or any(
        c not in "0123456789abcdef" for c in campaign_id):
        raise ValueError("canonical campaign SHA256 required")
    return {"include/dragon_save.h":HEADER,"src/dragon_save.c":SOURCE}
