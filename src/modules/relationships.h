#ifndef RELATIONSHIPS_MODULES_RELATIONSHIPS_H
#define RELATIONSHIPS_MODULES_RELATIONSHIPS_H

#include "flecs.h"

typedef struct RelationshipPair   { ecs_entity_t a; ecs_entity_t b; } RelationshipPair;
typedef struct TrustStrength      { float value; }                    TrustStrength;
typedef struct RelationshipAge    { int ticks; }                      RelationshipAge;
typedef struct LastReinforced     { int tick; }                       LastReinforced;

extern ECS_COMPONENT_DECLARE(RelationshipPair);
extern ECS_COMPONENT_DECLARE(TrustStrength);
extern ECS_COMPONENT_DECLARE(RelationshipAge);
extern ECS_COMPONENT_DECLARE(LastReinforced);

extern ecs_entity_t RelationshipPrefab;

void RelationshipsModuleImport(ecs_world_t *world);
#define RelationshipsModule RelationshipsModuleImport

/* Create a new relationship entity between a and b. Order is normalized so a < b. */
ecs_entity_t create_relationship(ecs_world_t *world,
                                 ecs_entity_t a, ecs_entity_t b,
                                 float initial_strength,
                                 int current_tick);

/* Linear scan; returns 0 if no relationship exists. */
ecs_entity_t find_relationship(ecs_world_t *world, ecs_entity_t a, ecs_entity_t b);

/* Destroy every relationship entity referencing `agent`. Called before agent entity itself is destroyed. */
void relationships_destroy_for_agent(ecs_world_t *world, ecs_entity_t agent, int current_tick);

/* Release the pair-key hash map. Call once before ecs_fini. */
void relationships_cleanup(void);

/* Per-tick formation flow: returns the number of relationships created since
   the last call and resets the internal counter. Used by per-tick metrics. */
long relationships_consume_formation_count(void);

#endif
