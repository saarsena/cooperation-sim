#ifndef RELATIONSHIPS_OUTPUT_EVENT_LOG_H
#define RELATIONSHIPS_OUTPUT_EVENT_LOG_H

#include "flecs.h"

/* When enabled == 0, no file is created and subsequent writes are no-ops. */
int  event_log_open(const char *path, int enabled);
void event_log_close(void);

/* value is unused (pass 0) for kinds that don't carry one.
   place_id is the witness-world place index in [0, PLACES_COUNT) for events
   that happen at a place; pass -1 for everything else (births, deaths,
   relationship cascades). The column is written even when places_enabled=0
   so the format is stable. */
void event_log_write(int tick, const char *kind,
                     ecs_entity_t a, ecs_entity_t b, float value,
                     int place_id);

#endif
