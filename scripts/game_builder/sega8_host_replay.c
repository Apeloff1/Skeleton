/* Compiles the *actual exported Sega game.c* into a host test binary.
 * Redirection of SMSlib I/O is the only difference from the cartridge build.
 * Not a Z80 CPU emulator or hardware playback certificate.
 */
#include "SMSlib.h"
#define main skeleton_sega_native_entry
#include "game-host.c"
#undef main

static void emit_state(void) {
    if (level_index>=LEVEL_COUNT || hero_x>=WIDTH || hero_y>=HEIGHT) abort();
    if (pending_count!=0) abort();
    if (host_screen[TOP+hero_y][LEFT+hero_x]!=HERO
        && host_screen[TOP+hero_y][LEFT+hero_x]!=HERO_ALT) abort();
    if (host_screen[HUD_Y][LEFT+12] != (unsigned char)(DIGIT_BASE+bond_rank))
        abort();
    if (host_screen[HUD_Y][LEFT+13] != (unsigned char)(DIGIT_BASE+(score/1000)%10))
        abort();
    if (host_screen[HUD_Y][LEFT+14] != (unsigned char)(DIGIT_BASE+(score/100)%10))
        abort();
    if (host_screen[HUD_Y][LEFT+15] != (unsigned char)(DIGIT_BASE+(score/10)%10))
        abort();
    if (host_screen[HUD_Y][LEFT+16] != (unsigned char)(DIGIT_BASE+score%10))
        abort();
    printf("S %u %u %u %u %u %u %u %u %u\n",
        (unsigned int)level_index,(unsigned int)hero_x,(unsigned int)hero_y,
        (unsigned int)health,(unsigned int)score,(unsigned int)gems_left,
        (unsigned int)won,(unsigned int)lost,(unsigned int)bond_rank);
}
int main(void) {
    char action;
    unsigned int frame_count=0;
    if (setjmp(host_boot_return)==0) skeleton_sega_native_entry();
    if (!host_display_enabled || host_palette_writes!=8) abort();
    emit_state();
    while (scanf(" %c",&action)==1) {
        if (++frame_count>20000U || won || lost) abort();
        switch (action) {
            case 'U': advance(0,-1); break;
            case 'D': advance(0,1); break;
            case 'L': advance(-1,0); break;
            case 'R': advance(1,0); break;
            default: abort();
        }
        while (pending_count) flush_pending();
        render_following_sprite();
        emit_state();
    }
    if (!won || lost || host_sprite_updates!=frame_count || host_tile_writes==0)
        abort();
    fprintf(stderr,"host_replay_validated_steps=%u tile_writes=%lu sprites=%lu\n",
        frame_count,host_tile_writes,host_sprite_updates);
    return 0;
}
