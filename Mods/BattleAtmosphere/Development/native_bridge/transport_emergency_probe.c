/* Controlled native unload-now diagnostic, isolated headless copy only. */
#define ba_startup ba_runtime_startup
#include "probe_bridge.c"
#undef ba_startup
static void emergency_probe_start(void *launcher) {
    PyObject *result;
    automatic_start(launcher);
    ((void (*)(void *))(game+0x4bff0))(game+0x3389610);
    /* Explicitly replace only this diagnostic child's observer callback. */
    decref(tick_callback);tick_callback=NULL;
    result=load_embedded_module("ba_emergency_test",
        "import struct\nimport _ba_native as n\nimport ba_fixture as fixture\nfrom ba_space import Controller\n"
        "c=Controller()\nordered=set()\n"
        "def tick():\n"
        "    if c.tick<20: fixture.transport_tick(c,False)\n"
        "    for uid,carrier in fixture.transport_pairs.items():\n"
        "        for entity in (uid,carrier):n.lease_ai_unit(struct.pack('<Qi',entity,1))\n"
        "    raw=n.world_unit_snapshot()\n"
        "    rows=[struct.unpack('<QQiii3f',raw[i:i+40]) for i in range(0,len(raw),40)]\n"
        "    loaded=[]\n"
        "    for r in rows:\n"
        "        flag=struct.unpack('<i',n.unit_activity(struct.pack('<Q',r[0])))[0]\n"
        "        if r[3]==6 and flag&2:\n"
        "            loaded.append(r[0])\n"
        "            if c.tick>=20 and r[0] not in ordered:\n"
        "                result=struct.unpack('<i',n.unload_now_ai_unit(struct.pack('<Qfff',r[0],r[5],r[6],r[7])))[0]\n"
        "                n.log('EMERGENCY_NATIVE_ORDER '+repr((r[0],result)))\n"
        "                ordered.add(r[0])\n"
        "    if c.tick%20==0 or 20<=c.tick<=30:n.log('EMERGENCY_NATIVE_STATE '+repr((c.tick,len(ordered),loaded)))\n"
        "    c.tick+=1\n"
        "n.set_tick_callback(tick)\n");
    if(!result){log_line("EMERGENCY_PROBE_FAILED");ExitProcess(74);}
    decref(result);
    ((void (*)(void *))(game+0x4c000))(game+0x3389610);
}
int ba_startup(void){
    DWORD old,ignored;void **vtable;
    if(!strstr(GetCommandLineA(),"-headless") || !strstr(GetCommandLineA(),"BattleAtmosphereProbeAutoFixture"))return 0;
    if(!ba_runtime_startup())return 0;
    vtable=(void **)(game+0x235e118);
    if(!VirtualProtect(vtable+11,8,PAGE_READWRITE,&old))return 0;
    vtable[11]=emergency_probe_start;VirtualProtect(vtable+11,8,old,&ignored);return 1;
}
