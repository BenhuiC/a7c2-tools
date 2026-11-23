/* Invocation-only fixed command; stdin contains data, never file offsets. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>
struct api_guard {unsigned offset,size;const unsigned char *bytes;};
#include CAMERA_CONFIG
#ifndef API_FULL_NATIVE
#define API_FULL_NATIVE 0
#endif
#ifndef API_MENU_ICONS
#define API_MENU_ICONS 0
#endif
#ifndef API_FIXED_BANK
#define API_FIXED_BANK 0
#endif
#if API_FIXED_BANK
static int fixed_commit_started,fixed_task_done;
#endif

static const char *root="",*error="io";
static const char *mounts[]={"/setting","/cp","/usr"};
static int remounted[3];
static unsigned long mount_flags[3];
static int bad(const char *why){error=why;return -1;}
static int protect_transaction(void){
    struct sigaction action={.sa_handler=SIG_IGN};sigemptyset(&action.sa_mask);
    if(sigaction(SIGHUP,&action,NULL)||sigaction(SIGTERM,&action,NULL)||sigaction(SIGPIPE,&action,NULL))
        return bad("transaction-signal-setup");
    return 0;
}
static void path(char *out,size_t size,const char *suffix){snprintf(out,size,"%s%s",root,suffix);}
static uint32_t get32(const unsigned char *p){return p[0]|p[1]<<8|p[2]<<16|(uint32_t)p[3]<<24;}
static int get16(const unsigned char *p){return (int16_t)(p[0]|p[1]<<8);}
static void put32(unsigned char *p,uint32_t v){for(int i=0;i<4;i++)p[i]=(unsigned char)(v>>(8*i));}
static int transfer(int fd,void *data,size_t size,off_t at,int writing) {
    unsigned char *p=data;
    while(size){ssize_t n=writing?pwrite(fd,p,size,at):pread(fd,p,size,at);if(n<0&&errno==EINTR)continue;if(n<=0)return bad(writing?"write":"read");p+=n;size-=n;at+=n;}return 0;
}
#include "look_undo.h"
static int replace_bytes(int fd,off_t at,const void *data,size_t size) {
    if(undo_record(fd,at,size))return -1;
    unsigned char check[1024];if(transfer(fd,(void*)data,size,at,1)||fsync(fd))return bad("write");
    const unsigned char *p=data;
    while(size){size_t n=size<sizeof(check)?size:sizeof(check);if(transfer(fd,check,n,at,0)||memcmp(check,p,n))return bad("readback");size-=n;p+=n;at+=n;}
#ifdef CAMERA_API_TEST
    const char *signal_at=getenv("A7C2_API_SIGNAL_AT");
    if(signal_at&&strtoul(signal_at,NULL,10)==undo_count){raise(SIGHUP);raise(SIGTERM);}
#endif
    return 0;
}
static int writable(int index) {
    char p[640];path(p,sizeof(p),mounts[index]);struct statvfs s;
    if(statvfs(p,&s))return bad("mount-info");
    if(s.f_flag&ST_RDONLY){
        unsigned long flags=0;
#define KEEP_FLAG(name) if(s.f_flag&ST_##name)flags|=MS_##name
        KEEP_FLAG(NOSUID);KEEP_FLAG(NODEV);KEEP_FLAG(NOEXEC);KEEP_FLAG(SYNCHRONOUS);
        KEEP_FLAG(MANDLOCK);KEEP_FLAG(NOATIME);KEEP_FLAG(NODIRATIME);KEEP_FLAG(RELATIME);
#undef KEEP_FLAG
        mount_flags[index]=flags;
        if(mount(NULL,p,NULL,MS_REMOUNT|flags,NULL))return bad("mount-rw");remounted[index]=1;
    }return 0;
}
static int restore_mounts(void) {
    int result=0;for(int i=2;i>=0;i--)if(remounted[i]){char p[640];path(p,sizeof(p),mounts[i]);if(mount(NULL,p,NULL,MS_REMOUNT|MS_RDONLY|mount_flags[i],NULL))result=bad("mount-ro");else remounted[i]=0;}return result;
}
static int input(unsigned char *out,size_t capacity,size_t *size) {
    *size=0;while(*size<capacity){ssize_t n=read(0,out+*size,capacity-*size);if(n<0&&errno==EINTR)continue;if(n<0)return bad("input");if(!n)return 0;*size+=n;}
    unsigned char extra;ssize_t n;do{n=read(0,&extra,1);}while(n<0&&errno==EINTR);return n?bad("input-size"):0;
}
static int boot_id(char *id) {
    char p[640];path(p,sizeof(p),"/proc/sys/kernel/random/boot_id");FILE *f=fopen(p,"r");if(!f)return bad("boot-id");
    int ok=fgets(id,40,f)!=NULL;fclose(f);if(!ok)return bad("boot-id");id[strcspn(id,"\r\n")]=0;return 0;
}
static int save_state(const char *state,const char *operation) {
    char p[640],to[640],id[40];if(boot_id(id))return -1;
    path(p,sizeof(p),"/setting/a7c2-api.task.new");path(to,sizeof(to),"/setting/a7c2-api.task");
    FILE *f=fopen(p,"w");if(!f)return bad("task-write");int ok=fprintf(f,"%s %s %s\n",state,id,operation)>=0;
    if(fflush(f)||fsync(fileno(f)))ok=0;if(fclose(f))ok=0;if(!ok||rename(p,to))return bad("task-write");
#if API_FIXED_BANK
    char parent[640];path(parent,sizeof parent,"/setting");int directory=open(parent,O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    if(directory<0)return bad("task-directory");int synced=fsync(directory);if(close(directory))synced=-1;
    if(synced)return bad("task-sync");
#endif
    return 0;
}
static int read_state(char *state,char *id,char *operation) {
    char p[640];path(p,sizeof(p),"/setting/a7c2-api.task");FILE *f=fopen(p,"r");if(!f){if(errno==ENOENT)return 0;return bad("task-read");}
    int n=fscanf(f,"%31s %39s %31s",state,id,operation);fclose(f);return n==3?1:bad("task-read");
}
static int state_snapshot(char *state,char *op,int *restarted) {
    char saved[40],current[40],lock[640];int n=read_state(state,saved,op);if(n<0)return -1;
    *restarted=0;
    if(!n){strcpy(state,"idle");op[0]=0;}
    else {if(boot_id(current))return -1;*restarted=strcmp(saved,current)!=0;
        if(!strcmp(state,"pending_reload")&&*restarted)strcpy(state,"active");}
    path(lock,sizeof lock,"/tmp_wbshd/a7c2-resource-update.lock");
    if(!access(lock,F_OK)){if(strcmp(state,"failed"))strcpy(state,"running");}
    else if(!strcmp(state,"running"))strcpy(state,"failed");
    return 0;
}
static int task(void) {
    char state[32],op[32];int restarted;if(state_snapshot(state,op,&restarted))return -1;
    if(!op[0]){printf("{\"state\":\"%s\"}\n",state);return 0;}
    /* A new Linux boot identity is only an observation, not CP/cache proof. */
    printf("{\"state\":\"%s\",\"operation\":\"%s\"",state,op);
    if(!strcmp(op,"look"))printf(",\"restart_method\":\"battery_removal\",\"runtime_verified\":false,\"restart_observed\":%s",restarted?"true":"false");
    puts("}");return 0;
}
static int ready(int look) {
    char state[32],saved[40],op[32],current[40];int n=read_state(state,saved,op);if(n<0)return -1;if(!n)return 0;
    if(!strcmp(state,"running")||!strcmp(state,"failed"))return bad("previous-result-unknown");if(boot_id(current))return -1;
    if(!look&&!strcmp(state,"pending_reload")&&!strcmp(saved,current))return bad("pending-reload");return 0;
}
static int name_file(const char *filename,int slot,const char *name,int writing) {
    char p[640];snprintf(p,sizeof(p),"%s/usr/share/app/%s",root,filename);int fd=open(p,writing?O_RDWR:O_RDONLY);
    if(fd<0)return bad("name-open");int result=-1;unsigned char header[16],pointer[2],tag[4];struct stat s;
    if(transfer(fd,header,16,0,0)||fstat(fd,&s))goto done;
    unsigned count=get32(header+12)&0x1fff;off_t base=(16+count*2+3)&~3;
    if(memcmp(header,"uxc\7\0\0\0\0",8)||header[8]!=8||header[9]||header[10]!=5||header[11]||count!=2866||s.st_size%4||s.st_size<base){bad("name-layout");goto done;}
    unsigned rid=label_ids[slot-1];off_t index=16+2*((rid&0xffffff)-0xa000);
    if(transfer(fd,pointer,2,index,0)||transfer(fd,tag,4,base+4*(pointer[0]|pointer[1]<<8),0))goto done;
    if(get32(tag)!=(0x1e000000|(rid&0xffffff))){bad("name-layout");goto done;}
    off_t text=base+4*(pointer[0]|pointer[1]<<8)+4;
    if(text<0||text>s.st_size){bad("name-layout");goto done;}
    unsigned char existing[64]={0};size_t available=(size_t)(s.st_size-text);
    if(available>sizeof existing)available=sizeof existing;
    if(available&&transfer(fd,existing,available,text,0))goto done;
    unsigned char *end=memchr(existing,0,available);
    if(end&&(size_t)(end-existing)==strlen(name)&&!memcmp(existing,name,strlen(name))){result=0;goto done;}
    unsigned next=(s.st_size-base)/4;if(next>=65535){bad("name-space");goto done;}
    if(writing){
        unsigned char record[72]={0};put32(record,0x1e000000|(rid&0xffffff));memcpy(record+4,name,strlen(name));size_t size=(4+strlen(name)+1+3)&~3;
        pointer[0]=next&255;pointer[1]=next>>8;
        if(replace_bytes(fd,s.st_size,record,size)||replace_bytes(fd,index,pointer,2))goto done;
    }
    result=0;
done:close(fd);return result;
}
static int cp_open(void){char p[640];path(p,sizeof(p),"/cp/cpapp-b.bin");return open(p,O_RDWR);}
#include "full_look.h"
#include "fixed_look.h"
#include "look_icons.h"
#include "look_readback.h"
static int check_file(const char *suffix,unsigned expected,const struct api_guard *guards,size_t count) {
    char p[640];path(p,sizeof(p),suffix);int fd=open(p,O_RDONLY);if(fd<0)return bad("layout-open");
    struct stat s;unsigned char data[256];int result=-1;
    if(fstat(fd,&s)||s.st_size!=expected){bad("layout-size");goto done;}
    for(size_t i=0;i<count;i++)for(unsigned at=0;at<guards[i].size;){
        unsigned n=guards[i].size-at;if(n>sizeof(data))n=sizeof(data);
        if(transfer(fd,data,n,guards[i].offset+at,0))goto done;
        if(memcmp(data,guards[i].bytes+at,n)){bad("layout-conflict");goto done;}at+=n;
    }result=0;
done:close(fd);return result;
}
static int space_for(int index,unsigned bytes,unsigned blocks,unsigned files) {
    char p[640];path(p,sizeof(p),mounts[index]);struct statvfs s;if(statvfs(p,&s))return bad("mount-info");
    blocks+=(bytes+s.f_frsize-1)/s.f_frsize;
    if(s.f_bavail<blocks||(s.f_files&&s.f_favail<files))return bad("no-space");return 0;
}
static int install_look(int slot,const char *name,const unsigned char *data,size_t input_size) {
#if API_FIXED_BANK
    if(writable(1)||writable(2)||fixed_install(slot))return -1;
    for(unsigned i=0;i<name_count;i++)if(name_file(name_files[i],slot,name,1))return -1;
    return 0;
#else

    if(writable(1)||writable(2))return -1;int fd=cp_open();if(fd<0)return bad("cp-open");int result=-1;
#if API_FULL_NATIVE
    unsigned char *prepared=NULL,gamma_table[62*28],full_mask[4];
#endif
    unsigned char header[8],sum[4],mask[4];if(transfer(fd,header,8,table_offset,0))goto done;
    if(get32(header)!=table_magic||get32(header+4)!=table_layout){bad("table-layout");goto done;}
    const unsigned char *grid=data;
#if API_FULL_NATIVE
    if(full_prepare(fd,slot,data,input_size,&prepared,gamma_table,full_mask))goto done;
    if(full_frame(data,input_size))grid=data+8;
#endif
    uint32_t value=2166136261U;for(int i=0;i<1215;i++)value=(value^grid[i])*16777619U;put32(sum,value);
    if(replace_bytes(fd,table_offset+32+(slot-1)*1215,grid,1215)||replace_bytes(fd,table_offset+8+(slot-1)*4,sum,4))goto done;
#if API_FULL_NATIVE
    if(replace_bytes(fd,F_PREFIX,prepared,F_CAPACITY)||replace_bytes(fd,F_TABLE,gamma_table,sizeof(gamma_table))||replace_bytes(fd,F_MASK,full_mask,4))goto done;
#else
    if(photo_available){
        if(transfer(fd,mask,4,photo_mask_offset,0))goto done;value=get32(mask);
        value=data[1215]?value|(1U<<(slot-1)):value&~(1U<<(slot-1));put32(mask,value);
        if(replace_bytes(fd,photo_params_offset+(slot-1)*108,data+1216,108)||replace_bytes(fd,photo_mask_offset,mask,4))goto done;
    }
#endif
    for(unsigned i=0;i<name_count;i++)if(name_file(name_files[i],slot,name,1))goto done;result=0;
done:
#if API_FULL_NATIVE
    free(prepared);
#endif
    close(fd);return result;

#endif
}
static int sound_current(int fd) {
    unsigned char table[5],gate[SOUND_GATE_SIZE],front[2],mechanical[2],variant[4];
    if(transfer(fd,table,5,sound_table_offset,0)||transfer(fd,gate,sizeof(gate),sound_gate_offset,0)
       ||transfer(fd,front,2,sound_front_offset,0)||transfer(fd,mechanical,2,sound_mechanical_offset,0)
       ||transfer(fd,variant,4,sound_variant_offset,0))return -1;
    if(memcmp(variant,sound_variant_before,4)&&memcmp(variant,sound_variant_after,4))return bad("sound-layout");
    if((memcmp(front,sound_front,2)&&memcmp(front,sound_front_before,2))||
       (memcmp(mechanical,sound_mechanical,2)&&memcmp(mechanical,sound_mechanical_before,2)))return bad("sound-layout");
    for(unsigned i=0;i<sound_states;i++)if(!memcmp(table,sound_tables[i],5)&&!memcmp(gate,sound_gates[i],sizeof(gate)))return sound_flags[i];return bad("sound-layout");
}
static int sound_shutdown_fix(int apply) {
    char p[640];unsigned char code[64];path(p,sizeof p,"/usr/lib/appFw.so");
    if(apply&&writable(2))return -1;
    int fd=open(p,apply?O_RDWR|O_NOFOLLOW:O_RDONLY|O_NOFOLLOW);
    if(fd<0)return bad("ap-open");int result=-1;
    for(unsigned i=0;i<sizeof(sound_lifecycle_edits)/sizeof(sound_lifecycle_edits[0]);i++){
        const struct sound_ap_edit *e=&sound_lifecycle_edits[i];
        if(e->size>sizeof code||transfer(fd,code,e->size,e->offset,0))goto done;
        if(!memcmp(code,e->after,e->size))continue;
        if(memcmp(code,e->before,e->size)&&(!e->previous||memcmp(code,e->previous,e->size))){bad("sound-shutdown-layout");goto done;}
        if(apply&&replace_bytes(fd,e->offset,e->after,e->size))goto done;
    }
    result=0;
done:close(fd);return result;
}
static int sound_switch(int selection,int enabled) {
    if(writable(1))return -1;int fd=cp_open();if(fd<0)return bad("cp-open");int result=-1,current=sound_current(fd);if(current<0)goto done;
    int next=enabled?(current|selection):(current&~selection);
    if(next==current){result=0;goto done;}
    if(replace_bytes(fd,sound_table_offset,sound_tables[next],5)||replace_bytes(fd,sound_gate_offset,sound_gates[next],SOUND_GATE_SIZE)
       ||replace_bytes(fd,sound_front_offset,sound_front,2)||replace_bytes(fd,sound_mechanical_offset,sound_mechanical,2))goto done;result=0;
done:close(fd);return result;
}
struct audio_row {unsigned present,file,size,offset;};
#define AUDIO_ROWS 15
static int audio_kind(unsigned kind){return (kind>=1&&kind<=3)||(kind>=10&&kind<=15);}
static void mechanical_variants(struct audio_row *rows){
    if(!rows[0].present)return;
    for(unsigned kind=10;kind<=15;kind++)rows[kind-1]=rows[kind<=12?1:0];
}
static int audio_config(struct audio_row *rows) {
    char p[640],line[512];path(p,sizeof(p),"/usr/share/avsystemsound/custom.txt");FILE *f=fopen(p,"r");if(!f)return errno==ENOENT?0:bad("audio-config");
    while(fgets(line,sizeof(line),f)) {
        if(strncmp(line,"CUSTOM,",7))continue;unsigned kind,size,offset;char name[64];
        if(sscanf(line,"CUSTOM,0x%X,APP,%63[^,],0x%X,0x%X,",&kind,name,&size,&offset)!=4||!audio_kind(kind)||!size||size>51200||offset>51200-size||size%64||offset%64){fclose(f);return bad("audio-config");}
        unsigned file;for(file=0;file<3;file++)if(!strcmp(name,audio_names[file]))break;
        if(file==3||rows[kind-1].present){fclose(f);return bad("audio-config");}rows[kind-1]=(struct audio_row){1,file,size,offset};
    }
    int result=ferror(f)?bad("audio-config"):0;fclose(f);
    if(rows[0].present!=rows[1].present)return bad("audio-config");
    if(rows[0].present&&(rows[0].offset||rows[1].file!=rows[0].file||rows[1].size!=64||rows[1].offset!=rows[0].size))return bad("audio-config");
    for(unsigned kind=10;kind<=15;kind++)if(rows[kind-1].present){
        struct audio_row *expected=&rows[kind<=12?1:0];
        if(!expected->present||memcmp(&rows[kind-1],expected,sizeof(*expected)))return bad("audio-config");
    }
    if(rows[2].present&&rows[2].offset)return bad("audio-config");
    mechanical_variants(rows);return result;
}
static int publish_audio_config(struct audio_row *rows) {
    char csv[1536];size_t at=(size_t)snprintf(csv,sizeof csv,"\n/* START */\n/usr/share/avsystemsound/\n");
    for(int i=0;i<AUDIO_ROWS;i++)if(rows[i].present){int n=snprintf(csv+at,sizeof(csv)-at,"CUSTOM,0x%04X,APP,%s,0x%X,0x%X,AA_RT,6,%X,0,0,0\n",i+1,audio_names[rows[i].file],rows[i].size,rows[i].offset,i+1);
        if(n<0||(size_t)n>=sizeof(csv)-at)return bad("audio-config-size");at+=(size_t)n;}
    memcpy(csv+at,"/* END */\n",10);at+=10;
    if(undo_snapshot_file(name_count+8)||undo_replace_file(name_count+8,(unsigned char*)csv,at,0))return -1;
    return 0;
}
static int install_audio(int selection,unsigned char *audio,size_t length,struct audio_row *rows) {
    unsigned file;for(file=0;file<3;file++){int used=0;for(int i=0;i<AUDIO_ROWS;i++)if(rows[i].present&&rows[i].file==file)used=1;if(!used)break;}
    if(file==3)return bad("audio-space");if(writable(2))return -1;
    size_t stored=length;if(selection&1){memset(audio+length,0,64);stored+=64;}
    if(undo_snapshot_file(name_count+5+file)||undo_replace_file(name_count+5+file,audio,stored,0))return -1;
    if(selection&1){rows[0]=(struct audio_row){1,file,length,0};rows[1]=(struct audio_row){1,file,64,length};}
    if(selection&2)rows[2]=(struct audio_row){1,file,length,0};
    mechanical_variants(rows);
    if(rows[0].present){
        if(writable(1))return -1;int fd=cp_open();if(fd<0)return bad("cp-open");
        int result=replace_bytes(fd,sound_variant_offset,sound_variant_after,4);close(fd);if(result)return -1;
    }
    return publish_audio_config(rows);
}
static int reset_audio(int selection,struct audio_row *rows){
    if(selection!=3)return bad("arguments");
    if(writable(2)||publish_audio_config((struct audio_row[AUDIO_ROWS]){{0}})||writable(1))return -1;
    int fd=cp_open();if(fd<0)return bad("cp-open");
    int result=replace_bytes(fd,sound_table_offset,sound_tables[4],5)||
        replace_bytes(fd,sound_gate_offset,sound_gates[4],SOUND_GATE_SIZE)||
        replace_bytes(fd,sound_front_offset,sound_front_before,2)||
        replace_bytes(fd,sound_mechanical_offset,sound_mechanical_before,2)||
        replace_bytes(fd,sound_variant_offset,sound_variant_before,4);
    close(fd);return result?-1:0;
}

