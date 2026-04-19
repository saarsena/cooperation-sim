#include "output/event_log.h"

#include <stdio.h>

static FILE *g_fp = NULL;
static int   g_enabled = 0;

int event_log_open(const char *path, int enabled) {
    g_enabled = enabled;
    if (!enabled) return 0;
    g_fp = fopen(path, "w");
    if (!g_fp) return -1;
    fprintf(g_fp, "tick\tkind\tagent_a\tagent_b\tvalue\n");
    return 0;
}

void event_log_close(void) {
    if (g_fp) {
        fclose(g_fp);
        g_fp = NULL;
    }
}

void event_log_write(int tick, const char *kind,
                     ecs_entity_t a, ecs_entity_t b, float value) {
    if (!g_enabled || !g_fp) return;
    fprintf(g_fp, "%d\t%s\t%llu\t%llu\t%.6f\n",
            tick, kind,
            (unsigned long long)a, (unsigned long long)b,
            (double)value);
}
