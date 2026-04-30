#include "modules/world_events.h"

#include "core/rng.h"
#include "core/world.h"
#include "modules/agents.h"
#include "modules/memory.h"
#include "modules/places.h"
#include "modules/relationships.h"
#include "output/event_log.h"

#include <stdio.h>
#include <string.h>

/* Stable 64-bit identifier for the world-events PCG sub-stream. ASCII for
   "EVENTS!". Independent of PLACES_STREAM_ID so the two modules' draws are
   not coupled. */
#define WORLD_EVENTS_STREAM_ID 0x4556454e54532121ULL

static int       g_initialized = 0;
static RngStream g_we_rng;

/* Maximum strong-bond witnesses we'll process per notable death. With pop
   sizes typically under a few hundred and trust thresholds at 0.5, this is
   plenty. Anyone past the cap is silently dropped — fine for V2; this is a
   diagnostic, not a billing system. */
#define MAX_WITNESSES 256

/* Fire system: per-tick, stochastic. With probability fire_per_tick_prob we
   pick a place (weighted by total venture count there, so popular places
   are more likely to burn) and broadcast to every alive agent. */

static ecs_query_t *g_q_alive_locprefs = NULL;

static int pick_burn_target(void) {
    /* Weighted by total ventures-at-place. If everywhere is empty (early
       run), fall back to uniform. */
    long total = 0;
    long counts[PLACES_COUNT];
    for (int i = 0; i < PLACES_COUNT; i++) {
        counts[i] = places_total_ventures_at(i);
        total += counts[i];
    }
    if (total <= 0) {
        return rng_stream_range_i(&g_we_rng, 0, PLACES_COUNT - 1);
    }
    /* Weighted draw using counts directly (no exponentiation; venture count
       IS the weight). */
    long r = (long)((double)rng_stream_float(&g_we_rng) * (double)total);
    long acc = 0;
    for (int i = 0; i < PLACES_COUNT; i++) {
        acc += counts[i];
        if (r < acc) return i;
    }
    return PLACES_COUNT - 1;
}

static void apply_fire(ecs_world_t *world, const Config *cfg, int tick, int p) {
    int affected = 0;
    /* First pass: count affected to compute the fire's magnitude (used by
       the memory module as the eviction-priority anchor). */
    int alive_count = 0;
    {
        ecs_iter_t cit = ecs_query_iter(world, g_q_alive_locprefs);
        while (ecs_query_next(&cit)) alive_count += cit.count;
    }
    /* Magnitude in [0,1]: fire that touched 80+ agents is "1.0", smaller
       fires scale down. Stored on each witness's story slot for eviction. */
    float magnitude = alive_count / 80.0f;
    if (magnitude > 1.0f) magnitude = 1.0f;

    /* Second pass: apply the LocationPrefs hit, log per-witness, record
       the witnessing in each agent's memory. */
    ecs_iter_t it = ecs_query_iter(world, g_q_alive_locprefs);
    while (ecs_query_next(&it)) {
        LocationPrefs *lp = ecs_field(&it, LocationPrefs, 0);
        for (int i = 0; i < it.count; i++) {
            float prior = lp[i].w[p];
            /* Floor hit + scaled-by-association extra. abs() so a place an
               agent had AVOIDED still feels the fire (negative prior agents
               aren't unaffected — they had attitudes about the place). */
            float prior_mag = prior < 0 ? -prior : prior;
            float delta = -cfg->fire_pref_hit * (1.0f + prior_mag);
            float v = lp[i].w[p] + delta;
            if (v < -1.0f) v = -1.0f;
            if (v >  1.0f) v =  1.0f;
            lp[i].w[p] = v;
            event_log_write(tick, "fire_witnessed",
                            it.entities[i], 0, prior, p);
            /* Phase 3: this fire becomes a story in the witness's
               inventory. origin_kind=0 (fire). No-op when memory_enabled=0. */
            memory_record_witness(world, cfg, it.entities[i],
                                  tick, /*kind*/ 0, p, magnitude);
            affected++;
        }
    }
    /* Bump the place's persistent fires counter. */
    ecs_entity_t pe = places_entity_at(p);
    if (pe) {
        const PlaceMark *cur = ecs_get(world, pe, PlaceMark);
        PlaceMark next = cur ? *cur : (PlaceMark){0,0};
        next.fires += 1;
        ecs_set_ptr(world, pe, PlaceMark, &next);
    }
    /* World-level event row, with affected_count in the value field. */
    event_log_write(tick, "fire", 0, 0, (float)affected, p);
}

