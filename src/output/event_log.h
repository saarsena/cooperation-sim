#ifndef RELATIONSHIPS_OUTPUT_EVENT_LOG_H
#define RELATIONSHIPS_OUTPUT_EVENT_LOG_H

#include "flecs.h"

/* When enabled == 0, no file is created and subsequent writes are no-ops. */
int  event_log_open(const char *path, int enabled);
void event_log_close(void);

/* value is unused (pass 0) for kinds that don't carry one. */
void event_log_write(int tick, const char *kind,
                     ecs_entity_t a, ecs_entity_t b, float value);

#endif
