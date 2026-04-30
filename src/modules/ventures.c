#include "modules/ventures.h"

#include "core/config.h"
#include "core/rng.h"
#include "core/world.h"
#include "modules/agents.h"
#include "modules/places.h"
#include "modules/relationships.h"
#include "output/event_log.h"

#include <math.h>
#include <stdlib.h>

#define MAX_CANDIDATES 1024

static ecs_query_t *q_alive = NULL;

static long g_ventures_total_tick       = 0;
static long g_ventures_on_existing_tick = 0;
static long g_ventures_on_strong_tick   = 0;

void ventures_consume_per_tick_counters(long *total, long *on_existing, long *on_strong) {
    if (total)       *total       = g_ventures_total_tick;
    if (on_existing) *on_existing = g_ventures_on_existing_tick;
    if (on_strong)   *on_strong   = g_ventures_on_strong_tick;
    g_ventures_total_tick       = 0;
    g_ventures_on_existing_tick = 0;
    g_ventures_on_strong_tick   = 0;
}

static inline float clampf(float x, float lo, float hi) {
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

/* Rule 4 helper: estimated trust toward a candidate based on shared traits,
   read from the actor's generalized table. Averaged over trait dimensions. */
static float trait_prior_trust(const TrustByTrait *tbt, const Traits *other) {
    float sum = 0.0f;
    for (int d = 0; d < TRAIT_COUNT; d++) {
        sum += tbt->v[d][other->v[d]];
    }
    return sum / (float)TRAIT_COUNT;
}

/* Perceived trust from A toward B:
   - if a direct Relationship exists, its TrustStrength wins;
   - otherwise the trait prior (if A has a TrustByTrait) is used;
   - otherwise A's personal TrustBaseline. */
static float perceived_trust(ecs_world_t *world,
                             ecs_entity_t self, float self_baseline,
                             const TrustByTrait *self_tbt,
                             ecs_entity_t cand)
{
    ecs_entity_t rel = find_relationship(world, self, cand);
    if (rel) {
        const TrustStrength *t = ecs_get(world, rel, TrustStrength);
        if (t) return t->value;
    }
    if (self_tbt) {
        const Traits *ct = ecs_get(world, cand, Traits);
        if (ct) return trait_prior_trust(self_tbt, ct);
    }
    return self_baseline;
}

/* Rule 6: selectivity grows with wealth. Clamped to configured bounds. */
static int search_effort(const Config *cfg, float resources) {
    if (cfg->search_base_k <= 0) return 0; /* legacy path: unlimited scan */
    float over = resources - cfg->search_wealth_threshold;
    if (over < 0.0f) over = 0.0f;
    int k = cfg->search_base_k + (int)(cfg->search_slope * over);
    if (k < cfg->search_min_k) k = cfg->search_min_k;
    if (k > cfg->search_max_k) k = cfg->search_max_k;
    if (k > MAX_CANDIDATES) k = MAX_CANDIDATES;
    return k;
}

/* Collect every alive entity (except self) into buf. Returns how many. */
static int collect_alive(ecs_world_t *world, ecs_entity_t self,
                         ecs_entity_t *buf, int cap)
{
    int n = 0;
    ecs_iter_t it = ecs_query_iter(world, q_alive);
    while (ecs_query_next(&it)) {
        for (int i = 0; i < it.count; i++) {
            ecs_entity_t c = it.entities[i];
            if (c == self) continue;
            if (n >= cap) return n;
            buf[n++] = c;
        }
    }
    return n;
}

/* Fisher–Yates partial shuffle: reorder buf so the first k entries are a
   uniform-random sample without replacement from the full set. */
static void partial_shuffle(ecs_entity_t *buf, int n, int k) {
    if (k > n) k = n;
    for (int i = 0; i < k; i++) {
        int j = rng_range_i(i, n - 1);
        ecs_entity_t t = buf[i]; buf[i] = buf[j]; buf[j] = t;
    }
}

static ecs_entity_t pick_partner(ecs_world_t *world,
                                 ecs_entity_t self, float self_baseline,
                                 float self_resources,
                                 const TrustByTrait *self_tbt,
                                 const Config *cfg,
                                 int *out_k_examined)
{
    ecs_entity_t candidates[MAX_CANDIDATES];
    float        weights[MAX_CANDIDATES];
    int          n = 0;

    const float effective_explore = cfg->exploration_rate;
    const int   explore = (rng_float() < effective_explore) ? 1 : 0;

    const int k_cap = search_effort(cfg, self_resources);

    if (k_cap <= 0) {
        /* Legacy path — unchanged from the pre-extension behavior. */
        ecs_iter_t it = ecs_query_iter(world, q_alive);
        while (ecs_query_next(&it)) {
            for (int i = 0; i < it.count; i++) {
                ecs_entity_t c = it.entities[i];
                if (c == self) continue;
                if (n >= MAX_CANDIDATES) break;
                candidates[n] = c;
                if (explore) {
                    weights[n] = 1.0f;
                } else {
                    float trust = perceived_trust(world, self, self_baseline,
                                                  self_tbt, c);
                    weights[n] = expf(2.0f * trust);
                }
                n++;
            }
        }
        if (out_k_examined) *out_k_examined = n;
    } else {
        /* Costly-search path: sample k candidates without replacement. */
        ecs_entity_t all[MAX_CANDIDATES];
        int n_all = collect_alive(world, self, all, MAX_CANDIDATES);
        if (n_all == 0) {
            if (out_k_examined) *out_k_examined = 0;
            return 0;
        }
        int k = k_cap;
        if (k > n_all) k = n_all;
        partial_shuffle(all, n_all, k);
        for (int i = 0; i < k; i++) {
            candidates[n] = all[i];
            if (explore) {
                weights[n] = 1.0f;
            } else {
                float trust = perceived_trust(world, self, self_baseline,
                                              self_tbt, all[i]);
                weights[n] = expf(2.0f * trust);
            }
            n++;
        }
        if (out_k_examined) *out_k_examined = n;
    }

    if (n == 0) return 0;

    float total = 0.0f;
    for (int i = 0; i < n; i++) total += weights[i];
    if (total <= 0.0f) return candidates[rng_range_i(0, n - 1)];

    float r = rng_float() * total;
    float acc = 0.0f;
    for (int i = 0; i < n; i++) {
        acc += weights[i];
        if (r <= acc) return candidates[i];
    }
    return candidates[n - 1];
}

/* Rule 4 helper: apply a trait-generalized trust nudge to a TrustByTrait table
   based on the partner's traits and the per-outcome delta. Mutates in place. */
static void generalize_trust_update(TrustByTrait *tbt,
                                    const Traits *partner_traits,
                                    float dtrust, float strength)
{
    if (strength <= 0.0f) return;
    const float delta = strength * dtrust;
    for (int d = 0; d < TRAIT_COUNT; d++) {
        float *slot = &tbt->v[d][partner_traits->v[d]];
        float v = *slot + delta;
        if (v >  1.0f) v =  1.0f;
        if (v < -1.0f) v = -1.0f;
        *slot = v;
    }
}

static void VentureSystem(ecs_iter_t *it) {
    Resources     *res = ecs_field(it, Resources,     0);
    VentureChance *vc  = ecs_field(it, VentureChance, 1);
    TrustBaseline *tb  = ecs_field(it, TrustBaseline, 2);

    const Config *cfg = world_cfg(it->world);
    SimState     *st  = world_state(it->world);
    const int     tick = st->current_tick;

    /* Apply interventions that override static config fields, without mutating
       the singleton Config (which would persist across ticks unclean). */
    float exploration_rate = cfg->exploration_rate;
    float generalization   = cfg->trait_generalization_strength;
    if (cfg->intervention_tick >= 0 && tick >= cfg->intervention_tick) {
        if (cfg->intervention_exploration_rate > 0.0f)
            exploration_rate = cfg->intervention_exploration_rate;
        if (cfg->intervention_generalization >= 0.0f)
            generalization = cfg->intervention_generalization;
    }
    /* Shim the effective rates into a local copy so the rest of the code paths
       read from a single source of truth. */
    Config eff = *cfg;
    eff.exploration_rate = exploration_rate;
    eff.trait_generalization_strength = generalization;

    for (int i = 0; i < it->count; i++) {
        if (rng_float() >= vc[i].p) continue;

        ecs_entity_t self = it->entities[i];

        const TrustByTrait *self_tbt_read = ecs_get(it->world, self, TrustByTrait);

        /* Rule 5: search depth and its upfront energy cost, before partner pick. */
        int k_used = 0;
        ecs_entity_t partner = pick_partner(it->world, self, tb[i].value,
                                            res[i].amount, self_tbt_read,
                                            &eff, &k_used);
        if (eff.search_cost_per_candidate > 0.0f && k_used > 0) {
            res[i].amount -= (float)k_used * eff.search_cost_per_candidate;
        }
        if (!partner) continue;

        const Traits *self_traits    = ecs_get(it->world, self,    Traits);
        const Traits *partner_traits = ecs_get(it->world, partner, Traits);

        ecs_entity_t rel = find_relationship(it->world, self, partner);
        float trust = tb[i].value;
        if (rel) {
            const TrustStrength *t = ecs_get(it->world, rel, TrustStrength);
            if (t) trust = t->value;
        } else if (self_tbt_read && partner_traits) {
            trust = trait_prior_trust(self_tbt_read, partner_traits);
        }

        /* Rule 3: success probability modulated by the minimum of the pair's
           hidden cooperative qualities, plus existing trust term. */
        float min_q = eff.coop_quality_mean;
        const CoopQuality *qa = ecs_get(it->world, self,    CoopQuality);
        const CoopQuality *qb = ecs_get(it->world, partner, CoopQuality);
        if (qa && qb) min_q = (qa->value < qb->value) ? qa->value : qb->value;
        /* center quality around 0.5 so weight=0 keeps legacy probability. */
        float p_success = clampf(
            eff.base_success_prob
            + eff.trust_success_weight * trust
            + eff.coop_quality_success_weight * (min_q - 0.5f),
            0.0f, 1.0f);

        int success = (rng_float() < p_success) ? 1 : 0;
        st->ventures_attempted++;

        /* Per-tick flow counters: every completed venture, split by whether it
           touched an existing pair and whether that pair was already strong.
           `trust` here is still the BEFORE-update value. */
        g_ventures_total_tick++;
        if (rel) {
            g_ventures_on_existing_tick++;
            if (trust >= 0.5f) g_ventures_on_strong_tick++;
        }

        float dres, dtrust;
        if (success) {
            /* Rule 3: payoff scales with mean quality when scale > 0. */
            float mean_q = eff.coop_quality_mean;
            if (qa && qb) mean_q = 0.5f * (qa->value + qb->value);
            dres   = eff.venture_reward
                   * (1.0f + eff.coop_quality_payoff_scale * (mean_q - 0.5f));
            dtrust =  eff.trust_gain_on_success;
            st->ventures_succeeded++;
        } else {
            dres   = -eff.venture_cost;
            dtrust = -eff.trust_loss_on_failure;
            st->ventures_failed++;
        }

        res[i].amount += dres;
        const Resources *pr = ecs_get(it->world, partner, Resources);
        if (pr) {
            ecs_set(it->world, partner, Resources, { pr->amount + dres });
        }

        float new_trust = clampf(trust + dtrust, -1.0f, 1.0f);
        if (rel) {
            ecs_set(it->world, rel, TrustStrength,  { new_trust });
            ecs_set(it->world, rel, LastReinforced, { tick });
        } else {
            create_relationship(it->world, self, partner, new_trust, tick);
        }

        /* Rule 4: generalize the trust delta across trait-sharing strangers.
           Symmetric: both sides learn about the other side's trait vector. */
        if (eff.trait_generalization_strength > 0.0f
            && self_traits && partner_traits) {
            TrustByTrait self_tbt_w;
            const TrustByTrait *p_self = ecs_get(it->world, self, TrustByTrait);
            self_tbt_w = p_self ? *p_self : (TrustByTrait){0};
            generalize_trust_update(&self_tbt_w, partner_traits,
                                    dtrust, eff.trait_generalization_strength);
            ecs_set_ptr(it->world, self, TrustByTrait, &self_tbt_w);

            TrustByTrait partner_tbt_w;
            const TrustByTrait *p_partner =
                ecs_get(it->world, partner, TrustByTrait);
            partner_tbt_w = p_partner ? *p_partner : (TrustByTrait){0};
            generalize_trust_update(&partner_tbt_w, self_traits,
                                    dtrust, eff.trait_generalization_strength);
            ecs_set_ptr(it->world, partner, TrustByTrait, &partner_tbt_w);
        }

        /* Witness-world: pick a place for this venture, log into both agents'
           location preferences, and stamp the event with the place index. The
           place draw uses an isolated PCG sub-stream so toggling places does
           not perturb other modules' trajectories at the same seed. */
        int place_id = -1;
        if (eff.places_enabled) {
            place_id = places_choose_for_venture(it->world, self, partner,
                                                 eff.exploration_rate);
            /* Phase 2.5: exposure-based attachment. The outcome-driven
               update is layered on top of a small constant gain that
               accumulates regardless of whether the venture succeeded —
               attachment from time spent, not just from whether time
               spent went well. Default 0.0 preserves V1-V3 behavior. */
            float dpref = (success
                ?  eff.place_pref_gain_on_success
                : -eff.place_pref_loss_on_failure)
                + eff.place_pref_exposure_gain;
            places_update_pref_on_outcome(it->world, self,    place_id, dpref);
            places_update_pref_on_outcome(it->world, partner, place_id, dpref);
            /* Phase 2: per-agent venture history (used to find the deceased's
               home place at notable-death time) and world-level totals (used
               by fire to weight target selection toward popular places). */
            places_record_venture_for_agent(it->world, self,    place_id);
            places_record_venture_for_agent(it->world, partner, place_id);
            places_record_venture_world(place_id);
        }

        /* Witness-world: bump LastActive for both venturers so the places
           inheritance scan can filter to the recently-active cohort. Cheap
           ecs_set on an already-present component (no archetype change). */
        ecs_set(it->world, self,    LastActive, { tick });
        ecs_set(it->world, partner, LastActive, { tick });

        event_log_write(tick, success ? "venture_success" : "venture_failure",
                        self, partner, new_trust, place_id);
    }
}

void VenturesModuleImport(ecs_world_t *world) {
    ECS_MODULE(world, VenturesModule);

    q_alive = ecs_query(world, {
        .terms = {
            { .id = Alive }
        }
    });

    /* Runs after metabolism so agents act on their post-decay resource level. */
    ecs_system(world, {
        .entity = ecs_entity(world, {
            .name = "VentureSystem",
            .add  = ecs_ids(ecs_dependson(EcsOnUpdate))
        }),
        .query.terms = {
            { .id = ecs_id(Resources),     .inout = EcsInOut },
            { .id = ecs_id(VentureChance), .inout = EcsIn    },
            { .id = ecs_id(TrustBaseline), .inout = EcsIn    },
            { .id = Alive }
        },
        .callback = VentureSystem
    });
}
