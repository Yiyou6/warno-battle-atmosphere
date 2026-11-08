#ifdef BA_PROXY
#include "lobby_fixtures.h"
static void lobby_capacity_selftest(void) {
    unsigned char *page, room[0x300], players[20*0x88];
    unsigned i,j,patched; DWORD old; char setting[8],line[256];
    /* Both flags required; never fabricate a room or touch the user's profile. */
    if(!strstr(GetCommandLineA(),"BattleAtmosphereProbeAutoFixture") ||
       !strstr(GetCommandLineA(),"-headless") ||
       !GetEnvironmentVariableA("BA_LOBBY_TEST",setting,8) || (setting[0]!='1' && setting[0]!='2'))return;
    page=lobby_near_page(game+0x15d44bd);if(!page){log_line("LOBBY_TEST_ERROR allocation");return;}
    for(i=0;i<2;i++)for(patched=0;patched<2;patched++) {
        unsigned char *code=page+(i*2+patched)*512;
        unsigned at=i?lobby_fixture_site_1:lobby_fixture_site_0;
        const unsigned char *source=i?lobby_fixture_1:lobby_fixture_0;
        unsigned length=i?sizeof(lobby_fixture_1):sizeof(lobby_fixture_0);
        memcpy(code,source,length);
        if(patched){code[at]=0xe8;*(int32_t *)(code+at+1)=(int32_t)((lobby_relays+i*256)-(code+at+5));}
    }
    VirtualProtect(page,4096,PAGE_EXECUTE_READ,&old);
    FlushInstructionCache(GetCurrentProcess(),page,4096);
    for(i=0;i<2;i++)for(j=0;j<6;j++) {
        unsigned stock,actual,expected;
        memset(room,0,sizeof(room));memset(players,0,sizeof(players));
        room[0x130]=(j>=2);room[0x1a8]=(j==1 || j>=3);
        *(unsigned *)(room+0x13c)=8;*(unsigned *)(room+0x134)=(j==4?20:8);
        *(unsigned *)(room+0x60)=1;*(void **)(room+0x68)=players;players[0x40]=(j!=5);
        stock=((unsigned (*)(void *))(page+i*1024))(room);
        actual=((unsigned (*)(void *))(page+i*1024+512))(room);
        expected=(j<2 && ba_allowed())?20:stock;
        sprintf(line,"LOBBY_CAPACITY_TEST site=%u case=%u network=%u host=%u stock=%u actual=%u expected=%u pass=%u",
            i,j,room[0x130],room[0x1a8],stock,actual,expected,actual==expected);
        log_line(line);
    }
    VirtualFree(page,0,MEM_RELEASE);
    /* Mode 2 is a bounded native calculation test, not a skirmish. A disabled
     * runtime cannot populate the otherwise empty headless fixture world. */
    if(setting[0]=='2') {
        log_line("LOBBY_CAPACITY_TEST_ONLY_COMPLETE");
        fflush(NULL);
        ExitProcess(0);
    }
}
#endif
