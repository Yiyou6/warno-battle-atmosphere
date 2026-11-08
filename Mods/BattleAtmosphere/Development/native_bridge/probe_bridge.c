/* Isolated headless research bridge, NOT an installed mod or public SDK.
 * Only the hash-pinned launcher may load this into the process it creates.
 * No original executable/archive changes. No arbitrary-address Python API.
 * Base ABI checked against CPython v2.5.1; WARNO packs string intern state
 * into one byte (verified in native constructor RVA 0x1c55f40).
 */
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <stdio.h>
#include <wchar.h>
#ifdef BA_EMBEDDED
#include "embedded_python.h"
#endif

typedef struct { intptr_t refs; void *type; } PyObject;
typedef struct { PyObject base; intptr_t size; long hash; unsigned char interned; char data[1]; } PyString;
typedef PyObject *(*PyCFunction)(PyObject *, PyObject *);
typedef struct { const char *name; PyCFunction function; int flags; const char *doc; } Method;
typedef PyObject *(*ImportFn)(const char *);
typedef PyObject *(*InitFn)(const char *, Method *, const char *, PyObject *, int);

static unsigned char *game;
static void *script_handle[2];
static DWORD python_thread;
static int module_ready;
static HANDLE runtime_log = INVALID_HANDLE_VALUE;
static PyObject *tick_callback;
static void *observed_descriptor;
static void **original_descriptor_vtable;
static void *descriptor_vtable[14], *action_vtable[15];
static void (*original_action_step)(void *);
static void (*original_timer_done)(void *);
static int observed_timer, shutting_down;
static void *(*original_factory)(void *, void *);
static int in_callback;
static PyObject *automatic_wrapper;
static void *automatic_launcher;
static void *attached_action;
static int attached_mode;
static uint64_t leased_ids[4096];
static uint64_t lease_expiry[4096], simulation_ticks;
static unsigned leased_count;
#ifdef BA_PROXY
extern int ba_allowed(void);
static int automatic_enabled;
#endif
static void release_leases(void);
static void expire_leases(void);

static void decref(PyObject *value) {
    if (value && --value->refs == 0)
        ((void (*)(PyObject *))(*(void **)((char *)value->type + 0x30)))(value);
}

