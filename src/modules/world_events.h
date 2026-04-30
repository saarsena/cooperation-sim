#ifndef RELATIONSHIPS_MODULES_WORLD_EVENTS_H
#define RELATIONSHIPS_MODULES_WORLD_EVENTS_H

#include "flecs.h"
#include "core/config.h"

/* Witness-world Phase 2: shared events that touch many agents at once.

   Two event types in V2:
   - Fire at a place: stochastic, broadcasts to every alive agent with a
     reaction that scales by their prior association with the place.
   - Notable death: triggered when a well-connected agent dies, broadcasts
     to their surviving high-trust partners as a shared loss.

   The module owns its own PCG sub-stream so toggling it on/off does not
   perturb the places stream or the global stream at the same seed. */

void WorldEventsModuleImport(ecs_world_t *world);
#define WorldEventsModule WorldEventsModuleImport

/* Call once after all modules are imported and Config is set, mirroring
   places_init. Idempotent. */
void world_events_init(ecs_world_t *world, const Config *cfg);

/* Hook called by AgentDeathSystem the moment an agent dies, before their
   relationships are torn down. Decides whether the death is "notable"
   (≥ notable_death_min_strong_bonds bonds at trust ≥ threshold), and if so
   broadcasts it: log notable_death + per-witness rows, hit each witness's
   TrustBaseline, and increment the deceased's home place's PlaceMark.deaths.

   Caller must hold world_events_enabled in the config — this function
   inspects the flag itself and returns immediately if disabled, so it's
   safe to call unconditionally. */
void world_events_handle_death(ecs_world_t *world, const Config *cfg,
                               ecs_entity_t deceased, int tick);

#endif
