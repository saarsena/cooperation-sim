#ifndef RELATIONSHIPS_CORE_WORLD_H
#define RELATIONSHIPS_CORE_WORLD_H

#include "flecs.h"
#include "core/config.h"

extern ECS_COMPONENT_DECLARE(Config);

typedef struct SimState {
    int  current_tick;
    long ventures_attempted;
    long ventures_succeeded;
    long ventures_failed;
    long births;
    long deaths;
    int  peak_population;
} SimState;

extern ECS_COMPONENT_DECLARE(SimState);

void world_register_singletons(ecs_world_t *world);
void world_set_config(ecs_world_t *world, const Config *cfg);

const Config  *world_cfg(const ecs_world_t *world);
SimState      *world_state(ecs_world_t *world);

#endif
