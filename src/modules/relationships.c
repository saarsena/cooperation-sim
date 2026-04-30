#include "modules/relationships.h"

#include "core/world.h"
#include "output/event_log.h"

#define STB_DS_IMPLEMENTATION
#include "stb_ds.h"

#include <stddef.h>
#include <string.h>

ECS_COMPONENT_DECLARE(RelationshipPair);
ECS_COMPONENT_DECLARE(TrustStrength);
ECS_COMPONENT_DECLARE(RelationshipAge);
ECS_COMPONENT_DECLARE(LastReinforced);

ecs_entity_t RelationshipPrefab = 0;

static ecs_query_t *q_all_relationships = NULL;

/* O(1) pair -> relationship-entity index. Maintained alongside the ECS storage;
   the previous linear-scan find_relationship was ~68% of runtime per perf. */
typedef struct {
    ecs_entity_t a;
    ecs_entity_t b;
} PairKey;

typedef struct {
    PairKey      key;
    ecs_entity_t value;
} PairEntry;

static PairEntry *g_index = NULL;

static long g_formation_count = 0;

static inline PairKey make_key(ecs_entity_t a, ecs_entity_t b) {
    PairKey k;
    memset(&k, 0, sizeof k);   /* zero any padding so stb_ds memcmp is well-defined */
    k.a = a;
    k.b = b;
    return k;
}

static void TrustDecayAndAge(ecs_iter_t *it) {
    TrustStrength   *ts  = ecs_field(it, TrustStrength,   0);
    RelationshipAge *age = ecs_field(it, RelationshipAge, 1);

    const Config *cfg = world_cfg(it->world);
    const float baseline = cfg->trust_baseline;
    const float decay    = cfg->trust_decay;

    for (int i = 0; i < it->count; i++) {
        age[i].ticks += 1;
        float diff = baseline - ts[i].value;
        ts[i].value += diff * decay;
        if (ts[i].value >  1.0f) ts[i].value =  1.0f;
        if (ts[i].value < -1.0f) ts[i].value = -1.0f;
    }
}

void RelationshipsModuleImport(ecs_world_t *world) {
    ECS_MODULE(world, RelationshipsModule);

    ECS_COMPONENT_DEFINE(world, RelationshipPair);
    ECS_COMPONENT_DEFINE(world, TrustStrength);
    ECS_COMPONENT_DEFINE(world, RelationshipAge);
    ECS_COMPONENT_DEFINE(world, LastReinforced);

    RelationshipPrefab = ecs_entity(world, {
        .name = "RelationshipPrefab",
        .add  = ecs_ids(EcsPrefab)
    });
    ecs_set(world, RelationshipPrefab, RelationshipPair, { 0, 0 });
    ecs_set(world, RelationshipPrefab, TrustStrength,    { 0.0f });
    ecs_set(world, RelationshipPrefab, RelationshipAge,  { 0 });
    ecs_set(world, RelationshipPrefab, LastReinforced,   { 0 });

    q_all_relationships = ecs_query(world, {
        .terms = {
            { .id = ecs_id(RelationshipPair) }
        }
    });

    ecs_system(world, {
        .entity = ecs_entity(world, {
            .name = "TrustDecayAndAge",
            .add  = ecs_ids(ecs_dependson(EcsOnUpdate))
        }),
        .query.terms = {
            { .id = ecs_id(TrustStrength),   .inout = EcsInOut },
            { .id = ecs_id(RelationshipAge), .inout = EcsInOut }
        },
        .callback = TrustDecayAndAge
    });
}

static inline void normalize_pair(ecs_entity_t *a, ecs_entity_t *b) {
    if (*a > *b) {
        ecs_entity_t t = *a;
        *a = *b;
        *b = t;
    }
}

ecs_entity_t create_relationship(ecs_world_t *world,
                                 ecs_entity_t a, ecs_entity_t b,
                                 float initial_strength,
                                 int current_tick)
{
    normalize_pair(&a, &b);
    ecs_entity_t r = ecs_new_w_pair(world, EcsIsA, RelationshipPrefab);
    ecs_set(world, r, RelationshipPair, { a, b });
    ecs_set(world, r, TrustStrength,    { initial_strength });
    ecs_set(world, r, RelationshipAge,  { 0 });
    ecs_set(world, r, LastReinforced,   { current_tick });

    PairKey key = make_key(a, b);
    hmput(g_index, key, r);
    g_formation_count++;

    event_log_write(current_tick, "relationship_created", a, b, initial_strength, -1);
    return r;
}

ecs_entity_t find_relationship(ecs_world_t *world, ecs_entity_t a, ecs_entity_t b) {
    (void)world;
    normalize_pair(&a, &b);
    PairKey key = make_key(a, b);
    ptrdiff_t idx = hmgeti(g_index, key);
    return (idx >= 0) ? g_index[idx].value : 0;
}

void relationships_destroy_for_agent(ecs_world_t *world, ecs_entity_t agent, int current_tick) {
    ecs_defer_begin(world);

    ecs_iter_t it = ecs_query_iter(world, q_all_relationships);
    while (ecs_query_next(&it)) {
        RelationshipPair *pairs = ecs_field(&it, RelationshipPair, 0);
        for (int i = 0; i < it.count; i++) {
            if (pairs[i].a == agent || pairs[i].b == agent) {
                PairKey key = make_key(pairs[i].a, pairs[i].b);
                (void)hmdel(g_index, key);
                event_log_write(current_tick, "relationship_destroyed",
                                pairs[i].a, pairs[i].b, 0.0f, -1);
                ecs_delete(world, it.entities[i]);
            }
        }
    }

    ecs_defer_end(world);
}

void relationships_cleanup(void) {
    hmfree(g_index);
    g_index = NULL;
    g_formation_count = 0;
}

long relationships_consume_formation_count(void) {
    long c = g_formation_count;
    g_formation_count = 0;
    return c;
}

int relationships_collect_strong_partners(
    ecs_world_t *world, ecs_entity_t agent, float min_trust,
    ecs_entity_t *partners, float *trusts, int max_out)
{
    int n = 0;
    ecs_iter_t it = ecs_query_iter(world, q_all_relationships);
    while (ecs_query_next(&it)) {
        RelationshipPair *pairs = ecs_field(&it, RelationshipPair, 0);
        for (int i = 0; i < it.count; i++) {
            ecs_entity_t partner = 0;
            if (pairs[i].a == agent)      partner = pairs[i].b;
            else if (pairs[i].b == agent) partner = pairs[i].a;
            else continue;
            const TrustStrength *ts = ecs_get(world, it.entities[i], TrustStrength);
            if (!ts) continue;
            if (ts->value < min_trust) continue;
            if (n >= max_out) return n;
            partners[n] = partner;
            trusts[n]   = ts->value;
            n++;
        }
    }
    return n;
}
