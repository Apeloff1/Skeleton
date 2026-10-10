/* Host-only Sega hardware stand-in for testing the actual generated gameplay C.
 * This stub is NOT an emulator, executable cartridge, or release approval.
 * All game rules, maps, animation code and score updates remain unmodified.
 */
#ifndef SKELETON_SEGA8_HOST_SMSLIB_H
#define SKELETON_SEGA8_HOST_SMSLIB_H
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
#include <string.h>

#define __sfr volatile unsigned char
#define __at(address)
#define RGB(r,g,b) ((r)|((g)<<2)|((b)<<4))
#define PORT_A_KEY_UP 0x0001
#define PORT_A_KEY_DOWN 0x0002
#define PORT_A_KEY_LEFT 0x0004
#define PORT_A_KEY_RIGHT 0x0008
#define PORT_A_KEY_1 0x0010
#define PORT_A_KEY_2 0x0020
#define GG_KEY_START 0x8000
#define SMS_EMBED_SEGA_ROM_HEADER(product,revision) extern const unsigned char skeleton_host_signature_sentinel

static jmp_buf host_boot_return;
static unsigned char host_screen[24][32];
static unsigned long host_tile_writes;
static unsigned long host_sprite_updates;
static unsigned long host_sprite_objects;
static unsigned long host_palette_writes;
static int host_display_enabled;

static void SMS_displayOff(void) { host_display_enabled=0; }
static void SMS_displayOn(void) { host_display_enabled=1; }
static void SMS_loadTiles(const void *data,unsigned int offset,unsigned int size) {
    if (!data || offset!=0 || size<22U*32U || size>8192) abort();
}
static void SMS_useFirstHalfTilesforSprites(unsigned char yes) {
    if (yes!=1) abort();
}
static void SMS_setTileatXY(int x,int y,unsigned int tile) {
    if (x<0 || x>=32 || y<0 || y>=24 || tile>=22U) abort();
    host_screen[y][x]=(unsigned char)tile;
    ++host_tile_writes;
}
static void SMS_setBGPaletteColor(unsigned char index,unsigned char rgb) {
    if (index>=16 || rgb>=64) abort();
    ++host_palette_writes;
}
static void SMS_setSpritePaletteColor(unsigned char index,unsigned char rgb) {
    if (index>=16 || rgb>=64) abort();
    ++host_palette_writes;
}
static void GG_setBGPaletteColor(unsigned char index,unsigned int rgb) {
    if (index>=16 || rgb>0xFFF) abort();
    ++host_palette_writes;
}
static void GG_setSpritePaletteColor(unsigned char index,unsigned int rgb) {
    if (index>=16 || rgb>0xFFF) abort();
    ++host_palette_writes;
}
static void SMS_initSprites(void) { host_sprite_objects=0; }
static signed char SMS_addSprite(unsigned char x,unsigned char y,unsigned int tile) {
    (void)x; (void)y;
    if (tile>=22 || host_sprite_objects>=64) abort();
    ++host_sprite_objects;
    return 0;
}
static void SMS_copySpritestoSAT(void) { ++host_sprite_updates; }
static void SMS_waitForVBlank(void) { longjmp(host_boot_return,1); }
static unsigned int SMS_getKeysStatus(void) { return 0; }
static unsigned int SMS_getKeysPressed(void) { return 0; }
#endif
