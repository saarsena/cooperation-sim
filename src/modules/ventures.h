#ifndef RELATIONSHIPS_MODULES_VENTURES_H
#define RELATIONSHIPS_MODULES_VENTURES_H

#include "flecs.h"

void VenturesModuleImport(ecs_world_t *world);
#define VenturesModule VenturesModuleImport

/* Per-tick venture flow counters. Filled with the count of ventures since
   the last call and reset to 0:
     - total: every completed venture (existing or new pair)
     - on_existing: ventures where a relationship already existed (refresh)
     - on_strong:   subset of on_existing where the prior trust was >= 0.5
   Used by per-tick metrics to compute strong-edge-specific refresh rate. */
void ventures_consume_per_tick_counters(long *total, long *on_existing, long *on_strong);

#endif
