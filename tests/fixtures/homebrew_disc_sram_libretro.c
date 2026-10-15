/* Original, intentionally tiny libretro C fixture for disc/SRAM ABI tests.
 * No commercial console, BIOS, ROM, copyrighted game or audio is embedded.
 * This binary is compiled only into an ephemeral test directory. */
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
struct disc_callbacks {
    bool (*set_eject_state)(bool);
    bool (*get_eject_state)(void);
    unsigned (*get_image_index)(void);
    bool (*set_image_index)(unsigned);
    unsigned (*get_num_images)(void);
    bool (*replace_image_index)(unsigned,const struct game_info*);
    bool (*add_image_index)(void);
};

static env_cb env;
static video_cb video;
static audio_cb audio;
static audio_batch_cb audio_batch;
static poll_cb poll;
static input_cb input;
static unsigned active_disc=0;
static bool ejected=false,loaded=false;
static uint32_t ticks=0;
static uint8_t save_ram[256];
static uint16_t pixels[32*24];
static int16_t samples[64*2];

static bool set_eject(bool value){ejected=value;return true;}
static bool get_eject(void){return ejected;}
static unsigned get_index(void){return ejected?UINT32_MAX:active_disc;}
static bool set_index(unsigned index){
    if(!ejected||index>=3)return false;
    active_disc=index;return true;
}
static unsigned image_count(void){return 3;}
static const struct disc_callbacks discs={
    set_eject,get_eject,get_index,set_index,image_count,NULL,NULL
};

unsigned retro_api_version(void){return 1;}
void retro_set_environment(env_cb cb){env=cb;}
void retro_set_video_refresh(video_cb cb){video=cb;}
void retro_set_audio_sample(audio_cb cb){audio=cb;}
void retro_set_audio_sample_batch(audio_batch_cb cb){audio_batch=cb;}
void retro_set_input_poll(poll_cb cb){poll=cb;}
void retro_set_input_state(input_cb cb){input=cb;}
void retro_get_system_info(struct system_info *out){
    *out=(struct system_info){"Skeleton original console smoke","1.0","bin",false,false};
}
void retro_get_system_av_info(struct av_info *out){
    *out=(struct av_info){{32,24,32,24,4.0f/3.0f},{60.0,16000.0}};
}
void retro_init(void){
    if(env){
        unsigned format=0;
        env(10,&format);
        unsigned version=0;
        if(env(57,&version)&&version>=1)
            env(58,(void*)&discs);
        else env(13,(void*)&discs);
    }
}
void retro_deinit(void){loaded=false;}
void retro_set_controller_port_device(unsigned port,unsigned dev){(void)port;(void)dev;}
bool retro_load_game(const struct game_info *game){
    static const unsigned char magic[]={'S','K','L','-','H','O','M','E','B','R','E','W'};
    if(!game||!game->data||game->size!=sizeof(magic)
       ||memcmp(game->data,magic,sizeof(magic))!=0)return false;
    ticks=0;active_disc=0;ejected=false;memset(save_ram,0,sizeof(save_ram));
    loaded=true;return true;
}
void retro_unload_game(void){loaded=false;}
void retro_reset(void){ticks=0;} /* SRAM deliberately survives reset */
void retro_run(void){
    if(!loaded)return;
    if(poll)poll();
    const unsigned pushed=(input&&input(0,1,0,8))?1u:0u;
    ++ticks;
    for(unsigned i=0;i<32u*24u;i++)
        pixels[i]=(uint16_t)(pushed?0x07e0u:((i+ticks+active_disc)&1u?0xf800u:0x001fu));
    if(video)video(pixels,32,24,64);
    for(unsigned i=0;i<64;i++){
        const int16_t wave=(int16_t)(((i+ticks+active_disc)%32u)*96u-1536);
        samples[i*2]=wave;samples[i*2+1]=(int16_t)-wave;
    }
    if(audio_batch)audio_batch(samples,64);
    else if(audio)for(unsigned i=0;i<64;i++)audio(samples[2*i],samples[2*i+1]);
}
size_t retro_serialize_size(void){return 8;}
bool retro_serialize(void *data,size_t size){
    if(!data||size!=8)return false;
    memcpy(data,&ticks,4);memcpy((unsigned char*)data+4,&active_disc,4);return true;
}
bool retro_unserialize(const void *data,size_t size){
    if(!data||size!=8)return false;
    memcpy(&ticks,data,4);memcpy(&active_disc,(const unsigned char*)data+4,4);
    return active_disc<3;
}
void *retro_get_memory_data(unsigned region){return region==0?save_ram:NULL;}
size_t retro_get_memory_size(unsigned region){return region==0?sizeof(save_ram):0;}