static void log_bytes(const char *s, DWORD length) {
    DWORD written;
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    WriteFile(output, "BA_BRIDGE ", 10, &written, NULL);
    WriteFile(output, s, length, &written, NULL);
    WriteFile(output, "\r\n", 2, &written, NULL);
    if (runtime_log != INVALID_HANDLE_VALUE) {
        WriteFile(runtime_log, "BA_RUNTIME ", 11, &written, NULL);
        WriteFile(runtime_log, s, length, &written, NULL);
        WriteFile(runtime_log, "\r\n", 2, &written, NULL);
    }
}
static void open_runtime_log(void) {
    wchar_t path[32768], *last;
    if (runtime_log!=INVALID_HANDLE_VALUE || !GetModuleFileNameW(NULL,path,32768)) return;
    last=wcsrchr(path,L'\\');if (!last) return;*last=0;
    if (wcslen(path)>32000) return;
    wcscat(path,L"\\Mods\\BattleAtmosphere\\Runtime\\last-run.log");
    runtime_log=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
}
static void log_line(const char *s) { log_bytes(s, (DWORD)strlen(s)); }
static PyObject *none(void) {
    PyObject *value = (PyObject *)(game + 0x315fb48);
    value->refs++;
    return value;
}
static PyString *string_arg(PyObject *value) {
    const char *type_name;
    if (!value || !value->type) return NULL;
    type_name = *(const char **)((char *)value->type + 24);
    if (!type_name || strcmp(type_name, "str")) return NULL;
    return (PyString *)value;
}
static PyObject *bridge_log(PyObject *self, PyObject *arg) {
    PyString *text = string_arg(arg);
    if (text && text->size >= 0 && text->size <= 16384)
        log_bytes(text->data, (DWORD)text->size);
    else log_line("REJECT invalid log argument");
    return none();
}
static void log_python_error(void) {
    PyObject *type = NULL, *value = NULL, *trace = NULL, *text = NULL;
    PyString *packed;
    ((void (*)(PyObject **, PyObject **, PyObject **))(game + 0x1ca0560))(&type, &value, &trace);
    if (value) text = ((PyObject *(*)(PyObject *, const char *, const char *))(game + 0x1c21420))(value, "__str__", NULL);
    packed = string_arg(text);
    if (packed) log_bytes(packed->data, (DWORD)packed->size);
    decref(text); decref(type); decref(value); decref(trace);
    ((void (*)(void))(game + 0x1ca05a0))();
}
static int readable(void *ptr, SIZE_T size) {
    MEMORY_BASIC_INFORMATION region;
    uintptr_t start = (uintptr_t)ptr;
    if (!ptr || !VirtualQuery(ptr, &region, sizeof(region))) return 0;
    if (region.State != MEM_COMMIT || (region.Protect & (PAGE_NOACCESS | PAGE_GUARD))) return 0;
    return start + size >= start && start + size <= (uintptr_t)region.BaseAddress + region.RegionSize;
}
static void invoke_tick_callback(void) {
    PyObject *result;
    if (!shutting_down) { simulation_ticks++; expire_leases(); }
    if (!tick_callback || shutting_down) return;
    /* Exactly the engine's Python serialization lock; callback runs on the
       GD simulation thread, never on a polling/background thread. */
    ((void (*)(void *))(game + 0x4bff0))(game + 0x3389610);
    python_thread = GetCurrentThreadId();
    in_callback = 1;
    result = ((PyObject *(*)(PyObject *, PyObject *))(game + 0x1c24ff0))(tick_callback, NULL);
    in_callback = 0;
    if (!result) {
        log_line("CALLBACK_ERROR");
        release_leases();
        ((void (*)(int))(game + 0x1cb22f0))(0);
        ((void (*)(void))(game + 0x1ca05a0))();
        decref(tick_callback);
        tick_callback = NULL;
    } else decref(result);
    ((void (*)(void *))(game + 0x4c000))(game + 0x3389610);
}
static void count_action_step(void *action) {
    original_action_step(action);
    invoke_tick_callback();
}
static void timer_done(void *action) {
    original_timer_done(action);
    invoke_tick_callback();
}
static void *count_factory(void *descriptor, void *context) {
    void *action = original_factory(descriptor, context);
    void **vtable = *(void ***)action;
    if (vtable != (void **)(game + (observed_timer ? 0x22a0ca8 : 0x22a0bb8))) {
        log_line("REJECT unexpected count action type"); return action;
    }
    memcpy(action_vtable, vtable - 1, (observed_timer ? 15 : 13) * sizeof(void *));
    if (observed_timer) {
        original_timer_done = (void (*)(void *))vtable[13];
        action_vtable[14] = (void *)timer_done;
    } else {
        original_action_step = (void (*)(void *))vtable[8];
        action_vtable[9] = (void *)count_action_step;
    }
    *(void ***)action = action_vtable + 1;
    return action;
}
static PyObject *set_tick_callback(PyObject *self, PyObject *callback) {
    if (GetCurrentThreadId() != python_thread || tick_callback) {
        log_line("REJECT duplicate callback/thread"); return none();
    }
    callback->refs++;
    tick_callback = callback;
    return none();
}
static PyObject *observe_count_action(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    void *descriptor;
    void **vtable;
    if (!packed || packed->size != 8 || GetCurrentThreadId() != python_thread || observed_descriptor) {
        log_line("REJECT count observer arguments/thread"); return none();
    }
    memcpy(&descriptor, packed->data, 8);
    if (!readable(descriptor, 0x38)) { log_line("REJECT count descriptor memory"); return none(); }
    vtable = *(void ***)descriptor;
    if ((unsigned char *)vtable < game || (unsigned char *)vtable >= game + 0x3000000 ||
        vtable[12] != game + (observed_timer ? 0x5fb090 : 0x5f8d50)) {
        log_line("REJECT count descriptor factory"); return none();
    }
    observed_descriptor = descriptor;
    original_descriptor_vtable = vtable;
    original_factory = (void *(*)(void *, void *))vtable[12];
    memcpy(descriptor_vtable, vtable - 1, sizeof(descriptor_vtable));
    descriptor_vtable[13] = (void *)count_factory;
    *(void ***)descriptor = descriptor_vtable + 1;
    log_line(observed_timer ? "TIMER_OBSERVER_READY" : "COUNT_OBSERVER_READY");
    return none();
}
static PyObject *observe_timer_action(PyObject *self, PyObject *arg) {
    if (observed_descriptor) return none();
    observed_timer = 1;
    return observe_count_action(self, arg);
}
static unsigned char *find_component(uint64_t id, unsigned char kind, int entity_kind) {
    uintptr_t view[5], *table, total;
    void *store;
    uint32_t high, index;
    if (!((unsigned char (*)(uint64_t *))(game + 0x5b2320))(&id)) return NULL;
    store = ((void *(*)(unsigned char, int))(game + 0x5c3640))(kind, entity_kind);
    if (!store) return NULL;
    ((void *(*)(void *, void *))(game + 0x5d23b0))(store, view);
    high = (uint32_t)(id >> 32);
    index = (high >> 8) & 0x7fffff;
    table = (uintptr_t *)view[(high & 0x80000000) ? 3 : 1];
    total = view[(high & 0x80000000) ? 4 : 2];
    if (index >= total || !readable(table + index, 8)) return NULL;
    return (unsigned char *)(table[index] & ~(uintptr_t)1);
}
static int native_ai_owner(uint64_t id) {
    unsigned char *owner = find_component(id, 0x61, 0), *player;
    int difficulty;
    if (!readable(owner, 0x20)) return 0;
    player = find_component(*(uint64_t *)(owner + 0x18), 0x81, 2);
    if (!readable(player, 0x48)) return 0;
    difficulty = *(int *)(player + 0x40);
    return difficulty >= 1 && difficulty <= 6;
}
static void release_leases(void) {
    void *manager = *(void **)(game + 0x3389b70);
    unsigned i;
    if (readable(manager, 0x1a8))
        for (i = 0; i < leased_count; i++)
            ((void (*)(void *, uint64_t))(game + 0xd81510))(manager, leased_ids[i]);
    leased_count = 0;
}
static void expire_leases(void) {
    void *manager = *(void **)(game + 0x3389b70);
    unsigned i = 0;
    while (i < leased_count) {
        if (simulation_ticks >= lease_expiry[i] || !native_ai_owner(leased_ids[i])) {
            if (readable(manager, 0x1a8))
                ((void (*)(void *, uint64_t))(game + 0xd81510))(manager, leased_ids[i]);
            leased_count--;
            leased_ids[i] = leased_ids[leased_count];
            lease_expiry[i] = lease_expiry[leased_count];
        } else i++;
    }
}
static PyObject *lease_ai_unit(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    uint64_t id;
    int enabled, status = 0;
    unsigned i;
    void *manager = *(void **)(game + 0x3389b70);
    if (!packed || packed->size != 12 || !in_callback || shutting_down ||
        GetCurrentThreadId() != python_thread || !readable(manager, 0x1a8)) goto done;
    memcpy(&id, packed->data, 8); memcpy(&enabled, packed->data + 8, 4);
    for (i = 0; i < leased_count && leased_ids[i] != id; i++);
    if (enabled) {
        if (!native_ai_owner(id) || (i == leased_count && leased_count >= 4096)) goto done;
        if (i == leased_count) {
            ((void (*)(void *, uint64_t))(game + 0xd814d0))(manager, id);
            leased_ids[leased_count++] = id;
        }
        /* Four simulation seconds at the fixed half-second observer rate.
           The controller must renew; callback failures and world stop release. */
        lease_expiry[i] = simulation_ticks + 8;
    } else if (i < leased_count) {
        ((void (*)(void *, uint64_t))(game + 0xd81510))(manager, id);
        leased_ids[i] = leased_ids[--leased_count];
        lease_expiry[i] = lease_expiry[leased_count];
    }
    status = 1;
done:
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)&status, 4);
}
static PyObject *token_id(PyObject *self, PyObject *arg) {
    PyString *name = string_arg(arg);
    uint32_t token;
    if (!name || name->size < 1 || name->size > 64 || GetCurrentThreadId() != python_thread) return none();
    ((void (*)(void *, const char *))(game + 0x2bb10))(&token, name->data);
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)&token, 4);
}
static PyObject *unit_traits(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    uint64_t id;
    unsigned char *ui, *movement;
    unsigned char output[16];
    uint32_t land;
    if (!packed || packed->size != 8 || !in_callback || GetCurrentThreadId() != python_thread) return none();
    memcpy(&id, packed->data, 8);
    if (!find_component(id, 0x10, 0) || !find_component(id, 0x4d, 0)) return none();
    ui = ((unsigned char *(*)(unsigned char, uint64_t))(game + 0x5c3340))(0x10, id);
    movement = ((unsigned char *(*)(unsigned char, uint64_t))(game + 0x5c3340))(0x4d, id);
    if (!readable(ui, 0x78) || !readable(movement, 0x38)) return none();
    memcpy(output, ui + 0x34, 4);
    memcpy(output + 4, movement + 0x34, 4);
    memcpy(output + 8, movement + 0x30, 4);
    land = find_component(id, 0x5f, 0) != NULL;
    memcpy(output + 12, &land, 4);
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)output, 16);
}
static PyObject *unit_role(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    uint64_t id;
    unsigned char *ui;
    void *text;
    const char *name;
    size_t size;
    if (!packed || packed->size != 8 || !in_callback || GetCurrentThreadId() != python_thread) return none();
    memcpy(&id, packed->data, 8);
    if (!find_component(id, 0x10, 0)) return none();
    ui = ((unsigned char *(*)(unsigned char, uint64_t))(game + 0x5c3340))(0x10, id);
    if (!readable(ui, 0x38)) return none();
    /* UnitRole uses the second typed string table, not generic token interning.
       This is its RTTI property's own serialization path (b1f820). */
    text = ((void *(*)(void *))(game + 0x2c4d0))(ui + 0x34);
    name = ((const char *(*)(void *))(game + 0x57a0))(text);
    if (!readable((void *)name, 64)) return none();
    for (size = 0; size < 63 && name[size]; size++);
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))(name, size);
}
static unsigned activity_flags(uint64_t id) {
    unsigned flags = 0;
    unsigned char *part = find_component(id, 0x88, 0);
    if (readable(part, 0x20) && *(uint64_t *)(part+0x18) != UINT64_MAX) flags |= 1;
    part = find_component(id, 0x89, 0);
    if (readable(part, 0x24) && *(unsigned *)(part+0x20)) flags |= 2;
    part = find_component(id, 0x6e, 0);
    if (readable(part, 0x1b) && (part[0x18] || part[0x19] || part[0x1a])) flags |= 4;
    part = find_component(id, 0x7d, 0);
    if (readable(part, 0x80) && *(uint64_t *)(part+0x78) != UINT64_MAX) flags |= 8;
    if (!find_component(id, 0x90, 0)) flags |= 16;
    /* TGDContrainteOnUnitCategory IsEnCombat (+0x4a) maps to category bit 8
       at 0x633fac. Native filter 0x92dd60 reads module 0x49 + 0x18.
       This is combat state, unlike the explicit-target module 0x7d above. */
    part=find_component(id,0x49,0);
    if (readable(part,0x1c) && (*(uint32_t *)(part+0x18)&8)) flags|=32;
    return flags;
}
static PyObject *unit_activity(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg); uint64_t id; unsigned flags;
    if (!packed || packed->size != 8 || !in_callback || GetCurrentThreadId() != python_thread) return none();
    memcpy(&id, packed->data, 8); flags = activity_flags(id);
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)&flags, 4);
}
static PyObject *unit_transporter(PyObject *self, PyObject *arg) {
    PyString *packed=string_arg(arg); uint64_t id,carrier=UINT64_MAX;
    unsigned char *part;
    if (!packed || packed->size!=8 || !in_callback || GetCurrentThreadId()!=python_thread) return none();
    memcpy(&id,packed->data,8);part=find_component(id,0x88,0);
    if (readable(part,0x20)) carrier=*(uint64_t *)(part+0x18);
    return ((PyObject *(*)(const char *, intptr_t))(game+0x1c55f40))((char *)&carrier,8);
}
static PyObject *fixture_mark_human(PyObject *self, PyObject *arg) {
    PyString *packed=string_arg(arg); uint64_t id;
    unsigned char *owner, *player;
    if (!strstr(GetCommandLineA(),"BattleAtmosphereProbeAutoFixture") || !in_callback ||
        GetCurrentThreadId()!=python_thread || !packed || packed->size!=8) return none();
    memcpy(&id,packed->data,8); owner=find_component(id,0x61,0);
    if (!readable(owner,0x20)) return none();
    player=find_component(*(uint64_t *)(owner+0x18),0x81,2);
    if (!readable(player,0x48) || *(int *)(player+0x40)!=7) return none();
    ((void (*)(void *,int))(game+0x9d63c0))(player,0);
    return none();
}
static PyObject *fixture_mode(PyObject *self, PyObject *unused) {
    char mode[64]; DWORD size;
    if (strstr(GetCommandLineA(),"BattleAtmosphereProbeAutoFixture") && strstr(GetCommandLineA(),"-headless")) {
        size=GetEnvironmentVariableA("BA_FRONT_FIXTURE",mode,sizeof(mode));
        if (size && size<sizeof(mode)) return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))(mode,size);
        return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))("fixture",7);
    }
    return none();
}
static PyObject *fixture_wrap_root(PyObject *self, PyObject *arg) {
    /* The shipped sip.wrapinstance parses `k` into a stack slot then reads a
       64-bit pointer from it. Bypass that width mismatch, only for the explicit
       empty-lobby fixture and this one descriptor type. Never a live-game API. */
    PyString *packed=string_arg(arg);
    unsigned char *root;
    uintptr_t vtable;
    PyObject *module,*dict,*type,*result;
    if (!strstr(GetCommandLineA(),"BattleAtmosphereProbeAutoFixture") ||
        !strstr(GetCommandLineA(),"-headless") || GetCurrentThreadId()!=python_thread ||
        !packed || packed->size!=8) return none();
    memcpy(&root,packed->data,8);
    if (!readable(root,0x80)) return none();
    vtable=(uintptr_t)*(void **)root;
    if (vtable<(uintptr_t)game || vtable>=(uintptr_t)game+0x4000000) return none();
    module=((ImportFn)(game+0x1ca5f80))("_gd_object_specific");
    if (!module) return NULL;
    dict=((PyObject *(*)(PyObject *))(game+0x1c4dee0))(module);
    type=dict?((PyObject *(*)(PyObject *,const char *))(game+0x1c331c0))(
        dict,"TGDDescriptorLaunchEffetStandard"):NULL;
    result=type?((PyObject *(*)(void *,PyObject *,PyObject *))(game+0x1cbc1e0))(root,type,NULL):none();
    decref(module);
    return result;
}
static PyObject *world_navigation(PyObject *self, PyObject *unused) {
    unsigned char *grid = *(unsigned char **)(game + 0x3398250);
    unsigned char *finder = *(unsigned char **)(game + 0x339d870), *mask, *output;
    unsigned width, height, count, kind;
    float cell, ox, oy;
    PyObject *result;
    if (!in_callback || GetCurrentThreadId() != python_thread || !readable(grid, 0x58) ||
        !readable(finder, 0xa8) || *(void **)finder != game + 0x238e850) return none();
    width = *(unsigned *)(grid + 0x24); height = *(unsigned *)(grid + 0x28);
    count = *(unsigned *)(grid + 0x54) + 1;
    cell = *(float *)(grid + 0x20); ox = *(float *)(grid + 0x44); oy = *(float *)(grid + 0x48);
    if (!width || !height || width > 512 || height > 512 || count != width * height ||
        !isfinite(cell) || cell <= 0 || !isfinite(ox) || !isfinite(oy)) return none();
    output = HeapAlloc(GetProcessHeap(), 0, 24 + count * 4);
    if (!output) return none();
    memcpy(output, &width, 4); memcpy(output+4, &height, 4); memcpy(output+8, &cell, 4);
    memcpy(output+12, &ox, 4); memcpy(output+16, &oy, 4); memcpy(output+20, &count, 4);
    for (kind = 0; kind < 4; kind++) {
        mask = *(unsigned char **)(finder + 0x20 + kind * 8);
        if (!readable(mask, 0x10) || *(unsigned *)(mask + 8) < count ||
            !readable(*(void **)mask, count)) { HeapFree(GetProcessHeap(), 0, output); return none(); }
        memcpy(output + 24 + kind * count, *(void **)mask, count);
    }
    result = ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)output, 24 + count * 4);
    HeapFree(GetProcessHeap(), 0, output);
    return result;
}
static PyObject *nav_point(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    unsigned kind;
    uint64_t xy;
    void *navigation;
    int radius, status = -1;
    float x, y;
    if (!packed || packed->size != 12 || !in_callback || GetCurrentThreadId() != python_thread) goto done;
    memcpy(&kind, packed->data, 4); memcpy(&xy, packed->data+4, 8);
    memcpy(&x, packed->data+4, 4); memcpy(&y, packed->data+8, 4);
    if (kind > 3 || !isfinite(x) || !isfinite(y) || fabs(x)>10000000 || fabs(y)>10000000) goto done;
    navigation = ((void *(*)(void))(game + 0x8b12f0))();
    if (!readable(navigation, 0x28)) goto done;
    radius = ((int (*)(unsigned))(game + 0xa17550))(kind);
    status = ((unsigned char (*)(void *, uint64_t, unsigned, int))(game + 0x8b0a80))(navigation, xy, kind, radius);
done:
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)&status, 4);
}
static void log_component_type(unsigned char *component) {
    unsigned char **vtable, *locator, *type;
    uint32_t rva;
    size_t length;
    if (!readable(component, 24)) return;
    vtable = *(unsigned char ***)component;
    if (!readable(vtable - 1, 8)) return;
    locator = vtable[-1];
    if (!readable(locator, 24)) return;
    memcpy(&rva, locator + 12, 4);
    if (rva >= 0x4000000) return;
    type = game + rva + 16;
    if (!readable(type, 200)) return;
    for (length = 0; length < 180 && type[length]; length++);
    log_bytes((char *)type, (DWORD)length);
}
static PyObject *probe_player_state(PyObject *self, PyObject *unused) {
    /* Read-only snapshot of current player descriptors, no control decision. */
    unsigned char *list = *(unsigned char **)(game + 0x3389840), *component;
    uint64_t *ids;
    unsigned char output[32 * (8 + 128)];
    uint32_t size, i, count = 0;
    if (!in_callback || GetCurrentThreadId() != python_thread || !readable(list, 0x30)) return none();
    ids = *(uint64_t **)(list + 0x20);
    size = *(uint32_t *)(list + 0x28);
    if (size > 32 || !readable(ids, size * 8)) return none();
    for (i = 0; i < size; i++) {
        component = find_component(ids[i], 0x81, 2);
        if (!readable(component, 128)) continue;
        log_component_type(component);
        memcpy(output + count * 136, ids + i, 8);
        memcpy(output + count * 136 + 8, component, 128);
        count++;
    }
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)output, count * 136);
}
static PyObject *probe_unit_component_types(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    uint64_t id;
    unsigned kind;
    unsigned char *component;
    char label[40];
    if (!packed || packed->size != 8 || !in_callback || GetCurrentThreadId() != python_thread) return none();
    memcpy(&id, packed->data, 8);
    for (kind = 0; kind < 256; kind++) {
        component = find_component(id, (unsigned char)kind, 0);
        if (!component) continue;
        sprintf(label, "COMPONENT %u VT %lx", kind, (unsigned long)((unsigned char *)*(void **)component - game));
        log_line(label);
        log_component_type(component);
    }
    return none();
}
static PyObject *world_context(PyObject *self, PyObject *unused) {
    /* TScenarioLoadInfo, verified by its registered property offsets.
       Returns path, name, root datapack, category, separated by newlines. */
    void *manager = *(void **)(game + 0x31df6d0);
    unsigned char *info;
    const char *s;
    char output[1024];
    unsigned offsets[4] = {0x18, 0x20, 0x28, 0x30};
    size_t i, j, used = 0;
    if (GetCurrentThreadId() != python_thread || !readable(manager, 0x38)) return none();
    info = ((unsigned char *(*)(void *))(game + 0x379a20))(manager);
    if (!readable(info, 0x50) || *(void **)info != game + 0x223f708) return none();
    for (i = 0; i < 4; i++) {
        s = ((const char *(*)(void *))(game + 0x57a0))(info + offsets[i]);
        if (!readable((void *)s, 256)) return none();
        for (j = 0; j < 255 && s[j]; j++) {
            if ((unsigned char)s[j] < 32 || (unsigned char)s[j] > 126) return none();
            output[used++] = s[j];
        }
        if (s[j]) return none();
        output[used++] = '\n';
    }
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))(output, used);
}
static PyObject *world_unit_snapshot(PyObject *self, PyObject *unused) {
    /* Immutable records <QQiii3f>: entity, owner, alliance, difficulty,
       player index, xyz. Enumerates the world's player unit lists, without
       synthetic Python groups. No control permission is implied. */
    unsigned char *list = *(unsigned char **)(game + 0x3389840);
    unsigned char *player, *unit_list, *owner, *spatial, *output;
    uint64_t *players, *units;
    unsigned char *player_views[32];
    uint64_t *unit_views[32];
    uint32_t sizes[32];
    uint32_t pn, un, i, j, count = 0, capacity = 0;
    PyObject *result;
    if (!in_callback || GetCurrentThreadId() != python_thread || !readable(list, 0x30)) return none();
    players = *(uint64_t **)(list + 0x20);
    pn = *(uint32_t *)(list + 0x28);
    if (pn > 32 || !readable(players, pn * 8)) return none();
    /* Reserve the complete snapshot before iterating. A global 4096-row cut
       silently omitted later owners in large matches. Per-owner bounds stay
       unchanged; at most 32 * 4096 records (5 MiB), on the simulation thread. */
    for (i = 0; i < pn; i++) {
        sizes[i] = 0;
        player = find_component(players[i], 0x81, 2);
        unit_list = find_component(players[i], 0x86, 2);
        if (!readable(player, 0x48) || !readable(unit_list, 0x30)) continue;
        units = *(uint64_t **)(unit_list + 0x18);
        un = *(uint32_t *)(unit_list + 0x20);
        if (un > 4096 || !readable(units, un * 8)) continue;
        player_views[i] = player; unit_views[i] = units; sizes[i] = un;
        capacity += un;
    }
    output = HeapAlloc(GetProcessHeap(), 0, capacity ? capacity * 40 : 1);
    if (!output) return none();
    for (i = 0; i < pn; i++) {
        un = sizes[i];
        if (!un) continue;
        player = player_views[i]; units = unit_views[i];
        for (j = 0; j < un; j++) {
            owner = find_component(units[j], 0x61, 0);
            spatial = find_component(units[j], 0x6b, 0);
            if (!readable(owner, 0x20) || !readable(spatial, 0x3c) ||
                *(uint64_t *)(owner + 0x18) != players[i]) continue;
            memcpy(output + count * 40, units + j, 8);
            memcpy(output + count * 40 + 8, players + i, 8);
            memcpy(output + count * 40 + 16, player + 0x3c, 12);
            memcpy(output + count * 40 + 28, spatial + 0x30, 12);
            count++;
        }
    }
    result = ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)output, count * 40);
    HeapFree(GetProcessHeap(), 0, output);
    return result;
}
static PyObject *world_landmarks(PyObject *self, PyObject *unused) {
    /* Read the mounted current scenario, with no map name/coordinates table.
       TGameDesignDatabase -> items -> typed addons; no world mutation.
       Records <i3fii6f>: type, xy/rotation, alliance, points, start/end xyz.
       Types: 1 command point, 2 deployment, 3 ground reinforcement. */
    uintptr_t path[2] = {0, 0}, *counter;
    unsigned char *db = NULL, **items, *item, *addon, output[512 * 48], *row;
    void *vtable;
    uint32_t total, i, count = 0;
    int kind, alliance, points;
    PyObject *result;
    if (GetCurrentThreadId() != python_thread) return none();
    ((void (*)(void *, const char *))(game + 0x20480))(path, "CurrentScenarioData:/out/LevelDesign.ndfbin");
    ((void (*)(void *, void *))(game + 0x1ed2e0))(&db, path);
    ((void (*)(void *))(game + 0x2cf0))(path);
    if (readable(db, 0x30) && *(void **)db == game + 0x235d8f8) {
        items = *(unsigned char ***)(db + 0x18);
        total = *(uint32_t *)(db + 0x20);
        if (total <= 4096 && readable(items, total * 8)) {
            for (i = 0; i < total && count < 512; i++) {
                item = items[i];
                if (!readable(item, 0x30)) continue;
                addon = *(unsigned char **)(item + 0x28);
                if (!readable(addon, 0x48)) continue;
                vtable = *(void **)addon;
                kind = vtable == game + 0x235d5a8 ? 1 : vtable == game + 0x235d6a8 ? 2 :
                       vtable == game + 0x235d348 ? 3 : 0;
                if (!kind || (kind == 3 && !readable(addon, 0x60))) continue;
                alliance = kind == 1 ? -1 : *(int *)(addon + 0x40);
                points = kind == 1 ? *(int *)(addon + 0x40) : 0;
                row = output + count++ * 48;
                memset(row, 0, 48);
                memcpy(row, &kind, 4);
                memcpy(row + 4, item + 0x18, 12);
                memcpy(row + 16, &alliance, 4);
                memcpy(row + 20, &points, 4);
                if (kind == 3) memcpy(row + 24, addon + 0x48, 24);
            }
        }
    }
    if (db) {
        counter = (uintptr_t *)(db + 8);
        if (!(*counter & 1)) counter = (uintptr_t *)*counter;
        *counter -= 2;
        if (*counter <= 1) ((void (*)(void *, int))(*(void ***)db)[0])(db, 1);
    }
    result = ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)output, count * 48);
    return result;
}
static PyObject *probe_first_unit_state(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    unsigned char *group, *component;
    uint64_t id, *ids;
    uint32_t count, high, index;
    uintptr_t view[5], *table, total;
    void *store;
    if (!packed || packed->size != 8 || GetCurrentThreadId() != python_thread) return none();
    memcpy(&group, packed->data, 8);
    if (!readable(group, 0xa8) || *(void **)group != game + 0x22ce988) return none();
    count = *(uint32_t *)(group + 0x70);
    ids = *(uint64_t **)(group + 0x68);
    if (!count || count > 4096 || !readable(ids, count * 8)) return none();
    id = ids[0];
    if (!((unsigned char (*)(uint64_t *))(game + 0x5b2320))(&id)) return none();
    store = ((void *(*)(unsigned char, int))(game + 0x5c3640))(0x6b, 0);
    if (!store) return none();
    ((void *(*)(void *, void *))(game + 0x5d23b0))(store, view);
    high = (uint32_t)(id >> 32);
    index = (high >> 8) & 0x7fffff;
    table = (uintptr_t *)view[(high & 0x80000000) ? 3 : 1];
    total = view[(high & 0x80000000) ? 4 : 2];
    if (index >= total || !readable(table + index, 8)) return none();
    component = (unsigned char *)(table[index] & ~(uintptr_t)1);
    if (!readable(component, 0x90)) return none();
    /* Diagnostic state of an explicitly owned test group; immutable copy.
       Component kind follows native UnitDansZone, RVA 0x5e4bb0. */
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)component, 0x90);
}
typedef struct { void *data; uint32_t size, pad1, capacity, pad2; } NativeVector;
static PyObject *fixture_load_transport(PyObject *self,PyObject *arg) {
    PyString *packed=string_arg(arg);uint64_t ids[2];int result=-1;
    NativeVector units={0},targets={0};float xyz[3]={0,0,0};uint32_t guid[4]={0};void *command,**vtable;
    if (!packed || packed->size!=16 || !in_callback || GetCurrentThreadId()!=python_thread ||
        !strstr(GetCommandLineA(),"BattleAtmosphereProbeAutoFixture") || !strstr(GetCommandLineA(),"-headless")) goto done;
    memcpy(ids,packed->data,16);
    if (!native_ai_owner(ids[0]) || !native_ai_owner(ids[1]))goto done;
    units.data=&ids[0];units.size=units.capacity=1;
    targets.data=&ids[1];targets.size=targets.capacity=1;
    command=((void *(*)(void *,void *,void *,int,int,int,int,void *))(game+0x8c1c00))(&units,&targets,xyz,0x14,1,0,0,guid);
    if(command){result=((unsigned char (*)(void *))(game+0x8bdb00))(command)?1:0;
        if(!result){vtable=*(void ***)command;((void (*)(void *))vtable[11])(command);}}
done:return ((PyObject *(*)(const char *,intptr_t))(game+0x1c55f40))((char *)&result,4);
}
static PyObject *order_ai_unit(PyObject *arg, int attack_move) {
    PyString *packed = string_arg(arg);
    uint64_t id, player_id;
    unsigned char *owner, *player;
    float xyz[3];
    int difficulty, status = -1, i;
    NativeVector units, positions, targets;
    uint32_t guid[4] = {0,0,0,0};
    void *command, **vtable;
    if (!packed || packed->size != 20) goto done;
    if (!in_callback || shutting_down || GetCurrentThreadId() != python_thread) {status = -2; goto done;}
    memcpy(&id, packed->data, 8);
    memcpy(xyz, packed->data + 8, 12);
    owner = find_component(id, 0x61, 0);
    if (!readable(owner, 0x20)) {status = -5; goto done;}
    player_id = *(uint64_t *)(owner + 0x18);
    player = find_component(player_id, 0x81, 2);
    if (!readable(player, 0x48)) {status = -5; goto done;}
    difficulty = *(int *)(player + 0x40);
    /* Source enumeration: 0 human, 1..6 native AI, 7 scripted. Unknown fails closed. */
    if (difficulty < 1 || difficulty > 6) {status = -3; goto done;}
    if (!find_component(id, 0x5f, 0) || !find_component(id, 0x4d, 0)) {status = -4; goto done;}
    if (attack_move>=2) {
        unsigned activity=activity_flags(id);
        /* Dedicated cargo commands only: never relax ordinary movement guards.
           The current carrier must be loaded; emergency unload permits combat. */
        if (!(activity&2) || (activity & (attack_move==3 ? 5 : 45))) {status=-7;goto done;}
    } else if (activity_flags(id)) {status = -7; goto done;}
    for (i = 0; i < 3; i++) if (!(xyz[i] >= -1e9f && xyz[i] <= 1e9f)) {status = -6; goto done;}
    memset(&units, 0, sizeof(units)); memset(&positions, 0, sizeof(positions));
    units.data = &id; units.size = units.capacity = 1;
    positions.data = xyz; positions.size = positions.capacity = 1;
    if (attack_move) {
        /* GiveOrderStandard::createOrder (0x605f40 -> 0x8c1c00).
           MoveAndAttack enum 0x18: native name mapping 0xc76659..0xc76668.
           Empty targets, explicit xyz, default normal move, nonqueued/nonforced,
           empty GUID. Shared native validation and submit/cleanup below. */
        memset(&targets, 0, sizeof(targets));
        command = ((void *(*)(void *, void *, void *, int, int, int, int, void *))
                   (game + 0x8c1c00))(&units, &targets, xyz, attack_move==2 ? 0x27 : attack_move==3 ? 0x28 : 0x18, 1, 0, 0, guid);
    } else {
        command = ((void *(*)(void *, void *, int, int, int))(game + 0x8c33d0))(&units, &positions, 0, 1, 0);
    }
    if (!command) {status = 0; goto done;}
    status = ((unsigned char (*)(void *))(game + 0x8bdb00))(command) ? 1 : 0;
    if (!status) {vtable = *(void ***)command; ((void (*)(void *))vtable[11])(command);}
done:
    return ((PyObject *(*)(const char *, intptr_t))(game + 0x1c55f40))((char *)&status, 4);
}
static PyObject *move_ai_unit(PyObject *self, PyObject *arg) { return order_ai_unit(arg, 0); }
static PyObject *attack_move_ai_unit(PyObject *self, PyObject *arg) { return order_ai_unit(arg, 1); }
/* Enum evidence: UnloadAtPosition=0x27 at c7680c; UnloadFromTransport=0x28 at c76828. */
static PyObject *unload_at_ai_unit(PyObject *self, PyObject *arg) { return order_ai_unit(arg, 2); }
static PyObject *unload_now_ai_unit(PyObject *self, PyObject *arg) { return order_ai_unit(arg, 3); }
static PyObject *move_probe_group(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    unsigned char *group;
    NativeVector units, positions;
    float xyz[3];
    uint64_t *ids;
    void *command;
    void **vtable;
    unsigned char accepted;
    unsigned i;
    if (!packed || packed->size != 20 || !in_callback || GetCurrentThreadId() != python_thread) {
        log_line("REJECT move outside simulation callback"); return none();
    }
    memcpy(&group, packed->data, 8);
    memcpy(xyz, packed->data + 8, 12);
    if (!readable(group, 0xa8) || *(void **)group != game + 0x22ce988) return none();
    memset(&units, 0, sizeof(units));
    memset(&positions, 0, sizeof(positions));
    units.data = *(void **)(group + 0x68);
    units.size = units.capacity = *(uint32_t *)(group + 0x70);
    if (!units.size || units.size > 64 || !readable(units.data, units.size * 8)) return none();
    ids = units.data;
    for (i = 0; i < units.size; i++)
        if (!((unsigned char (*)(uint64_t *))(game + 0x5b2320))(ids + i)) return none();
    for (i = 0; i < 3; i++) if (!(xyz[i] >= -1e9f && xyz[i] <= 1e9f)) return none();
    positions.data = xyz;
    positions.size = positions.capacity = 1;
    /* Same factory and submit/cleanup path as TGDDescriptorMoveUnitGroup,
       nonblocking, no forced road, no loop. Engine performs order validation. */
    command = ((void *(*)(void *, void *, int, int, int))(game + 0x8c33d0))(&units, &positions, 0, 1, 0);
    if (!command) return none();
    accepted = ((unsigned char (*)(void *))(game + 0x8bdb00))(command);
    if (!accepted) {
        vtable = *(void ***)command;
        ((void (*)(void *))vtable[11])(command);
    }
    log_line(accepted ? "DYNAMIC_MOVE_ACCEPTED" : "DYNAMIC_MOVE_REJECTED");
    return none();
}
static PyObject *set_probe_position(PyObject *self, PyObject *arg) {
    /* Typed, same-thread edit of a Python-owned synthetic tag only.
       Native TGDTagPosition::GetPosition at 0x14d970 returns object+0x38.
       SIP shadow constructor at 0x6c8210 uses vtable 0x22cd318. */
    PyString *packed = string_arg(arg);
    unsigned char *tag;
    float xyz[3], direction[3] = {1.0f, 0.0f, 0.0f};
    int i;
    if (!packed || packed->size != 20 || GetCurrentThreadId() != python_thread) {
        log_line("REJECT position arguments/thread"); return none();
    }
    memcpy(&tag, packed->data, 8);
    memcpy(xyz, packed->data + 8, 12);
    if (!readable(tag, 0x58) || *(void **)tag != game + 0x22cd318) {
        log_line("REJECT position tag type"); return none();
    }
    for (i = 0; i < 3; i++) if (!(xyz[i] >= -1e9f && xyz[i] <= 1e9f)) {
        log_line("REJECT position coordinate"); return none();
    }
    memcpy(tag + 0x38, xyz, 12);
    memcpy(tag + 0x44, direction, 12);
    return none();
}
static PyObject *start_script(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    void *descriptor, *vtable;
    if (!packed || packed->size != 8 || GetCurrentThreadId() != python_thread || script_handle[0]) {
        log_line("REJECT start arguments, thread, or duplicate start");
        return none();
    }
    memcpy(&descriptor, packed->data, 8);
    if (!readable(descriptor, 40)) { log_line("REJECT descriptor memory"); return none(); }
    vtable = *(void **)descriptor;
    if ((unsigned char *)vtable < game || (unsigned char *)vtable >= game + 0x4000000) {
        log_line("REJECT descriptor vtable"); return none();
    }
    log_line("START_SCRIPT begin");
    ((void (*)(void *, void *, void *))(game + 0x5dafe0))(script_handle, descriptor, NULL);
    ((void (*)(void *))(game + 0x5db0d0))(script_handle);
    log_line("START_SCRIPT returned");
    return none();
}
static PyObject *attach_update(PyObject *self, PyObject *arg) {
    PyString *packed = string_arg(arg);
    unsigned char *interface, *owner, *parent;
    void *descriptor, **vtable;
    if (!packed || packed->size != 8 || GetCurrentThreadId() != python_thread || script_handle[0]) return none();
    interface = *(unsigned char **)(game + 0x33896f8);
    if (!interface) return none();
    owner = interface - 0x70;
    if (!readable(owner, 0xd8)) return none();
    parent = *(unsigned char **)(owner + 0x98);
    if (!readable(parent, 0x50)) return none();
    memcpy(&descriptor, packed->data, 8);
    if (!readable(descriptor, 0x28)) return none();
    vtable = *(void ***)descriptor;
    if ((unsigned char *)vtable < game || (unsigned char *)vtable >= game + 0x3000000) return none();
    ((void (*)(void *, void *, void *))(game + 0x5dafe0))(script_handle, descriptor, NULL);
    attached_action = ((void *(*)(void *, void *))vtable[12])(descriptor, parent);
    attached_mode = 1;
    ((void (*)(void *, void *))(game + 0x5dba80))(attached_action, owner);
    log_line("UPDATE_ATTACHED_TO_EXISTING_WORLD");
    return none();
}
static PyObject *finish_script(PyObject *self, PyObject *unused) {
    /* Match BOTH TLaunchGDScript stop (slot 12) and handle release (slot 10).
       Releasing the descriptor without stopping its GD owner leaves actions
       alive during world teardown. */
    void *descriptor = script_handle[0];
    uintptr_t *count, indirect;
    if (GetCurrentThreadId() != python_thread) { log_line("REJECT cleanup thread"); return none(); }
    if (attached_mode && attached_action) {
        log_line("DEFER_UPDATE_RELEASE until native owner stops");
        return none();
    }
    if (descriptor && !attached_mode) ((void (*)(void *))(game + 0x5db010))(script_handle);
    attached_mode = 0;
    if (observed_descriptor) {
        *(void ***)observed_descriptor = original_descriptor_vtable;
        observed_descriptor = NULL;
    }
    decref(tick_callback);
    tick_callback = NULL;
    script_handle[0] = script_handle[1] = NULL;
    if (descriptor) {
        count = (uintptr_t *)((char *)descriptor + 0x18);
        indirect = *count;
        if (!(indirect & 1)) count = (uintptr_t *)indirect;
        *count -= 2;
        if (*count <= 1) {
            void *base = (char *)descriptor + 0x10;
            void **vtable = *(void ***)base;
            ((void (*)(void *, int))vtable[0])(base, 1);
        }
    }
    log_line("TERMINATE_SCRIPT");
    return none();
}
static PyObject *diagnostic_exit(PyObject *self, PyObject *unused) {
    log_line("DIAGNOSTIC_EXIT_73 (not a completed game lifecycle)");
    ExitProcess(73);
    return NULL;
}
static Method methods[] = {
    {"log", bridge_log, 8, "Write bounded probe text to inherited stdout."},
    {"set_probe_position", set_probe_position, 8, "Set a synthetic Python-owned position tag in the test world."},
    {"set_tick_callback", set_tick_callback, 8, "Register one simulation-thread diagnostic callback."},
    {"observe_count_action", observe_count_action, 8, "Observe the owned native group-count action after execution."},
    {"observe_timer_action", observe_timer_action, 8, "Observe completion of a timer without creating late world variables."},
    {"probe_first_unit_state", probe_first_unit_state, 8, "Read a bounded copy of the test group's first unit spatial component."},
    {"probe_player_state", probe_player_state, 4, "Read current player identity data for ownership research, without issuing orders."},
    {"probe_unit_component_types", probe_unit_component_types, 8, "List component type names on a live test entity for ABI research."},
    {"world_context", world_context, 4, "Read the current engine scenario identity and category."},
    {"world_unit_snapshot", world_unit_snapshot, 4, "Read player-owned live units without synthetic group handles."},
    {"world_landmarks", world_landmarks, 4, "Read the current scenario's command, deployment and reinforcement points."},
    {"move_probe_group", move_probe_group, 8, "Submit a validated nonblocking move during the test simulation callback."},
    {"move_ai_unit", move_ai_unit, 8, "Submit a move only for a live ground unit owned by a native AI player; return explicit status."},
    {"attack_move_ai_unit", attack_move_ai_unit, 8, "Native MoveAndAttack for an eligible AI ground unit."},
    {"lease_ai_unit", lease_ai_unit, 8, "Research-only bounded native strategic exclusion; release explicitly and on shutdown."},
    {"token_id", token_id, 8, "Resolve a bounded native token name."},
    {"unit_traits", unit_traits, 8, "Read a live unit's native role, pathfinding class, speed and land capability."},
    {"unit_role", unit_role, 8, "Read the role name through its registered property string table."},
    {"unit_activity", unit_activity, 8, "Conservative exclusion flags for transport, rout state, target and armament."},
    {"unit_transporter", unit_transporter, 8, "Read the loaded unit's carrier identity, or UINT64_MAX."},
    {"fixture_load_transport", fixture_load_transport, 8, "Isolated headless fixture only: native boarding command."},
    {"unload_at_ai_unit", unload_at_ai_unit, 8, "Native AI ground carrier unload-at-position; separate loaded-unit safeguards."},
    {"unload_now_ai_unit", unload_now_ai_unit, 8, "Native AI ground carrier emergency unload."},
    {"fixture_mark_human", fixture_mark_human, 8, "Isolated empty-lobby identity test only; never used in normal games."},
    {"fixture_mode", fixture_mode, 4, "True only in the explicitly requested isolated headless fixture."},
    {"fixture_wrap_root", fixture_wrap_root, 8, "64-bit typed SIP wrapper for the isolated fixture root only."},
    {"world_navigation", world_navigation, 4, "Copy current strategic navigation masks and grid geometry."},
    {"nav_point", nav_point, 8, "Check a point with the native tactical navigation predicate for its movement class."},
    {"start_script", start_script, 8, "Start one retained native descriptor in this isolated process."},
    {"attach_update", attach_update, 8, "Attach a periodic action to the existing native GD owner, without reinitializing the world."},
    {"finish_script", finish_script, 4, "Release the probe descriptor handle."},
    {"diagnostic_exit", diagnostic_exit, 4, "Exit ONLY this headless diagnostic with code 73."},
    {NULL, NULL, 0, NULL}
};
#ifdef BA_EMBEDDED
static PyObject *load_embedded_module(const char *name, const char *source) {
    PyObject *module = NULL, *dict, *code = NULL, *modules, *builtins, *result;
    void *node;
    /* Use the same Python grammar/compiler/evaluator present in the engine.
       Retail deliberately omits the public compile/eval builtins. */
    node = ((void *(*)(const char *, int, int))(game + 0x1cb3020))(source, 257, 0);
    if (!node) {log_line("EMBED_PARSE_ERROR"); goto done;}
    code = ((PyObject *(*)(void *, const char *))(game + 0x1c96b60))(node, name);
    ((void (*)(void *))(game + 0x1c84050))(node);
    if (!code) {log_line("EMBED_COMPILE_ERROR"); goto done;}
    module = ((PyObject *(*)(const char *))(game + 0x1c4de10))(name);
    if (!module) goto done;
    dict = ((PyObject *(*)(PyObject *))(game + 0x1c4dee0))(module);
    builtins = ((PyObject *(*)(void))(game + 0x1c94d70))();
    if (!dict || !builtins || ((int (*)(PyObject *, const char *, PyObject *))(game + 0x1c33210))(
        dict, "__builtins__", builtins) < 0) goto fail;
    result = ((PyObject *(*)(PyObject *, PyObject *, PyObject *))(game + 0x1c8f3c0))(code, dict, dict);
    if (!result) {log_line("EMBED_EVAL_ERROR"); goto fail;}
    decref(result);
    modules = ((PyObject *(*)(void))(game + 0x1ca5530))();
    if (!modules || ((int (*)(PyObject *, const char *, PyObject *))(game + 0x1c33210))(
        modules, name, module) < 0) goto fail;
    log_line("EMBEDDED_MODULE_LOADED"); log_line(name);
    goto done;
fail:
    decref(module); module = NULL;
done:
    if (!module) log_python_error();
    decref(code);
    return module;
}
#endif
static int ensure_native_module(void) {
    if (!module_ready) {
        PyObject *module;
        python_thread = GetCurrentThreadId();
        module = ((InitFn)(game + 0x1ca9980))("_ba_native", methods,
                   "Build-pinned skirmish runtime bridge", NULL, 1013);
        module_ready = module != NULL;
        log_line(module_ready ? "MODULE_REGISTERED" : "MODULE_REGISTRATION_FAILED");
    }
    return module_ready;
}
static PyObject *import_shim(const char *name) {
#ifdef BA_EMBEDDED
    {
        unsigned i;
        for (i = 0; embedded_modules[i].name; i++)
            if (!strcmp(name, embedded_modules[i].name)) {
                /* Every embedded entry may import _ba_native. Register before
                   evaluating any of them, including the first cold import.
                   The headless fixture must never be a startup dependency. */
                if (!ensure_native_module()) return NULL;
                return load_embedded_module(name, embedded_modules[i].source);
            }
    }
#endif
    if ((!strcmp(name, "ba_probe") || !strcmp(name, "ba_autorun") || !strcmp(name, "ba_fixture"))
        && !ensure_native_module()) return NULL;
    return ((ImportFn)(game + 0x1ca5f80))(name);
}
#ifdef BA_PROXY
static void lobby_capacity_selftest(void);
#endif
static void automatic_load(void *launcher) {
    PyObject *module, *dict, *entry, *result;
#ifdef BA_PROXY
    automatic_enabled = ba_allowed();
    if (automatic_enabled) open_runtime_log();
    lobby_capacity_selftest();
#endif
    ((void (*)(void *))(game + 0xc24020))(launcher);
#ifdef BA_PROXY
    if (!automatic_enabled) return;
#endif
    /* Explicit test-only empty-lobby provisioning; never called by the
       regular automatic hook and never bundled as a production roster. */
    if (!strstr(GetCommandLineA(), "BattleAtmosphereProbeAutoFixture")) return;
    ((void (*)(void *))(game + 0x4bff0))(game + 0x3389610);
    python_thread = GetCurrentThreadId();
    module = import_shim("ba_fixture");
    if (module) {
        dict = ((PyObject *(*)(PyObject *))(game + 0x1c4dee0))(module);
        entry = dict ? ((PyObject *(*)(PyObject *, const char *))(game + 0x1c331c0))(dict, "prepare") : NULL;
        if (entry) {
            result = ((PyObject *(*)(PyObject *, PyObject *))(game + 0x1c24ff0))(entry, NULL);
            decref(result);
        }
        decref(module);
    }
    if (((PyObject *(*)(void))(game + 0x1ca00c0))()) {
        log_line("FIXTURE_PREPARE_ERROR");
        ((void (*)(int))(game + 0x1cb22f0))(0);
        ((void (*)(void))(game + 0x1ca05a0))();
    }
    ((void (*)(void *))(game + 0x4c000))(game + 0x3389610);
}

