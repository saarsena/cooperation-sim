#ifndef RELATIONSHIPS_OUTPUT_PER_TICK_METRICS_H
#define RELATIONSHIPS_OUTPUT_PER_TICK_METRICS_H

#include "flecs.h"

int  per_tick_metrics_open(const char *path);
void per_tick_metrics_close(void);

void per_tick_metrics_register(ecs_world_t *world);

#endif
