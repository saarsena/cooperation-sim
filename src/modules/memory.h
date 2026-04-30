#ifndef RELATIONSHIPS_MODULES_MEMORY_H
#define RELATIONSHIPS_MODULES_MEMORY_H

#include "flecs.h"
#include "core/config.h"
#include <stdint.h>

/* Witness-world Phase 3: cultural transmission of stories along the
   social-ancestor edge. Each new agent inherits a (decay-scaled) copy of
   their picked ancestor's Stories inventory. Witnessed touchstones (fires,
   notable deaths) are added at full fidelity at the moment of witnessing.

   Decay model: continuous-from-origin. A story's fidelity is a function
   purely of (current_tick - origin_tick), not of how many holders it
   passed through. Two holders at the same moment see the same fidelity
   for the same story regardless of path. This is more honest than
   reset-on-inheritance — "the story did not keep" lines can appear on
   stories inherited only last decade if they originated long before.

   Single-step provenance attribution: each slot carries one bit
   (`source_was_origin_witness`) recording whether the immediate ancestor
   was the originating witness or themselves a relay. This lets the
   chronicler say "Corven inherited from Selka" only when Selka witnessed
   the event firsthand, and otherwise "the story had reached Selka from
   before her own time, and from Selka it reached Corven."

   Reserved RNG sub-stream for V3.5 corruption (story details distorting
   on transmission rather than just losing intensity):
       MEMORY_STREAM_ID = 0x4d454d4f52592121ULL  // ASCII "MEMORY!!"
   Not initialized in V3 — declared in code as documentation. */

#define STORY_CAPACITY 10

/* One slot in an agent's story inventory. ~24 bytes per slot, 240 bytes
   per agent (×10 slots), plus the slot count = 244 total per agent. */
typedef struct Story {
    int          origin_tick;     /* tick of the originating event */
    uint8_t      origin_kind;     /* 0 = fire, 1 = notable_death */
    int8_t       origin_place;    /* place_id, or -1 if not anchored */
    uint8_t      was_direct_witness;       /* 1 if THIS holder witnessed */
    uint8_t      source_was_origin_witness;/* 1 if immediate source did */
    float        origin_magnitude; /* [0,1] event magnitude for eviction priority */
    ecs_entity_t source_id;       /* immediate source; 0 if direct */
} Story;

typedef struct Stories {
    Story slots[STORY_CAPACITY];
    int   n;
} Stories;

extern ECS_COMPONENT_DECLARE(Stories);

void MemoryModuleImport(ecs_world_t *world);
#define MemoryModule MemoryModuleImport

/* Compute the current fidelity of a story given the current tick and
   per-year decay constant. Returns a value in (0, 1].

   fidelity(t) = decay ^ ((t - origin_tick) / 365)

   For t == origin_tick (or earlier — defensive), returns 1.0. */
float memory_fidelity_now(const Story *s, int current_tick,
                          float decay_per_year);

/* Add a story to `agent`'s inventory representing direct witnessing of an
   event at `origin_tick` (which is generally the current tick). Magnitude
   is the event's clamped-[0,1] strength — used in eviction priority.
   No-op if memory_enabled is 0. */
void memory_record_witness(ecs_world_t *world, const Config *cfg,
                           ecs_entity_t agent,
                           int origin_tick, int origin_kind,
                           int origin_place, float origin_magnitude);

/* Inherit stories from `ancestor` into `heir`'s inventory. Each slot of
   the ancestor's Stories is considered; if its current fidelity (computed
   from origin_tick) is at or above story_min_fidelity, a copy is added to
   the heir's inventory with the source-attribution bits set.

   The heir's existing inventory is preserved; if the combined slot count
   exceeds STORY_CAPACITY, lowest-priority slots (priority = fidelity +
   origin_magnitude) are evicted.

   Logs one `story_inherited` event per slot copied, so biography
   renderers can reconstruct the inventory from events.log. */
void memory_inherit_from(ecs_world_t *world, const Config *cfg,
                         ecs_entity_t heir, ecs_entity_t ancestor);

#endif
