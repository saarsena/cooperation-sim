#include "modules/agents.h"

#include "core/rng.h"
#include "core/world.h"
#include "modules/relationships.h"
#include "output/event_log.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

ECS_COMPONENT_DECLARE(Resources);
ECS_COMPONENT_DECLARE(TrustBaseline);
ECS_COMPONENT_DECLARE(Age);
ECS_COMPONENT_DECLARE(VentureChance);
ECS_COMPONENT_DECLARE(Traits);
ECS_COMPONENT_DECLARE(CoopQuality);
ECS_COMPONENT_DECLARE(TrustByTrait);
ECS_TAG_DECLARE(Alive);

/* Box–Muller normal sample using the project RNG — kept here (not rng.c) because
   only the trait/quality spawn path needs it. */
static float sample_normal(float mean, float sigma) {
    if (sigma <= 0.0f) return mean;
    float u1 = rng_float();
    if (u1 < 1e-7f) u1 = 1e-7f;
    float u2 = rng_float();
    float z  = sqrtf(-2.0f * logf(u1)) * cosf(6.28318530718f * u2);
    return mean + sigma * z;
}

static inline float clampf(float x, float lo, float hi) {
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

ecs_entity_t AgentPrefab = 0;

static void MetabolismSystem(ecs_iter_t *it) {
    Resources *res = ecs_field(it, Resources, 0);
    Age       *age = ecs_field(it, Age,       1);

    const Config *cfg = world_cfg(it->world);
    const float   m   = cfg->metabolism;

    for (int i = 0; i < it->count; i++) {
        res[i].amount -= m;
        age[i].ticks  += 1;
    }
}

static void AgentDeathSystem(ecs_iter_t *it) {
    Resources *res = ecs_field(it, Resources, 0);

    SimState *st = world_state(it->world);
    const int tick = st->current_tick;

    /* Collect first to avoid mutating during iteration. */
    ecs_entity_t dying[512];
    int          n = 0;

    for (int i = 0; i < it->count; i++) {
        if (res[i].amount <= 0.0f) {
            if (n < (int)(sizeof dying / sizeof dying[0])) {
                dying[n++] = it->entities[i];
            }
        }
    }

    for (int i = 0; i < n; i++) {
        event_log_write(tick, "agent_death", dying[i], 0, 0.0f);
        relationships_destroy_for_agent(it->world, dying[i], tick);
        ecs_delete(it->world, dying[i]);
        st->deaths++;
    }
}

static void SpawnSystem(ecs_iter_t *it) {
    const Config *cfg = world_cfg(it->world);
    SimState *st = world_state(it->world);
    if (st->current_tick <= 0) return;
    if (st->current_tick % cfg->spawn_interval != 0) return;
    spawn_agent(it->world, cfg);
}

void AgentsModuleImport(ecs_world_t *world) {
    ECS_MODULE(world, AgentsModule);

    ECS_COMPONENT_DEFINE(world, Resources);
    ECS_COMPONENT_DEFINE(world, TrustBaseline);
    ECS_COMPONENT_DEFINE(world, Age);
    ECS_COMPONENT_DEFINE(world, VentureChance);
    ECS_COMPONENT_DEFINE(world, Traits);
    ECS_COMPONENT_DEFINE(world, CoopQuality);
    ECS_COMPONENT_DEFINE(world, TrustByTrait);
    ECS_TAG_DEFINE(world, Alive);

    AgentPrefab = ecs_entity(world, {
        .name = "AgentPrefab",
        .add  = ecs_ids(EcsPrefab)
    });
    ecs_set(world, AgentPrefab, Resources,     { 100.0f });
    ecs_set(world, AgentPrefab, TrustBaseline, { 0.0f });
    ecs_set(world, AgentPrefab, Age,           { 0 });
    ecs_set(world, AgentPrefab, VentureChance, { 0.4f });

    ecs_system(world, {
        .entity = ecs_entity(world, {
            .name = "MetabolismSystem",
            .add  = ecs_ids(ecs_dependson(EcsOnUpdate))
        }),
        .query.terms = {
            { .id = ecs_id(Resources), .inout = EcsInOut },
            { .id = ecs_id(Age),       .inout = EcsInOut },
            { .id = Alive }
        },
        .callback = MetabolismSystem
    });

    ecs_system(world, {
        .entity = ecs_entity(world, {
            .name = "AgentDeathSystem",
            .add  = ecs_ids(ecs_dependson(EcsPostUpdate))
        }),
        .query.terms = {
            { .id = ecs_id(Resources), .inout = EcsIn },
            { .id = Alive }
        },
        .callback = AgentDeathSystem
    });

    ecs_system(world, {
        .entity = ecs_entity(world, {
            .name = "SpawnSystem",
            .add  = ecs_ids(ecs_dependson(EcsPostUpdate))
        }),
        .callback = SpawnSystem
    });
}

ecs_entity_t spawn_agent(ecs_world_t *world, const Config *cfg) {
    ecs_entity_t e = ecs_new_w_pair(world, EcsIsA, AgentPrefab);

    SimState *st = world_state(world);

    /* Resource endowment — bimodal if configured (Rule 6 / Rule 7 unequal starts). */
    float res;
    if (cfg->initial_resource_rich_frac > 0.0f
        && rng_float() < cfg->initial_resource_rich_frac) {
        res = rng_range_f(cfg->initial_resources_rich_min,
                          cfg->initial_resources_rich_max);
    } else {
        res = rng_range_f(cfg->initial_resources_min, cfg->initial_resources_max);
    }
    /* Intervention: boost new entrants after a configured tick. */
    if (cfg->intervention_tick >= 0
        && st->current_tick >= cfg->intervention_tick) {
        res *= cfg->intervention_newentrant_boost;
    }

    float tb  = rng_range_f(-0.3f, 0.5f);
    float vc  = cfg->venture_chance;

    /* Rule 2 / Rule 7: random traits at spawn, uniform over TRAIT_LEVELS. */
    Traits traits;
    for (int d = 0; d < TRAIT_COUNT; d++) {
        traits.v[d] = (uint8_t)rng_range_i(0, TRAIT_LEVELS - 1);
    }

    /* Rule 3: hidden cooperative quality.
       Base draw ~ Normal(coop_quality_mean, coop_quality_sigma), then blended
       toward a trait-determined value by trait_quality_correlation. */
    float q_raw = sample_normal(cfg->coop_quality_mean, cfg->coop_quality_sigma);
    float q_trait_target = cfg->coop_quality_mean; /* neutral default */
    if (cfg->trait_quality_correlation > 0.0f) {
        /* Pack traits into [0,1]; makes some groups systematically higher-q. */
        int key = traits_group_key(&traits);
        q_trait_target = (float)key / (float)(TRAITS_GROUP_COUNT - 1);
        /* center around coop_quality_mean so correlation=1 gives a spread
           symmetric around the mean instead of shifting its expectation. */
        q_trait_target = cfg->coop_quality_mean + (q_trait_target - 0.5f);
    }
    float q = (1.0f - cfg->trait_quality_correlation) * q_raw
            + cfg->trait_quality_correlation * q_trait_target;
    q = clampf(q, 0.0f, 1.0f);

    /* Rule 7: new agents enter with zero generalized trust history. */
    TrustByTrait tbt;
    memset(&tbt, 0, sizeof tbt);

    ecs_set(world, e, Resources,     { res });
    ecs_set(world, e, TrustBaseline, { tb });
    ecs_set(world, e, Age,           { 0 });
    ecs_set(world, e, VentureChance, { vc });
    ecs_set_ptr(world, e, Traits, &traits);
    ecs_set(world, e, CoopQuality, { q });
    ecs_set_ptr(world, e, TrustByTrait, &tbt);
    ecs_add(world, e, Alive);

    st->births++;

    event_log_write(st->current_tick, "agent_birth", e, 0, res);
    return e;
}
