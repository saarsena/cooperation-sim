#include "output/output.h"
#include "output/event_log.h"
#include "output/per_tick_metrics.h"
#include "output/snapshots.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static int mkdir_p(const char *path) {
    char buf[768];
    size_t n = strlen(path);
    if (n + 1 > sizeof buf) return -1;
    memcpy(buf, path, n + 1);

    for (size_t i = 1; i < n; i++) {
        if (buf[i] == '/') {
            buf[i] = '\0';
            if (mkdir(buf, 0755) != 0 && errno != EEXIST) return -1;
            buf[i] = '/';
        }
    }
    if (mkdir(buf, 0755) != 0 && errno != EEXIST) return -1;
    return 0;
}

int output_open(const Config *cfg) {
    struct stat sb;
    if (stat(cfg->output_dir, &sb) == 0) {
        fprintf(stderr, "output error: '%s' already exists — rename or delete it first\n",
                cfg->output_dir);
        return -1;
    }
    if (mkdir_p(cfg->output_dir) != 0) {
        fprintf(stderr, "output error: cannot create '%s': %s\n",
                cfg->output_dir, strerror(errno));
        return -1;
    }

    char path[768];

    snprintf(path, sizeof path, "%s/metrics.csv", cfg->output_dir);
    if (per_tick_metrics_open(path) != 0) {
        fprintf(stderr, "output error: cannot open %s\n", path);
        return -1;
    }

    snprintf(path, sizeof path, "%s/events.log", cfg->output_dir);
    if (event_log_open(path, cfg->log_events) != 0) {
        fprintf(stderr, "output error: cannot open %s\n", path);
        return -1;
    }

    snprintf(path, sizeof path, "%s/snapshots", cfg->output_dir);
    if (mkdir(path, 0755) != 0 && errno != EEXIST) {
        fprintf(stderr, "output error: cannot create %s\n", path);
        return -1;
    }
    if (snapshots_init(path) != 0) {
        return -1;
    }

    return 0;
}

void output_close(void) {
    per_tick_metrics_close();
    event_log_close();
}

void output_register_systems(ecs_world_t *world) {
    per_tick_metrics_register(world);
    snapshots_register(world);
}