static void FireSystem(ecs_iter_t *it) {
    const Config *cfg = world_cfg(it->world);
    if (!cfg->world_events_enabled) return;
    if (cfg->fire_per_tick_prob <= 0.0f) return;
    SimState *st = world_state(it->world);
    if (st->current_tick <= 0) return;  /* skip tick 0; population still seeding */
    if (rng_stream_float(&g_we_rng) >= cfg->fire_per_tick_prob) return;
    apply_fire(it->world, cfg, st->current_tick, pick_burn_target());
}

void WorldEventsModuleImport(ecs_world_t *world) {
    ECS_MODULE(world, WorldEventsModule);

    g_q_alive_locprefs = ecs_query(world, {
        .terms = {
            { .id = ecs_id(LocationPrefs), .inout = EcsInOut },
            { .id = Alive }
        }
    });

    ecs_system(world, {
        .entity = ecs_entity(world, {
            .name = "FireSystem",
            .add  = ecs_ids(ecs_dependson(EcsOnUpdate))
        }),
        .callback = FireSystem
    });
}

void world_events_init(ecs_world_t *world, const Config *cfg) {
    (void)world;
    if (g_initialized) return;
    g_initialized = 1;
    rng_stream_init(&g_we_rng, cfg->seed, WORLD_EVENTS_STREAM_ID);
}

/* Notable death: invoked synchronously from AgentDeathSystem before the
   deceased's relationships are destroyed. We collect strong bonds, decide
   whether the death qualifies, and if so broadcast it. */
void world_events_handle_death(ecs_world_t *world, const Config *cfg,
                               ecs_entity_t deceased, int tick)
{
    if (!cfg->world_events_enabled) return;

    ecs_entity_t partners[MAX_WITNESSES];
    float        trusts  [MAX_WITNESSES];
    int n = relationships_collect_strong_partners(
        world, deceased, cfg->notable_death_trust_threshold,
        partners, trusts, MAX_WITNESSES);
    if (n < cfg->notable_death_min_strong_bonds) return;

    /* Find the deceased's home place: argmax of VentureCountByPlace. If the
       deceased never ventured at any place (shouldn't happen if they had
       strong bonds, but be defensive), home_place stays -1. */
    int   home_place = -1;
    int   home_count = 0;
    const VentureCountByPlace *vc = ecs_get(world, deceased, VentureCountByPlace);
    if (vc) {
        for (int p = 0; p < PLACES_COUNT; p++) {
            if (vc->count[p] > home_count) {
                home_count = vc->count[p];
                home_place = p;
            }
        }
    }

    /* Broadcast: world-level row first, then per-witness rows. */
    event_log_write(tick, "notable_death", deceased, 0, (float)n, home_place);

    /* Magnitude in [0,1]: a notable death with ≥10 strong bonds is "1.0",
       fewer scale down. Used by memory's eviction priority. */
    float magnitude = n / 10.0f;
    if (magnitude > 1.0f) magnitude = 1.0f;

    for (int i = 0; i < n; i++) {
        ecs_entity_t w = partners[i];
        float t = trusts[i];
        /* Hit witness TrustBaseline scaled by their pairwise trust to the
           deceased. Floor at -1. */
        const TrustBaseline *cur = ecs_get(world, w, TrustBaseline);
        float base = cur ? cur->value : 0.0f;
        float delta = -cfg->notable_death_baseline_hit * t;
        float v = base + delta;
        if (v < -1.0f) v = -1.0f;
        if (v >  1.0f) v =  1.0f;
        ecs_set(world, w, TrustBaseline, { v });
        event_log_write(tick, "notable_death_witnessed", w, deceased, t, -1);
        /* Phase 3: the death becomes a story in this witness's inventory.
           origin_kind=1 (notable_death), origin_place=home_place (or -1
           if the deceased had no recorded home). */
        memory_record_witness(world, cfg, w, tick, /*kind*/ 1,
                              home_place, magnitude);
    }

    /* Stain the deceased's home place. */
    if (home_place >= 0) {
        ecs_entity_t pe = places_entity_at(home_place);
        if (pe) {
            const PlaceMark *cur = ecs_get(world, pe, PlaceMark);
            PlaceMark next = cur ? *cur : (PlaceMark){0,0};
            next.deaths += 1;
            ecs_set_ptr(world, pe, PlaceMark, &next);
        }
    }
}
