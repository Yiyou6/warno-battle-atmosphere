/* Revision 201602: replace only the default capacity calculation in the two
 * native lobby refresh paths. The existing network-only branches remain intact.
 * The UI allocates its roster from room+0x13c; no fixed-size roster is enlarged.
 * Original EXE and data files are never changed. */
#ifdef BA_PROXY
static unsigned char *lobby_relays;

static int lobby_is_local(unsigned char *room) {
    return readable(room,0x1a9) && room[0x130]==0 &&
        !strstr(GetCommandLineA(),"-replay") && ba_allowed();
}

/* Ordinary local-room restoration can overwrite the initial capacity. The
 * native settings accessor is used before UI allocation and Add AI. Keep the
 * real human/AI counts untouched; only the available capacity is corrected. */
static void *lobby_settings(unsigned char *room) {
    if(lobby_is_local(room) && *(unsigned *)(room+0x13c)!=20) {
        char line[192];
        sprintf(line,"SKIRMISH_ROOM_RESTORED previous=%u slots=20 humans=%u ai=%u",
            *(unsigned *)(room+0x13c),*(unsigned *)(room+0x134),*(unsigned *)(room+0x170));
        *(unsigned *)(room+0x13c)=20;
        ++*(uint64_t *)(room+0x28);++*(uint64_t *)(room+0x30);
        open_runtime_log();log_line(line);
    }
    return room+0x120;
}

static unsigned lobby_hidden_slots(unsigned char *room,unsigned original,unsigned allocated) {
    static unsigned reports;
    if(allocated==20 && lobby_is_local(room)) {
        if(reports++<8) {
            char line[128];
            sprintf(line,"SKIRMISH_OPEN_SEATS allocated=20 hidden=0 original_hidden=%u",original);
            open_runtime_log();log_line(line);
        }
        return 0;
    }
    return original;
}

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
/* kind 0/1: original capacity hooks; 2: settings accessor; 3: hidden seats.
 * Kinds 2/3 are also exercised through actual emitted native relays in tests. */
static unsigned lobby_emit_relay(unsigned char *p, int kind) {
    unsigned char *start=p; unsigned i;
    static const unsigned char begin[]={0x9c,0x50,0x51,0x52,0x41,0x50,0x41,0x51,0x41,0x52,0x41,0x53,
        0x48,0x81,0xec,0x88,0,0,0};
    static const unsigned char end[]={0x48,0x81,0xc4,0x88,0,0,0,
        0x41,0x5b,0x41,0x5a,0x41,0x59,0x41,0x58,0x5a,0x59,0x58,0x9d,0xc3};
    if(kind==3) {
        static const unsigned char original[]={0x8b,0x8d,0xbc,0,0,0,0x03,0x48,0x14,0x41,0x29,0xcf};
        memcpy(p,original,sizeof(original));p+=sizeof(original);
    }
    memcpy(p,begin,sizeof(begin));
    p+=sizeof(begin);
    for(i=0;i<6;i++) { *p++=0xf3;*p++=0x0f;*p++=0x7f;*p++=0x44+i*8;*p++=0x24;*p++=0x20+i*16; }
    if(kind==3) {
        static const unsigned char arguments[]={0x48,0x8b,0x4e,0x28,0x44,0x89,0xfa,0x44,0x8b,0x46,0x50};
        memcpy(p,arguments,sizeof(arguments));p+=sizeof(arguments);
    } else if(kind!=2) {
        *p++=0x48;*p++=0x89;*p++=0xf1; /* rcx = native room in rsi */
    }
    *p++=0x48;*p++=0xb8;
    *(void **)p=kind==2?(void *)lobby_settings:kind==3?(void *)lobby_hidden_slots:(void *)lobby_local_capacity;p+=8;
    *p++=0xff;*p++=0xd0;
    if(kind==3) { *p++=0x41;*p++=0x89;*p++=0xc7; } /* r15d = hidden count */
    else {
        *p++=0x48;*p++=0x89;*p++=0x84;*p++=0x24;
        *(unsigned *)p=kind==1?0xb0:0xb8;p+=4;
    }
    for(i=0;i<6;i++) { *p++=0xf3;*p++=0x0f;*p++=0x6f;*p++=0x44+i*8;*p++=0x24;*p++=0x20+i*16; }
    memcpy(p,end,sizeof(end));p+=sizeof(end);
    return (unsigned)(p-start);
}

static int lobby_capacity_install(void) {
    /* Settings getter retains its PUSH/MOV RBP prologue and POP/RET epilogue. */
    static const unsigned rvas[4]={0x15d44bd,0x15d59b6,0x15ceeb4,0x13a7d7c};
    static const unsigned lengths[4]={5,5,7,12};
    static const unsigned char expected[4][12]={{0xb8,8,0,0,0},{0xb9,8,0,0,0},
        {0x48,0x8d,0x81,0x20,1,0,0},{0x8b,0x8d,0xbc,0,0,0,0x03,0x48,0x14,0x41,0x29,0xcf}};
    DWORD old[4],ignored; unsigned i,j;
    for(i=0;i<4;i++) if(!readable(game+rvas[i],lengths[i]) || memcmp(game+rvas[i],expected[i],lengths[i])) return 0;
    lobby_relays=lobby_near_page(game+rvas[0]);if(!lobby_relays)return 0;
    for(i=0;i<4;i++) lobby_emit_relay(lobby_relays+i*256,i);
    if(!VirtualProtect(lobby_relays,4096,PAGE_EXECUTE_READ,&ignored))return 0;
    for(i=0;i<4;i++) if(!VirtualProtect(game+rvas[i],lengths[i],PAGE_EXECUTE_READWRITE,&old[i])) {
        for(j=0;j<i;j++)VirtualProtect(game+rvas[j],lengths[j],old[j],&ignored);
        return 0;
    }
    for(i=0;i<4;i++) {
        unsigned char patch[12];memset(patch,0x90,sizeof(patch));patch[0]=0xe8;
        *(int32_t *)(patch+1)=(int32_t)((lobby_relays+i*256)-(game+rvas[i]+5));
        memcpy(game+rvas[i],patch,lengths[i]);
        VirtualProtect(game+rvas[i],lengths[i],old[i],&ignored);
        FlushInstructionCache(GetCurrentProcess(),game+rvas[i],lengths[i]);
    }
    FlushInstructionCache(GetCurrentProcess(),lobby_relays,4096);
    log_line("SKIRMISH_CAPACITY_HOOK_READY local_slots=20 original_slots=8 network_branch=stock");
    log_line("SKIRMISH_UI_HOOK_READY restored_capacity=20 open_seats=20");
    return 1;
}
#endif
