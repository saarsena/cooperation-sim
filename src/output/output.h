#ifndef RELATIONSHIPS_OUTPUT_OUTPUT_H
#define RELATIONSHIPS_OUTPUT_OUTPUT_H

#include "flecs.h"
#include "core/config.h"

/* Create the output dir (fails if it exists), open all output file handles. */
int  output_open(const Config *cfg);
void output_close(void);

/* Register per-tick and snapshot systems. Must run after modules that
   define the components being observed. */
void output_register_systems(ecs_world_t *world);

#endif
