/* Standalone boundary tests of extracted production functions.
 * All memory and engine stubs belong to this process; no game is opened. */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct { intptr_t refs; void *type; } PyObject;
typedef struct { PyObject base; intptr_t size; long hash; unsigned char interned; char data[1]; } PyString;
static unsigned char *game;
static DWORD python_thread;
static int in_callback=1, shutting_down;
static uint64_t leased_ids[4096], lease_expiry[4096], simulation_ticks;
static unsigned leased_count, additions, removals;
static unsigned char player_list[64], player_data[32][128], unit_lists[32][64];
static uint64_t owners[32], unit_ids[32][4096];
static unsigned char ownership[5200][32], positions[5200][64];
static unsigned char answer[5200*40];
static intptr_t answer_size;
static PyObject result, nil;
static PyObject *none(void) {answer_size=-1;return &nil;}
static PyString *string_arg(PyObject *p) {return (PyString *)p;}
static int readable(void *p,SIZE_T size) {
    MEMORY_BASIC_INFORMATION r;uintptr_t start=(uintptr_t)p;
    return p && VirtualQuery(p,&r,sizeof(r)) && r.State==MEM_COMMIT &&
        !(r.Protect&(PAGE_NOACCESS|PAGE_GUARD)) && start+size>=start &&
        start+size<=(uintptr_t)r.BaseAddress+r.RegionSize;
}
static unsigned char *find_component(uint64_t id,unsigned char kind,int entity) {
    unsigned k;
    if(entity==2 && id>0x100000000ULL && id<=0x100000014ULL) {
        k=(unsigned)(id-0x100000001ULL);
        return kind==0x81?player_data[k]:kind==0x86?unit_lists[k]:NULL;
    }
    if(entity==0 && id>=0x200000000ULL && id<0x200001450ULL) {
        k=(unsigned)(id-0x200000000ULL);
        return kind==0x61?ownership[k]:kind==0x6b?positions[k]:NULL;
    }
    return NULL;
}
static PyObject *make_string(const char *s,intptr_t n) {
    if(n>sizeof(answer))ExitProcess(7);
    memcpy(answer,s,n);answer_size=n;return &result;
}
static void add_lease(void *manager,uint64_t id) {additions++;}
static void remove_lease(void *manager,uint64_t id) {removals++;}
static void jump(unsigned rva,void *fn) {
    game[rva]=0x48;game[rva+1]=0xb8;memcpy(game+rva+2,&fn,8);
    game[rva+10]=0xff;game[rva+11]=0xe0;
}
#include "capacity_functions.generated.h"
static int lease(uint64_t id,int on) {
    unsigned char storage[128];PyString *arg=(PyString *)storage;
    memset(storage,0,sizeof(storage));arg->size=12;
    memcpy(arg->data,&id,8);memcpy(arg->data+8,&on,4);
    lease_ai_unit(NULL,(PyObject *)arg);
    return answer_size==4?*(int *)answer:-99;
}
int main(void) {
    unsigned i,j,k=0,failed=0,seen[20]={0};unsigned char manager[0x200];
    game=VirtualAlloc(NULL,0x3400000,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE);
    if(!game)return 2;
    python_thread=GetCurrentThreadId();
    jump(0x1c55f40,make_string);jump(0xd814d0,add_lease);jump(0xd81510,remove_lease);
    *(void **)(game+0x3389840)=player_list;*(void **)(game+0x3389b70)=manager;
    *(void **)(player_list+0x20)=owners;*(unsigned *)(player_list+0x28)=20;
    for(i=0;i<20;i++) {
        owners[i]=0x100000001ULL+i;
        *(int *)(player_data[i]+0x3c)=i/10;
        *(int *)(player_data[i]+0x40)=6;
        *(int *)(player_data[i]+0x44)=i;
        *(void **)(unit_lists[i]+0x18)=unit_ids[i];*(unsigned *)(unit_lists[i]+0x20)=260;
        for(j=0;j<260;j++,k++) {
            unit_ids[i][j]=0x200000000ULL+k;
            *(uint64_t *)(ownership[k]+0x18)=owners[i];
            *(float *)(positions[k]+0x30)=(float)k;
        }
    }
    world_unit_snapshot(NULL,NULL);
    for(i=0;i<(unsigned)(answer_size/40);i++) {
        j=*(unsigned *)(answer+i*40+24);
        if(j>=20)ExitProcess(8);seen[j]++;
        if(*(uint64_t *)(answer+i*40)!=0x200000000ULL+i ||
           *(uint64_t *)(answer+i*40+8)!=owners[j] ||
           *(float *)(answer+i*40+28)!=(float)i)failed++;
    }
    for(i=0;i<20;i++)if(seen[i]!=260)failed++;
    printf("SNAPSHOT units=%ld expected=5200 last_owner=%u expected_last=260 pass=%d\n",(long)(answer_size/40),seen[19],!failed);
    for(i=0;i<4096;i++)if(lease(0x200000000ULL+i,1)!=1)ExitProcess(9);
    simulation_ticks=100;
    i=lease(0x200000000ULL,1);
    j=i==1 && leased_count==4096 && additions==4096 && lease_expiry[0]==108;
    printf("LEASE_FULL_RENEW status=%u expiry=%llu pass=%u\n",i,(unsigned long long)lease_expiry[0],j);
    if(!j)failed++;
    j=lease(0x200001000ULL,1)==0 && leased_count==4096 && additions==4096;
    printf("LEASE_FULL_NEW_REFUSED pass=%u\n",j);if(!j)failed++;
    lease(0x200000000ULL,0);
    j=lease(0x200001000ULL,1)==1 && leased_count==4096 && removals==1;
    printf("LEASE_REUSE_AFTER_RELEASE pass=%u\n",j);if(!j)failed++;
    *(int *)(player_data[0]+0x40)=0;
    j=lease(0x200000001ULL,1)==0;
    printf("LEASE_HUMAN_REFUSED pass=%u\n",j);if(!j)failed++;
    simulation_ticks=200;expire_leases();
    j=leased_count==0 && removals==4097;
    printf("LEASE_EXPIRE_ALL pass=%u\n",j);if(!j)failed++;
    *(unsigned *)(player_list+0x28)=0;
    world_unit_snapshot(NULL,NULL);
    j=answer_size==0;
    printf("SNAPSHOT_EMPTY pass=%u\n",j);if(!j)failed++;
    return failed?1:0;
}
