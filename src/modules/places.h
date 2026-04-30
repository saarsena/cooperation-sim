#ifndef RELATIONSHIPS_MODULES_PLACES_H
#define RELATIONSHIPS_MODULES_PLACES_H

#include "flecs.h"
#include "core/config.h"
#include <stdint.h>

/* Witness-world places module.

   The world has 12 fixed named locations. Each is an ECS entity with a name
   and a type. Ventures happen *at* one of these places, agents accumulate
   per-place preference weights, and new agents inherit a weak prior from
   currently-living agents.

   The pool is the same across every run on this branch; what varies between
   seeds is which agents come to prefer which places. */

/* Compile-time place count. Hardcoded so LocationPrefs can hold a fixed-size
   array (sized below at PLACES_COUNT) instead of a flexible dynamic field on
   every agent. If a future scenario needs to vary place count: either
   (a) make this a tunable max at build time and have scenarios populate up
   to it, leaving unused slots zeroed; or (b) move LocationPrefs to a
   variable-length component and pay the heap cost. The 12-place pool below
   was the V1 design choice — sized to give six type categories two names
   each, rich enough for biographies but small enough that ventures don't
   spread thin across too many bins. */
#define PLACES_COUNT 12

/* Place entity components. */
typedef struct PlaceName { const char *value; } PlaceName;
typedef struct PlaceType { const char *value; } PlaceType;
/* Stable index in [0, PLACES_COUNT) — small integer ID used for indexing into
   per-agent LocationPrefs arrays and serialized into events.log. */
typedef struct PlaceIndex { int value; } PlaceIndex;

/* Phase 2: persistent counters for things-that-happened-at-this-place. The
   place's "reputation" — incremented by world_events, never decays. Used in
   place biographies as the slow-accumulating record of touchstone events. */
typedef struct PlaceMark {
    int fires;   /* number of fires that have occurred here */
    int deaths;  /* notable deaths most associated with this place */
} PlaceMark;

extern ECS_COMPONENT_DECLARE(PlaceName);
extern ECS_COMPONENT_DECLARE(PlaceType);
extern ECS_COMPONENT_DECLARE(PlaceIndex);
extern ECS_COMPONENT_DECLARE(PlaceMark);

/* Per-agent component: signed preference weights, one per place.
   Updated on venture outcomes (gain on success at p, loss on failure at p)
   and decays toward 0 each tick. New agents start with a scaled copy of one
   recent ancestor's weights (single-ancestor inheritance). */
typedef struct LocationPrefs {
    float w[PLACES_COUNT];
} LocationPrefs;

/* Phase 2: per-agent venture counts at each place. Used to identify which
   place was most central to an agent's life — answers "where did Pellyl
   spend their days?" at notable-death time, and lets fire's per-witness
   reaction scale by lived experience as well as preference. Pure history
   record; never decays. */
typedef struct VentureCountByPlace {
    int count[PLACES_COUNT];
} VentureCountByPlace;

extern ECS_COMPONENT_DECLARE(LocationPrefs);
extern ECS_COMPONENT_DECLARE(VentureCountByPlace);

void PlacesModuleImport(ecs_world_t *world);
#define PlacesModule PlacesModuleImport

/* Call once after PlacesModule is imported and Config singleton is set.
   Spawns the 12 place entities and seeds the places sub-stream from cfg.seed.
   Idempotent — returns immediately on second call. */
void places_init(ecs_world_t *world, const Config *cfg);

/* Pick a place for a venture between `initiator` and `partner`. Reads each
   agent's LocationPrefs, blends them, mixes with uniform via exploration_rate,
   draws from the places sub-stream, and returns the chosen place index in
   [0, PLACES_COUNT).

   Caller must have verified cfg->places_enabled. */
int  places_choose_for_venture(ecs_world_t *world,
                               ecs_entity_t initiator, ecs_entity_t partner,
                               float exploration_rate);

/* Apply per-place preference update on a venture outcome. delta is positive
   on success, negative on failure. Mutates LocationPrefs in place; clamps to
   [-1, 1]. */
void places_update_pref_on_outcome(ecs_world_t *world,
                                   ecs_entity_t agent,
                                   int place_index, float delta);

/* Increment the per-agent venture count for `agent` at `place_index` by 1.
   Called once per agent per venture (so a venture between A and B updates
   both their counts). */
void places_record_venture_for_agent(ecs_world_t *world,
                                     ecs_entity_t agent,
                                     int place_index);

/* Increment the world-level total venture count at `place_index`. Called
   once per venture (not once per partner). Used by world_events for fire
   target weighting — well-used places are more likely to burn. */
void places_record_venture_world(int place_index);

/* Read the world-level total venture count at `place_index`. */
long places_total_ventures_at(int place_index);

/* Per-tick decay: drift every agent's location weights toward 0. Registered
   as an ECS system by PlacesModuleImport. */

/* Compute the inherited initial LocationPrefs for a new agent.

   Picks one uniformly-random "social ancestor" from the windowed cohort
   (currently-alive agents whose LastActive is within place_inherit_window
   ticks of now), then copies their LocationPrefs × place_inherit_strength
   into `out`. Returns the entity ID of the chosen ancestor, or 0 if no
   agents qualified (initial population at tick 0).

   The Phase 3 memory module needs to inherit *from the same ancestor* as
   the LocationPrefs, so this function returns the picked entity. Callers
   that don't need it can ignore the return value.

   We deliberately do NOT average across the cohort. Averaging cancels the
   idiosyncratic preference variance individual agents accumulate from
   their venture histories — every place gets the same population-mean
   weight, and the resulting prior carries no preference signal (verified
   empirically: cohort-mean priors had per-spawn variance of 0.000079,
   essentially zero). Single-ancestor sampling preserves the full
   per-agent within-variance and matches the "social ancestor" framing in
   the witness-world spec literally — your prior is one specific
   predecessor's preferences, not an aggregate. */
ecs_entity_t places_compute_inherited_prior(ecs_world_t *world,
                                            const Config *cfg,
                                            LocationPrefs *out);

/* Read accessors for snapshot/output code. idx must be in [0, PLACES_COUNT). */
const char  *places_name(int idx);
const char  *places_type(int idx);
ecs_entity_t places_entity_at(int idx);

/* Diagnostic: dump aggregate stats about inherited priors observed across
   the run. Specifically the per-spawn variance over the 12 inherited
   weights — answers whether the prior carries any preference signal at
   spawn time. Near zero ⇒ priors are flat ⇒ the recency-windowed cohort
   version of inheritance is needed. Meaningful ⇒ V1 simplification is
   fine. Pass `stderr` or any open FILE *. */
void places_log_summary(void *fp);

#endif
