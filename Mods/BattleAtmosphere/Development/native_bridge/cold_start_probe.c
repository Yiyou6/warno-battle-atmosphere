/* Isolated headless regression only; never install this DLL in the game root.
   Prepare the minimal native roster, then remove the fixture's Python bridge
   registration so the real automatic_start must handle a cold interpreter. */
#define ba_startup ba_runtime_startup
#include "probe_bridge.c"
#undef ba_startup

static void cold_probe_start(void *launcher) {
    PyObject *result;
    ((void (*)(void *))(game+0x4bff0))(game+0x3389610);
    python_thread=GetCurrentThreadId();
    result=load_embedded_module("ba_cold_probe_reset",
        "import sys\n"
        "if '_ba_native' not in sys.modules: raise RuntimeError('cold fixture bridge missing')\n"
        "for name in ('ba_allocator', 'ba_front', 'ba_transport', 'ba_tactics', 'ba_space', 'ba_autorun'):\n"
        "    if name in sys.modules: raise RuntimeError('cold precondition violated: '+name)\n"
        "del sys.modules['_ba_native']\n");
    if (!result) { log_line("COLD_PRECONDITION_FAILED"); ExitProcess(74); }
    decref(result);
    module_ready=0;
    log_line("COLD_START_NO_NATIVE_MODULE");
    ((void (*)(void *))(game+0x4c000))(game+0x3389610);
    /* This is the production function, unchanged by the regression wrapper. */
    automatic_start(launcher);
}

int ba_startup(void) {
    DWORD old,ignored;void **vtable;
    if (!strstr(GetCommandLineA(),"-headless") ||
        !strstr(GetCommandLineA(),"BattleAtmosphereProbeAutoFixture")) return 0;
    if (!ba_runtime_startup()) return 0;
    vtable=(void **)(game+0x235e118);
    if (!VirtualProtect(vtable+11,8,PAGE_READWRITE,&old)) return 0;
    vtable[11]=cold_probe_start;
    VirtualProtect(vtable+11,8,old,&ignored);
    return 1;
}
