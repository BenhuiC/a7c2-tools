/* One-shot USB adaptor. Only a child executes the installed command. */
#define _init model_probe
#include "../fl23/native/probe.c"
#undef _init
#include PATCH_MANIFEST
#ifndef USB_API_DIR
#define USB_API_DIR "/tmp/jiritsu/"
#endif
#ifndef USB_API_COMMAND
#define USB_API_COMMAND "/usr/lib/a7c2-tools/ssh/a7c2-api"
#endif
#ifndef USB_API_ENTRY
#define USB_API_ENTRY _init
#endif
static u8 request[52000];
static void exit_child(i64 code){sc(94,code,0,0,0,0,0);for(;;){}}
static void finish(i64 status){
    i64 fd=op(USB_API_DIR "a7c2.api.result",0x241);
    if(fd>=0){write_all(fd,&status,8);sc(82,fd,0,0,0,0,0);cl(fd);}
}
static int equal(const u8 *a,const char *b){u32 i=0;while(b[i]&&a[i]==(u8)b[i])i++;return !b[i]&&!a[i];}
__attribute__((visibility("default"))) void USB_API_ENTRY(void){
#ifndef USB_API_TEST
    model_probe();
    if(report.status||report.index!=16||report.euid){finish(-19);return;}
#else
    sc(35,-100,(i64)(USB_API_DIR "libJit.so"),0,0,0,0);
#endif
    i64 n=read_all(USB_API_DIR "a7c2.api.request",request,sizeof request);
    if(n<4){finish(-22);return;}
    u32 count=request[0],at=1;char *argv[5]={(char*)USB_API_COMMAND,0,0,0,0};
    if(count<1||count>3){finish(-22);return;}
    for(u32 i=0;i<count;i++){
        argv[i+1]=(char*)request+at;u32 begin=at;
        while(at<(u32)n&&request[at])at++;
        if(at>=(u32)n||at-begin>128){finish(-22);return;}at++;
    }
    if(!((count==1&&(equal((u8*)argv[1],"info")||equal((u8*)argv[1],"task")))||
         (count==3&&(equal((u8*)argv[1],"look")||equal((u8*)argv[1],"sound"))))||n-at>51200){finish(-22);return;}
    i64 fd=op(USB_API_DIR "a7c2.api.stdin",0x241);
    if(fd<0||write_all(fd,request+at,(u32)n-at)){cl(fd);finish(-5);return;}cl(fd);
    /* Detach a bounded monitor; the App waits only for its immediate child. */
    i64 child=sc(220,17,0,0,0,0,0);
    if(child<0){finish(child);return;}
    if(child){i64 status;while(sc(260,child,(i64)&status,0,0,0,0)==-4){}return;}
    i64 monitor=sc(220,17,0,0,0,0,0);
    if(monitor<0){finish(monitor);exit_child(1);}
    if(monitor)exit_child(0);
    sc(157,0,0,0,0,0,0); /* separate the monitor from the USB caller's session */
    u64 limit[2]={65536,65536};sc(163,7,(i64)limit,0,0,0,0);
    for(u64 i=0;i<limit[0];i++)cl((i64)i);
    i64 api=sc(220,17,0,0,0,0,0);
    if(api<0){finish(api);exit_child(1);}
    if(!api){
        const char *names[]={USB_API_DIR "a7c2.api.stdin",USB_API_DIR "a7c2.api.stdout",USB_API_DIR "a7c2.api.stderr"};
        for(i64 i=0;i<3;i++){
            i64 f=op(names[i],i?0x241:0);
            if(f<0||(f!=i&&sc(24,f,i,0,0,0,0)<0))exit_child(126);
            if(f!=i)cl(f);
        }
        char *env[]={"PATH=/bin:/usr/bin",0};
        sc(221,(i64)USB_API_COMMAND,(i64)argv,(i64)env,0,0,0);exit_child(127);
    }
    i64 status=0,wait;do{wait=sc(260,api,(i64)&status,0,0,0,0);}while(wait==-4);
    finish(wait<0?wait:status);exit_child(0);
}
