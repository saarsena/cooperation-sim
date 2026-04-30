#ifndef RELATIONSHIPS_MODULES_AGENTS_H
#define RELATIONSHIPS_MODULES_AGENTS_H

#include "flecs.h"
#include "core/config.h"
#include <stdint.h>

/* Rule 2: visible discrete-valued traits, fixed per agent for life.
   2 traits × 2 levels = 4 distinct visible "types" — populous enough at
   default pop sizes that within-group buckets aren't starved. */
#define TRAIT_COUNT  2
#define TRAIT_LEVELS 2

typedef struct Resources       { float amount; }   Resources;
typedef struct TrustBaseline   { float value;  }   TrustBaseline;
typedef struct Age             { int   ticks;  }   Age;
typedef struct VentureChance   { float p;      }   VentureChance;
/* Witness-world: tick of this agent's most recent venture (or, for a
   freshly-spawned agent, their birth tick). Read by places inheritance to
   filter the cohort an inheriting spawn averages over: only agents whose
   current_tick - LastActive < place_inherit_window contribute. Decoupled
   from Age so that long-lived but currently-inactive agents stop carrying
   weight in newcomers' priors. */
typedef struct LastActive      { int   tick;   }   LastActive;
/* Witness-world Phase 3: the specific recent ancestor whose LocationPrefs
   (and, when memory_enabled, Stories) were sampled by this agent at spawn.
   0 for the initial population (no ancestor was alive). Used by the
   biography renderer to attribute "inherited from Selka" lines to a real
   predecessor, not just to "the previous generation." */
typedef struct SocialAncestor  { ecs_entity_t id; } SocialAncestor;

typedef struct Traits {
    uint8_t v[TRAIT_COUNT];
} Traits;

/* Rule 3: hidden, intrinsic "cooperative quality" drawn at spawn.
   Shifts venture success probability and payoff when config weights are > 0. */
typedef struct CoopQuality { float value; } CoopQuality;

/* Rule 4: per-agent generalized trust table toward agents bearing a given
   (trait_dim, trait_value) combination. Updated whenever this agent has a
   venture outcome; read during partner evaluation as a cheap prior when no
   direct relationship exists. */
typedef struct TrustByTrait {
    float v[TRAIT_COUNT][TRAIT_LEVELS];
} TrustByTrait;

extern ECS_COMPONENT_DECLARE(Resources);
extern ECS_COMPONENT_DECLARE(TrustBaseline);
extern ECS_COMPONENT_DECLARE(Age);
extern ECS_COMPONENT_DECLARE(VentureChance);
extern ECS_COMPONENT_DECLARE(Traits);
extern ECS_COMPONENT_DECLARE(CoopQuality);
extern ECS_COMPONENT_DECLARE(TrustByTrait);
extern ECS_COMPONENT_DECLARE(LastActive);
extern ECS_COMPONENT_DECLARE(SocialAncestor);
extern ECS_TAG_DECLARE(Alive);

extern ecs_entity_t AgentPrefab;

void AgentsModuleImport(ecs_world_t *world);
#define AgentsModule AgentsModuleImport

ecs_entity_t spawn_agent(ecs_world_t *world, const Config *cfg);

/* Pack traits into a single integer key in [0, TRAIT_LEVELS^TRAIT_COUNT). */
static inline int traits_group_key(const Traits *t) {
    int k = 0;
    for (int d = 0; d < TRAIT_COUNT; d++) {
        k = k * TRAIT_LEVELS + t->v[d];
    }
    return k;
}

#define TRAITS_GROUP_COUNT 4 /* TRAIT_LEVELS ^ TRAIT_COUNT */

#endif