static void automatic_start(void *launcher) {
    PyObject *context, *module, *dict, *entry;
    PyString *packed;
    /* Preserve the real native launcher, roster, rules and root descriptor. */
    log_line("NATIVE_LAUNCH_START");
    shutting_down = 0;
    simulation_ticks = 0;
    ((void (*)(void *))(game + 0xc244e0))(launcher);
#ifdef BA_PROXY
    if (!automatic_enabled) return;
#endif
    /* Read the same multiplayer state as the game's crash-context reporter.
       Single-player skirmish is the only supported execution scope. */
    if (game[0x31783b0] || strstr(GetCommandLineA(),"-replay")) {
        log_line("SKIP_NETWORK_OR_REPLAY"); return;
    }
    ((void (*)(void *))(game + 0x4bff0))(game + 0x3389610);
    python_thread = GetCurrentThreadId();
    context = world_context(NULL, NULL);
    packed = string_arg(context);
    if (automatic_wrapper || !packed || packed->size < 9 ||
        memcmp(packed->data + packed->size - 9, "Skirmish\n", 9)) {
        decref(context);
        ((void (*)(void *))(game + 0x4c000))(game + 0x3389610);
        return;
    }
    log_line("AUTOMATIC_SKIRMISH_ENTRY");
    log_bytes(packed->data, (DWORD)packed->size);
    decref(context);
#ifdef BA_EMBEDDED
    module = import_shim("ba_allocator");
    if (!module) {log_python_error(); ((void (*)(void *))(game+0x4c000))(game+0x3389610);return;}
    decref(module);
    module = import_shim("ba_front");
    if (!module) {log_python_error(); ((void (*)(void *))(game+0x4c000))(game+0x3389610);return;}
    decref(module);
    module = import_shim("ba_transport");
    if (!module) {log_python_error(); ((void (*)(void *))(game+0x4c000))(game+0x3389610);return;}
    decref(module);
    module = import_shim("ba_tactics");
    if (!module) {log_python_error(); ((void (*)(void *))(game+0x4c000))(game+0x3389610);return;}
    decref(module);
    module = import_shim("ba_space");
    if (!module) {log_python_error(); ((void (*)(void *))(game+0x4c000))(game+0x3389610);return;}
    decref(module);
#endif
    module = import_shim("ba_autorun");
    if (module) {
        dict = ((PyObject *(*)(PyObject *))(game + 0x1c4dee0))(module);
        entry = dict ? ((PyObject *(*)(PyObject *, const char *))(game + 0x1c331c0))(dict, "launch") : NULL;
        if (entry) automatic_wrapper = ((PyObject *(*)(PyObject *, PyObject *))(game + 0x1c24ff0))(entry, NULL);
        if (automatic_wrapper) automatic_launcher = launcher;
        decref(module);
    }
    if (((PyObject *(*)(void))(game + 0x1ca00c0))()) {
        log_line("AUTOMATIC_ENTRY_ERROR");
        ((void (*)(int))(game + 0x1cb22f0))(0);
        ((void (*)(void))(game + 0x1ca05a0))();
    }
    ((void (*)(void *))(game + 0x4c000))(game + 0x3389610);
}
static void automatic_stop(void *launcher) {
    PyObject *result;
    /* Stop the owning native action tree before releasing Python-owned
       descriptors referenced by its children. Never create a second world. */
    shutting_down = 1;
    release_leases();
    ((void (*)(void *))(game + 0xc24580))(launcher);
    attached_action = NULL;
    if (launcher == automatic_launcher && automatic_wrapper) {
        ((void (*)(void *))(game + 0x4bff0))(game + 0x3389610);
        python_thread = GetCurrentThreadId();
        result = ((PyObject *(*)(PyObject *, const char *, const char *))(game + 0x1c21420))(
            automatic_wrapper, "TerminateScript", NULL);
        decref(result);
        if (((PyObject *(*)(void))(game + 0x1ca00c0))()) {
            log_line("AUTOMATIC_STOP_ERROR");
            ((void (*)(int))(game + 0x1cb22f0))(0);
            ((void (*)(void))(game + 0x1ca05a0))();
            decref(finish_script(NULL, NULL));
        }
        decref(automatic_wrapper);
        automatic_wrapper = NULL;
        automatic_launcher = NULL;
        log_line("AUTOMATIC_SKIRMISH_STOP");
        ((void (*)(void *))(game + 0x4c000))(game + 0x3389610);
    }
}

