#ifndef RELATIONSHIPS_OUTPUT_FINAL_SUMMARY_H
#define RELATIONSHIPS_OUTPUT_FINAL_SUMMARY_H

#include "flecs.h"
#include "core/config.h"

void final_summary_write(ecs_world_t *world, const Config *cfg, const char *path);

#endif
