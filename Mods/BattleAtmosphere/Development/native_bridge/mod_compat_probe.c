/* Owned headless diagnostic only. Never install this DLL in the real game root. */
#define ba_startup ba_runtime_startup
#include "probe_bridge.c"
#undef ba_startup

static void compatibility_probe_start(void *launcher) {
    unsigned char *manager=*(unsigned char **)(game+0x31a6a90), *items;
    unsigned count,i; char line[2048];
    if (!readable(manager,0x98)) {log_line("MOD_AUDIT_NO_MANAGER");ExitProcess(71);}
    items=*(unsigned char **)(manager+0x40);count=*(unsigned *)(manager+0x48);
    sprintf(line,"MOD_AUDIT_COUNT %u",count);log_line(line);
    if (count>4096 || (count && !readable(items,count*0x68))) ExitProcess(72);
    for (i=0;i<count;i++) {
        unsigned char *item=items+i*0x68;
        const char *name=((const char *(*)(void *))(game+0x57a0))(item+0x10);
        const char *path=((const char *(*)(void *))(game+0x57a0))(item+0x38);
        sprintf(line,"MOD_AUDIT name=%.160s path=%.200s id=%llu version=%u generation=%u flags=%u,%u,%u,%u,%u,%u",
          name,path,*(unsigned long long *)item,*(unsigned *)(item+8),*(unsigned *)(item+0x44),
          item[0x48],item[0x49],item[0x4a],item[0x4b],item[0x4c],item[0x4d]);
        log_line(line);
    }
    {
        const char *selected=((const char *(*)(void *))(game+0x57a0))(manager+0x90);
        int room_status=((int (*)(void *,void *))(game+0x1570250))(0,manager+0x90);
        sprintf(line,"MOD_AUDIT_ROOM selected=%.200s native_status=%d",selected,room_status);
        log_line(line);
    }
    /* Finish through the native map-load/quit lifecycle, so this diagnostic
       does not leave EugGame.lock behind or trigger recovery on next boot. */
    automatic_start(launcher);
}
int ba_startup(void) {
    DWORD old,ignored;void **vtable;
    if (!strstr(GetCommandLineA(),"-headless")) return 0;
    if (!ba_runtime_startup()) return 0;
    vtable=(void **)(game+0x235e118);
    if (!VirtualProtect(vtable+11,8,PAGE_READWRITE,&old)) return 0;
    vtable[11]=compatibility_probe_start;
    VirtualProtect(vtable+11,8,old,&ignored);
    return 1;
}
