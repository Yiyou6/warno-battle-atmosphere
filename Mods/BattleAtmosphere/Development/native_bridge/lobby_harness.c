/* Standalone ABI smoke test, not a running-game or rendered-lobby test.
 * Only touches the virtual image allocated by this process. */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define BA_PROXY
static unsigned char *game;
static int enabled=1;
static int ba_allowed(void) {return enabled;}
static void open_runtime_log(void) {}
static void log_line(const char *s) {puts(s);fflush(stdout);}
static int readable(void *p,SIZE_T size) {
    MEMORY_BASIC_INFORMATION r;uintptr_t start=(uintptr_t)p;
    return p && VirtualQuery(p,&r,sizeof(r)) && r.State==MEM_COMMIT &&
        !(r.Protect&(PAGE_NOACCESS|PAGE_GUARD)) && start+size>=start &&
        start+size<=(uintptr_t)r.BaseAddress+r.RegionSize;
}
#include "skirmish_lobby.h"
#include "lobby_selftest.h"
int main(int argc,char **argv) {
    DWORD old;
    const unsigned char hidden[]={0x8b,0x8d,0xbc,0,0,0,0x03,0x48,0x14,0x41,0x29,0xcf};
    enabled=!strstr(GetCommandLineA(),"--disabled");
    game=VirtualAlloc(NULL,0x1600000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!game)return 2;
    game[0x15d44bd]=0xb8;game[0x15d44be]=8;
    game[0x15d59b6]=0xb9;game[0x15d59b7]=8;
    memcpy(game+0x15ceeb0,lobby_getter_fixture,sizeof(lobby_getter_fixture));memcpy(game+0x13a7d7c,hidden,sizeof(hidden));
    VirtualProtect(game,0x1600000,PAGE_EXECUTE_READ,&old);
    if(!lobby_capacity_install())return 3;
    SetEnvironmentVariableA("BA_LOBBY_TEST","2");
    lobby_capacity_selftest();
    return 4;
}
