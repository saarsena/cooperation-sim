#ifndef RELATIONSHIPS_OUTPUT_SNAPSHOTS_H
#define RELATIONSHIPS_OUTPUT_SNAPSHOTS_H

#include "flecs.h"

int  snapshots_init(const char *dir);
void snapshots_register(ecs_world_t *world);

#endif
