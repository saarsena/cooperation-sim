#ifndef RELATIONSHIPS_MODULES_VENTURES_H
#define RELATIONSHIPS_MODULES_VENTURES_H

#include "flecs.h"

void VenturesModuleImport(ecs_world_t *world);
#define VenturesModule VenturesModuleImport

#endif
