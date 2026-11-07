/* Revision 201602 only. Included after native memory/logging helpers.
 * Keep the stock watchdog and its quality scaling. Change the deserialized
 * MaxParticles field, not the unrelated exposed MaxParticleCount constant.
 * No original EXE/archive edits, no change to AI or particle lifetimes.
 */
#ifdef BA_PROXY
static DWORD fx_budget_last_log;
static void fx_budget_tick(void *watchdog) {
    unsigned char *w = watchdog;
    DWORD now = GetTickCount();
    if ((DWORD)(now - fx_budget_last_log) >= 10000) {
        char line[192];
        fx_budget_last_log = now;
        float quality = ((float (*)(void *))(game + 0xc1ff70))(w);
        float count = *(float *)(game + 0x33a2494);
        sprintf(line, "FX_BUDGET_STATUS particles=%.0f effective_limit=%.0f max_particles=%u",
                count, quality * *(unsigned *)(w + 0x18), *(unsigned *)(w + 0x18));
        log_line(line);
    }
    ((void (*)(void *))(game + 0xc1fba0))(watchdog);
}
static void fx_budget_initialize(void *watchdog) {
    unsigned char *w = watchdog, *timer;
    ((void (*)(void *))(game + 0xc1fa90))(watchdog);
    if (!ba_allowed()) return;
    open_runtime_log();
    if (!readable(w, 0x68) || *(void **)w != game + 0x235cdc8 ||
        *(unsigned *)(w + 0x18) != 80000) {
        log_line("FX_BUDGET_REFUSE unexpected watchdog type or original limit");
        return;
    }
    *(unsigned *)(w + 0x18) = 320000;
    timer = *(unsigned char **)(w + 0x40);
    if (readable(timer, 0x70) && *(void **)(timer + 0x58) == w &&
        *(void **)(timer + 0x60) == game + 0xc1fba0) {
        *(void **)(timer + 0x60) = fx_budget_tick;
        log_line("FX_BUDGET_APPLIED original=80000 max_particles=320000 quality_scaled=1 telemetry=1");
    } else {
        log_line("FX_BUDGET_APPLIED original=80000 max_particles=320000 quality_scaled=1 telemetry=0");
    }
}
static int fx_budget_install(void) {
    void **slot = (void **)(game + 0x235cdf8);
    DWORD old, ignored;
    if (!readable(slot, 8) || *slot != game + 0xc1fa90) return 0;
    if (!VirtualProtect(slot, 8, PAGE_READWRITE, &old)) return 0;
    *slot = fx_budget_initialize;
    VirtualProtect(slot, 8, old, &ignored);
    log_line("FX_BUDGET_HOOK_READY multiplier=4");
    return 1;
}
#endif
