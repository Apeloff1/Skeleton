/* Homebrew, deterministic libretro ABI qualification fixture.
 * No console firmware, commercial game, ROM or game logic is included. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef bool (*env_cb)(unsigned,void*);
typedef void (*video_cb)(const void*,unsigned,unsigned,size_t);
typedef void (*audio_cb)(int16_t,int16_t);
typedef size_t (*audio_batch_cb)(const int16_t*,size_t);
typedef void (*poll_cb)(void);
typedef int16_t (*input_cb)(unsigned,unsigned,unsigned,unsigned);

struct system_info {const char *name,*version,*ext;bool fullpath,block_extract;};
struct geometry {unsigned width,height,max_width,max_height;float aspect;};
struct timing {double fps,samplerate;};
struct av_info {struct geometry geometry;struct timing timing;};
struct game_info {const char *path;const void *data;size_t size;const char *meta;};
struct input_desc {unsigned port,device,index,id;const char *description;};

static env_cb env;
static video_cb video;
static audio_cb audio;
static audio_batch_cb audio_batch;
static poll_cb poll;
static input_cb input;
static uint32_t ticks,pressed;
static unsigned devices[4];
static uint8_t memory[256];
static uint16_t pixels[32*24];
static int16_t samples[64*2];
static bool loaded;

unsigned retro_api_version(void){return 1;}
void retro_set_environment(env_cb fn){env=fn;}
void retro_set_video_refresh(video_cb fn){video=fn;}
void retro_set_audio_sample(audio_cb fn){audio=fn;}
void retro_set_audio_sample_batch(audio_batch_cb fn){audio_batch=fn;}
void retro_set_input_poll(poll_cb fn){poll=fn;}
void retro_set_input_state(input_cb fn){input=fn;}
void retro_get_system_info(struct system_info *info){
    *info=(struct system_info){"Skeleton homebrew ABI fixture","1.0","bin",false,false};
}
void retro_get_system_av_info(struct av_info *info){
    *info=(struct av_info){{32,24,32,24,4.0f/3.0f},{60.0,16000.0}};
}
void retro_init(void){
    static const struct input_desc labels[]={
        {0,1,0,8,"Homebrew pulse"},
        {0,1,0,0,"Homebrew rest"},
        {0,0,0,0,NULL}
    };
    if(env){unsigned fmt=0;env(10,&fmt);env(11,(void*)labels);}
}
void retro_deinit(void){loaded=false;}
void retro_set_controller_port_device(unsigned port,unsigned device){
    if(port<4)devices[port]=device;
}
bool retro_load_game(const struct game_info *game){
    static const unsigned char magic[]={83,75,76,45,72,79,77,69,66,82,69,87};
    if(!game||!game->data||game->size!=sizeof(magic)||
       memcmp(game->data,magic,sizeof(magic))!=0)return false;
    ticks=pressed=0;memset(memory,0,sizeof(memory));loaded=true;return true;
}
void retro_unload_game(void){loaded=false;}
void retro_reset(void){ticks=pressed=0;memset(memory,0,sizeof(memory));}
void retro_run(void){
    if(!loaded)return;
    if(poll)poll();
    pressed=(input && input(0,1,0,8))?1u:0u;
    ++ticks;memory[0]=(uint8_t)ticks;memory[1]=(uint8_t)pressed;
    for(unsigned i=0;i<32u*24u;i++){
        unsigned x=i%32u;
        pixels[i]=(uint16_t)(pressed?0x07e0u:((x+ticks)&1u?0xf800u:0x001fu));
    }
    if(video)video(pixels,32,24,32*sizeof(uint16_t));
    for(unsigned i=0;i<64;i++){
        int16_t wave=(int16_t)(((i+ticks*3u)%32u)*96u-1536);
        samples[2*i]=wave;samples[2*i+1]=(int16_t)-wave;
    }
    if(audio_batch)audio_batch(samples,64);
    else if(audio)for(unsigned i=0;i<64;i++)audio(samples[2*i],samples[2*i+1]);
}
size_t retro_serialize_size(void){return sizeof(ticks)+sizeof(pressed);}
bool retro_serialize(void *data,size_t size){
    if(!data||size!=retro_serialize_size())return false;
    memcpy(data,&ticks,4);memcpy((unsigned char*)data+4,&pressed,4);return true;
}
bool retro_unserialize(const void *data,size_t size){
    if(!data||size!=retro_serialize_size())return false;
    memcpy(&ticks,data,4);memcpy(&pressed,(const unsigned char*)data+4,4);return true;
}
void *retro_get_memory_data(unsigned region){return region==0?memory:NULL;}
size_t retro_get_memory_size(unsigned region){return region==0?sizeof(memory):0;}