#include "fx_budget.h"
#include "skirmish_lobby.h"
#include "lobby_selftest.h"

static int install(void) {
    unsigned char *site, *relay = NULL;
    unsigned char expected[] = {0xe8, 0x51, 0x17, 0x08, 0x01};
    unsigned char jump[] = {0xff, 0x25, 0, 0, 0, 0};
    DWORD old, ignored;
    uintptr_t address, origin;
    intptr_t delta;
    int32_t relative;
    const char *cmd = GetCommandLineA();
#ifndef BA_PROXY
    if (!strstr(cmd, "-headless") || !strstr(cmd, "-noautologin") ||
        !strstr(cmd, "-noMod") || !strstr(cmd, "BattleAtmosphereProbe")) return 0;
#else
    /* Only install a minimal native lifecycle wrapper here. Full file hash,
       mod activation and opt-in configuration are checked outside DllMain. */
#endif
    if (sizeof(PyObject) != 16 || offsetof(PyString, data) != 29 || sizeof(Method) != 32) return 0;
    game = (unsigned char *)GetModuleHandleA(NULL);
    {
        IMAGE_DOS_HEADER *dos=(IMAGE_DOS_HEADER *)game;
        IMAGE_NT_HEADERS64 *pe;
        if (!readable(game,sizeof(*dos)) || dos->e_magic!=IMAGE_DOS_SIGNATURE || dos->e_lfanew<0 || dos->e_lfanew>4096) return 0;
        pe=(IMAGE_NT_HEADERS64 *)(game+dos->e_lfanew);
        if (!readable(pe,sizeof(*pe)) || pe->Signature!=IMAGE_NT_SIGNATURE ||
            pe->FileHeader.TimeDateStamp!=0x6a8405c0 || pe->OptionalHeader.SizeOfImage!=0x3e1e000) return 0;
    }
#ifdef BA_PROXY
    if (!fx_budget_install()) log_line("FX_BUDGET_HOOK_REFUSED");
    if (!lobby_capacity_install()) log_line("SKIRMISH_CAPACITY_HOOK_REFUSED");
#endif
    if (
#ifdef BA_PROXY
        1
#else
        strstr(cmd, "BattleAtmosphereProbeAuto")
#endif
    ) {
        void **vtable = (void **)(game + 0x235e118);
        if (!readable(vtable, 13 * sizeof(void *))) return 0;
        if (vtable[9] != game + 0xc24020 || vtable[11] != game + 0xc244e0 || vtable[12] != game + 0xc24580) return 0;
        if (!VirtualProtect(vtable + 9, 32, PAGE_READWRITE, &old)) return 0;
        vtable[9] = automatic_load;
        vtable[11] = automatic_start;
        vtable[12] = automatic_stop;
        VirtualProtect(vtable + 9, 32, old, &ignored);
        log_line("AUTOMATIC_HOOK_READY");
        return 1;
    }
    site = game + 0xc2482a;
    if (memcmp(site, expected, sizeof(expected))) { log_line("REFUSE unknown callsite"); return 0; }
    origin = (uintptr_t)site & ~(uintptr_t)0xffff;
    for (delta = 0x10000; delta < 0x70000000 && !relay; delta += 0x10000) {
        address = origin + delta;
        relay = VirtualAlloc((void *)address, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    }
    if (!relay) { log_line("REFUSE relay allocation"); return 0; }
    memcpy(relay, jump, 6);
    *(void **)(relay + 6) = (void *)import_shim;
    if (!VirtualProtect(relay, 4096, PAGE_EXECUTE_READ, &old)) return 0;
    relative = (int32_t)(relay - (site + 5));
    if (!VirtualProtect(site, 5, PAGE_EXECUTE_READWRITE, &old)) return 0;
    memcpy(site + 1, &relative, 4);
    VirtualProtect(site, 5, old, &ignored);
    FlushInstructionCache(GetCurrentProcess(), site, 5);
    log_line("CALLSITE_READY");
    return 1;
}
#ifdef BA_PROXY
int ba_startup(void) { return install(); }
#else
BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        return install();
    }
    return TRUE;
}
#endif
