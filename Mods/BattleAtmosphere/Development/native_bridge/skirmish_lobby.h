/* Revision 201602: replace only the default capacity calculation in the two
 * native lobby refresh paths. The existing network-only branches remain intact.
 * The UI allocates its roster from room+0x13c; no fixed-size roster is enlarged.
 * Original EXE and data files are never changed. */
#ifdef BA_PROXY
static unsigned char *lobby_relays;

static unsigned lobby_local_capacity(unsigned char *room) {
    unsigned result = 8;
    if (readable(room, 0x1a9) && room[0x130] == 0 &&
        !strstr(GetCommandLineA(), "-replay") && ba_allowed()) {
        char line[192];
        result = 20;
        open_runtime_log();
        sprintf(line, "SKIRMISH_CAPACITY local=1 slots=20 previous=%u roster=%u",
            *(unsigned *)(room+0x13c), *(unsigned *)(room+0x60)&0x7ffffff);
        log_line(line);
    }
    return result;
}

static unsigned char *lobby_near_page(void *site) {
    uintptr_t origin=(uintptr_t)site & ~(uintptr_t)0xffff;
    uintptr_t delta; unsigned char *page=NULL;
    for (delta=0x10000;delta<0x60000000 && !page;delta+=0x10000)
        page=VirtualAlloc((void *)(origin+delta),4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    return page;
}

/* A call replaces MOV reg,8. Preserve flags, every other volatile integer
 * register and XMM0..5: the surrounding native code still needs its CMP flags
 * and, at the second site, the AL host flag. Win64 shadow space is reserved. */
static unsigned lobby_emit_relay(unsigned char *p, int output_ecx) {
    unsigned char *start=p; unsigned i;
    static const unsigned char begin[]={0x9c,0x50,0x51,0x52,0x41,0x50,0x41,0x51,0x41,0x52,0x41,0x53,
        0x48,0x81,0xec,0x88,0,0,0};
    static const unsigned char end[]={0x48,0x81,0xc4,0x88,0,0,0,
        0x41,0x5b,0x41,0x5a,0x41,0x59,0x41,0x58,0x5a,0x59,0x58,0x9d,0xc3};
    memcpy(p,begin,sizeof(begin));p+=sizeof(begin);
    for(i=0;i<6;i++) { *p++=0xf3;*p++=0x0f;*p++=0x7f;*p++=0x44+i*8;*p++=0x24;*p++=0x20+i*16; }
    *p++=0x48;*p++=0x89;*p++=0xf1; /* rcx = native room in rsi */
    *p++=0x48;*p++=0xb8;*(void **)p=lobby_local_capacity;p+=8;
    *p++=0xff;*p++=0xd0;
    *p++=0x48;*p++=0x89;*p++=0x84;*p++=0x24;
    *(unsigned *)p=output_ecx?0xb0:0xb8;p+=4;
    for(i=0;i<6;i++) { *p++=0xf3;*p++=0x0f;*p++=0x6f;*p++=0x44+i*8;*p++=0x24;*p++=0x20+i*16; }
    memcpy(p,end,sizeof(end));p+=sizeof(end);
    return (unsigned)(p-start);
}

static int lobby_capacity_install(void) {
    static const unsigned rvas[2]={0x15d44bd,0x15d59b6};
    static const unsigned char expected[2][5]={{0xb8,8,0,0,0},{0xb9,8,0,0,0}};
    DWORD old[2],ignored; unsigned i;
    for(i=0;i<2;i++) if(!readable(game+rvas[i],5) || memcmp(game+rvas[i],expected[i],5)) return 0;
    lobby_relays=lobby_near_page(game+rvas[0]);if(!lobby_relays)return 0;
    lobby_emit_relay(lobby_relays,0);lobby_emit_relay(lobby_relays+256,1);
    if(!VirtualProtect(lobby_relays,4096,PAGE_EXECUTE_READ,&ignored))return 0;
    if(!VirtualProtect(game+rvas[0],5,PAGE_EXECUTE_READWRITE,&old[0]))return 0;
    if(!VirtualProtect(game+rvas[1],5,PAGE_EXECUTE_READWRITE,&old[1])) {
        VirtualProtect(game+rvas[0],5,old[0],&ignored);return 0;
    }
    for(i=0;i<2;i++) {
        unsigned char patch[5];patch[0]=0xe8;
        *(int32_t *)(patch+1)=(int32_t)((lobby_relays+i*256)-(game+rvas[i]+5));
        memcpy(game+rvas[i],patch,5);
        VirtualProtect(game+rvas[i],5,old[i],&ignored);
        FlushInstructionCache(GetCurrentProcess(),game+rvas[i],5);
    }
    FlushInstructionCache(GetCurrentProcess(),lobby_relays,4096);
    log_line("SKIRMISH_CAPACITY_HOOK_READY local_slots=20 original_slots=8 network_branch=stock");
    return 1;
}
#endif