int main(int argc,char **argv) {
#ifdef CAMERA_API_TEST
    root=getenv("A7C2_TEST_ROOT");if(!root)return 2;
#endif
    int result=-1,undo_closed=0;
#if API_MENU_ICONS
    unsigned char small[I_PACKET_MAX],*data=small;
#elif API_FULL_NATIVE
    unsigned char small[F_FRAME],*data=small;
#else
    unsigned char small[1324],*data=small;
#endif
    if(argc==2&&!strcmp(argv[1],"info")) {
        char state[32],op[32];int restarted;if(state_snapshot(state,op,&restarted))goto answer;
        printf("{\"slots\":[");int comma=0;for(int i=0;i<6;i++)if(slot_mask&(1<<i)){printf("%s%d",comma?",":"",i+1);comma=1;}
        printf("],\"state\":\"%s\",\"operation\":\"%s\",\"api_protocol\":2,\"native_look_protocol\":2,\"sound\":[%s],\"sound_operations\":[%s],\"native_photo\":%s,\"menu_icons_protocol\":%u,\"look_storage\":\"%s\",\"live_reload\":%s,\"look_activation\":\"battery_removal\",\"sound_loader_max_buffers\":%u}\n",state,op,sound_available?"\"mechanical\",\"electronic\",\"both\"":"",
            !sound_available?"":custom_audio_available?"\"on\",\"off\",\"custom\",\"reset\"":"\"on\",\"off\"",photo_available?"true":"false",(unsigned)API_MENU_ICONS,API_FIXED_BANK?"cp-fixed-v1":"cp-static","false",custom_audio_available?2U:0U);return 0;
    }
    if(argc==2&&!strcmp(argv[1],"task")){result=task();goto answer;}
#if API_FIXED_BANK
    if(argc==2&&!strcmp(argv[1],"look-status")){result=fixed_status();goto answer;}
#endif
    if(argc==2&&!strcmp(argv[1],"files")){result=rb_files();goto answer;}
    if(argc==5&&!strcmp(argv[1],"readback")){result=rb_read(argv+2);goto answer;}
    if(argc==3&&!strcmp(argv[1],"undo")){result=rb_undo(argv[2]);goto answer;}
    if(argc==3&&!strcmp(argv[1],"result")){result=rb_result(argv[2]);goto answer;}
    int reset_sound=argc==4&&!strcmp(argv[1],"sound")&&!strcmp(argv[3],"reset");
    int is_look=argc==4&&!strcmp(argv[1],"look"),selection=0,custom=0,enabled=0,slot=0;
    size_t size=0;struct audio_row rows[AUDIO_ROWS]={{0}};
    if(is_look) {
        char *end;long value=strtol(argv[2],&end,10);if(*end||value<1||value>6||!(slot_mask&(1<<(value-1)))){bad("slot");goto answer;}slot=value;
        size_t length=strlen(argv[3]);if(!length||length>63){bad("name");goto answer;}
        for(size_t i=0;i<length;i++)if((unsigned char)argv[3][i]<32){bad("name");goto answer;}
        if(input(data,sizeof(small),&size)){bad("look-size");goto answer;}
        const unsigned char *color=data;size_t color_size=size;
        int artwork=icon_unwrap(&color,&color_size);
        if(artwork<0)goto answer;
        if(artwork){memmove(data,color,color_size);size=color_size;}
        const unsigned char *grid=data;int dense=0;
#if API_FULL_NATIVE
        if(full_frame(data,size)){if(full_edit_valid(data+8+1215))goto answer;grid=data+8;dense=1;}
#endif
        if(!dense&&(size!=1324||data[1215]>1)){bad("look-size");goto answer;}
        for(int i=0;i<1215;i++)if((signed char)grid[i]<-64||(signed char)grid[i]>63){bad("look-range");goto answer;}
        if(!dense&&data[1215]&&!photo_available){bad("photo-unavailable");goto answer;}
        if(!dense&&data[1215])for(int i=0;i<54;i++) {
            int v=get16(data+1216+2*i),limit=(i<3||i>=30)?1024:2048;
            if(v < -limit||v>limit){bad("photo-range");goto answer;}
        }
    } else if(argc==4&&!strcmp(argv[1],"sound")&&sound_available) {
        selection=!strcmp(argv[2],"mechanical")?1:!strcmp(argv[2],"electronic")?2:!strcmp(argv[2],"both")?3:0;
        custom=!strcmp(argv[3],"custom");enabled=!strcmp(argv[3],"on");
        if(!selection||(!custom&&!enabled&&!reset_sound&&strcmp(argv[3],"off"))){bad("arguments");goto answer;}
        if(custom){
            if(!custom_audio_available){bad("custom-unavailable");goto answer;}
            data=malloc(51200);if(!data){data=small;bad("memory");goto answer;}
            if(input(data,51136,&size)||!size||size%64){bad("audio-size");goto answer;}
            for(size_t i=0;i<size;i+=32)if(data[i]>8){bad("audio-codec");goto answer;}
        }
    } else {bad("arguments");goto answer;}
    if(protect_transaction())goto answer;
    char p[640];path(p,sizeof(p),"/tmp_wbshd/a7c2-resource-update.lock");
    if(mkdir(p,0700)){bad("busy");goto answer;}
#define CHECK_FILE(file,bytes,rows) check_file(file,bytes,rows,sizeof(rows)/sizeof(rows[0]))
    int checked=is_look?(CHECK_FILE("/cp/cpapp-b.bin",cp_file_size,look_cp_guards)||CHECK_FILE("/usr/lib/appFw.so",ap_file_size,look_ap_guards)):
        (CHECK_FILE("/cp/cpapp-b.bin",cp_file_size,sound_cp_guards)||CHECK_FILE("/usr/lib/appFw.so",ap_file_size,sound_ap_guards));
    if(!checked&&!is_look){char cp[640];path(cp,sizeof(cp),"/cp/cpapp-b.bin");int fd=open(cp,O_RDONLY);
        if(fd<0)checked=bad("cp-open");else{checked=sound_current(fd)<0;close(fd);}}
    if(!checked&&custom)checked=CHECK_FILE("/usr/lib/appFw.so",ap_file_size,custom_ap_guards);
    if(!checked&&!is_look&&custom_audio_available)checked=sound_shutdown_fix(0);
    if(!checked&&(custom||reset_sound))checked=audio_config(rows);
    if(!checked)checked=ready(is_look);
#if API_FIXED_BANK
    if(!checked&&is_look)checked=fixed_prepare(slot,data,size);
#endif
    if(!checked&&is_look)for(unsigned i=0;i<name_count;i++)if(name_file(name_files[i],slot,argv[3],0)){checked=1;break;}
    unsigned journal_bytes=icon_masks?200000:(custom||reset_sound)?110000:1024;
#if API_FIXED_BANK
    if(is_look)journal_bytes+=FIXED_BYTES+32768;
#endif
    if(checked||(is_look&&icons_prepare((unsigned)slot))||
        space_for(0,journal_bytes,2,(icon_masks||(API_FIXED_BANK&&is_look))?2:1)||
        (is_look&&space_for(2,72*name_count+icon_growth,name_count+4,0))||
        (custom&&space_for(2,53248,2,2))||writable(0)){rmdir(p);goto answer;}
    if(undo_begin(custom||reset_sound)){rmdir(p);goto cleanup;}
    if(save_state("running",argv[1])){rmdir(p);goto cleanup;}
    if(!is_look&&custom_audio_available&&sound_shutdown_fix(1)){result=-1;goto operation_done;}
    if(is_look)result=install_look(slot,argv[3],data,size);
    else if(custom){if(!install_audio(selection,data,size,rows))result=sound_switch(selection,1);}
    else if(reset_sound)result=reset_audio(selection,rows);
    else result=sound_switch(selection,enabled);
operation_done:
    if(!result&&is_look)result=icons_publish();
#if API_FIXED_BANK
    if(!result&&is_look)result=fixed_publish();
#endif
    const char *operation=argv[1];
#if API_FIXED_BANK
    if(is_look){
        if(!result&&undo_active&&undo_mark("COMMIT01"))result=-1;
        if(!result){fixed_commit_started=1;if(save_state("pending_reload",operation))result=-1;else fixed_task_done=1;}
    }else
#endif
    {
        if(!result&&save_state("pending_reload",operation))result=-1;
        if(!result&&undo_active&&undo_mark("COMMIT01"))result=-1;
    }
    if(result){
#if API_FIXED_BANK
        if(!fixed_commit_started)
#endif
        {
            const char *saved=error;int rollback=undo_active?undo_abort():0;
            int state_error=save_state(undo_active&&!rollback?"rolled_back":"failed",operation);
            if(state_error&&undo_active&&!rollback){rollback=1;undo_rolled_back=0;}
            error=rollback?"rollback-incomplete":saved;
        }
    }
    if(!result&&!undo_active)rmdir(p);
cleanup: {
    int release=undo_active&&(!result||undo_rolled_back);
    undo_close();undo_closed=1;
    if(restore_mounts()){result=-1;release=0;}
    if(release)rmdir(p);
}
answer:
    icons_close();if(!undo_closed)undo_close();if(data!=small)free(data);
#if API_FIXED_BANK
    fixed_close();
#endif
    if(result){
#if API_FIXED_BANK
        if(fixed_commit_started)printf("{\"state\":\"failed\",\"error\":\"%s\",\"files_committed\":true,\"task_committed\":%s,\"rollback_complete\":false"
            "}\n",error,fixed_task_done?"true":"false"
            );
        else
#endif
        if(undo_fd>=0)printf("{\"state\":\"failed\",\"error\":\"%s\",\"rollback_complete\":%s}\n",error,undo_rolled_back?"true":"false");
        else printf("{\"state\":\"failed\",\"error\":\"%s\"}\n",error);
    }else if(argc!=2&&strcmp(argv[1],"readback")&&strcmp(argv[1],"undo")&&strcmp(argv[1],"result")){
        const char *restart=!strcmp(argv[1],"look")?",\"reload_required\":true,\"restart_method\":\"battery_removal\",\"live_reload\":false,\"runtime_verified\":false":"";
        if(undo_path[0])printf("{\"state\":\"pending_reload\",\"menu_icons\":%s,\"undo\":\"%s\"%s}\n",icon_masks?"true":"false",strrchr(undo_path,'/')+1,restart);
        else printf("{\"state\":\"pending_reload\"%s}\n",restart);
    }
    return result?1:0;
}
