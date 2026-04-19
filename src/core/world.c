#include "core/world.h"

#include <string.h>

ECS_COMPONENT_DECLARE(Config);
ECS_COMPONENT_DECLARE(SimState);

void world_register_singletons(ecs_world_t *world) {
    ECS_COMPONENT_DEFINE(world, Config);
    ECS_COMPONENT_DEFINE(world, SimState);

    SimState s = {0};
    ecs_singleton_set_ptr(world, SimState, &s);
}

void world_set_config(ecs_world_t *world, const Config *cfg) {
    ecs_singleton_set_ptr(world, Config, (void *)cfg);
}

const Config *world_cfg(const ecs_world_t *world) {
    return ecs_singleton_get(world, Config);
}

SimState *world_state(ecs_world_t *world) {
    return ecs_singleton_ensure(world, SimState);
}
