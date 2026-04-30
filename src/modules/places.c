#include "modules/places.h"

#include "core/rng.h"
#include "core/world.h"
#include "modules/agents.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

ECS_COMPONENT_DECLARE(PlaceName);
ECS_COMPONENT_DECLARE(PlaceType);
ECS_COMPONENT_DECLARE(PlaceIndex);
ECS_COMPONENT_DECLARE(PlaceMark);
ECS_COMPONENT_DECLARE(LocationPrefs);
ECS_COMPONENT_DECLARE(VentureCountByPlace);

/* The 12-place pool. Order is the persistent place index — once a name
   appears at index N here, it stays at N forever, so events.log entries from
   any run can be re-resolved against this table. New names go at the end of
   the list, never inserted in the middle. */
typedef struct PlaceDef {
    const char *type;
    const char *name;
} PlaceDef;

static const PlaceDef g_pool[PLACES_COUNT] = {
    { "tavern",  "Bill's"                 },
    { "tavern",  "Dancing Hall of Death"  },
    { "river",   "The Hidden Rapids"      },
    { "river",   "Jutt's Creek"           },
    { "house",   "A common house"         },
    { "house",   "A shabby place"         },
    { "field",   "A wheat field"          },
    { "field",   "A barley field"         },
    { "pasture", "The grazed pasture"     },
    { "pasture", "The fallow pasture"     },
    { "ruins",   "The Old One"            },
    { "ruins",   "Green Eyes"             },
};

/* Module state. */
static ecs_entity_t g_place_entities[PLACES_COUNT] = {0};
static int          g_initialized = 0;
static RngStream    g_places_rng;
static ecs_query_t *g_q_alive_prefs = NULL;

/* Phase 2: world-level total venture count per place. Used by world_events
   to weight fire target selection toward well-used places. Updated once per
   venture (not once per partner) by places_record_venture_world. */
static long g_total_ventures_per_place[PLACES_COUNT] = {0};

/* Diagnostic accumulators for inherited-prior variance.
   Per spawn we compute v = variance(inherited_weights) across the 12 places
   and accumulate sum(v) and sum(v^2). At end of run we report mean(v) and
   sd(v). Cost is a few flops per spawn. */
static double g_prior_var_sum    = 0.0;
static double g_prior_var_sum_sq = 0.0;
static long   g_prior_var_count  = 0;

/* Stable 64-bit identifier so the places sub-stream is independent of any
   stream the world_events or memory modules will later add. ASCII for
   "PLACES!". */
#define PLACES_STREAM_ID 0x504c4143455321ULL

static inline float clampf(float x, float lo, float hi) {
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

/* Per-tick: drift everyone's location weights toward 0. Mirrors trust_decay
   for the existing trust/marker fields. Magnitude controlled by
   cfg->place_pref_decay; runs only when places_enabled. */
static void LocationPrefsDecaySystem(ecs_iter_t *it) {
    const Config *cfg = world_cfg(it->world);
    if (!cfg->places_enabled) return;
    const float decay = cfg->place_pref_decay;
    if (decay <= 0.0f) return;

    LocationPrefs *lp = ecs_field(it, LocationPrefs, 0);
    for (int i = 0; i < it->count; i++) {
        for (int p = 0; p < PLACES_COUNT; p++) {
            float v = lp[i].w[p];
            if (v >  decay) v -= decay;
            else if (v < -decay) v += decay;
            else                 v  = 0.0f;
            lp[i].w[p] = v;
        }
    }
}

void PlacesModuleImport(ecs_world_t *world) {
    ECS_MODULE(world, PlacesModule);

    ECS_COMPONENT_DEFINE(world, PlaceName);
    ECS_COMPONENT_DEFINE(world, PlaceType);
    ECS_COMPONENT_DEFINE(world, PlaceIndex);
    ECS_COMPONENT_DEFINE(world, PlaceMark);
    ECS_COMPONENT_DEFINE(world, LocationPrefs);
    ECS_COMPONENT_DEFINE(world, VentureCountByPlace);

    g_q_alive_prefs = ecs_query(world, {
        .terms = {
            { .id = ecs_id(LocationPrefs), .inout = EcsIn },
            { .id = ecs_id(LastActive),    .inout = EcsIn },
            { .id = Alive }
        }
    });

    ecs_system(world, {
        .entity = ecs_entity(world, {
            .name = "LocationPrefsDecaySystem",
            .add  = ecs_ids(ecs_dependson(EcsOnUpdate))
        }),
        .query.terms = {
            { .id = ecs_id(LocationPrefs), .inout = EcsInOut },
            { .id = Alive }
        },
        .callback = LocationPrefsDecaySystem
    });
}

void places_init(ecs_world_t *world, const Config *cfg) {
    if (g_initialized) return;
    g_initialized = 1;

    rng_stream_init(&g_places_rng, cfg->seed, PLACES_STREAM_ID);

    for (int i = 0; i < PLACES_COUNT; i++) {
        ecs_entity_t e = ecs_new(world);
        PlaceName  n = { g_pool[i].name };
        PlaceType  t = { g_pool[i].type };
        PlaceIndex idx = { i };
        PlaceMark  pm = { 0, 0 };
        ecs_set_ptr(world, e, PlaceName,  &n);
        ecs_set_ptr(world, e, PlaceType,  &t);
        ecs_set_ptr(world, e, PlaceIndex, &idx);
        ecs_set_ptr(world, e, PlaceMark,  &pm);
        g_place_entities[i] = e;
    }
}

void places_record_venture_for_agent(ecs_world_t *world,
                                     ecs_entity_t agent,
                                     int place_index)
{
    if (place_index < 0 || place_index >= PLACES_COUNT) return;
    const VentureCountByPlace *cur = ecs_get(world, agent, VentureCountByPlace);
    VentureCountByPlace next;
    if (cur) next = *cur;
    else     memset(&next, 0, sizeof next);
    next.count[place_index] += 1;
    ecs_set_ptr(world, agent, VentureCountByPlace, &next);
}

void places_record_venture_world(int place_index) {
    if (place_index < 0 || place_index >= PLACES_COUNT) return;
    g_total_ventures_per_place[place_index] += 1;
}

long places_total_ventures_at(int place_index) {
    if (place_index < 0 || place_index >= PLACES_COUNT) return 0;
    return g_total_ventures_per_place[place_index];
}

const char *places_name(int idx) {
    if (idx < 0 || idx >= PLACES_COUNT) return NULL;
    return g_pool[idx].name;
}

const char *places_type(int idx) {
    if (idx < 0 || idx >= PLACES_COUNT) return NULL;
    return g_pool[idx].type;
}

ecs_entity_t places_entity_at(int idx) {
    if (idx < 0 || idx >= PLACES_COUNT) return 0;
    return g_place_entities[idx];
}

/* Read both agents' LocationPrefs (treating missing as zero), build a softmax
   over averaged weights, mix with uniform via exploration_rate, sample. */
int places_choose_for_venture(ecs_world_t *world,
                              ecs_entity_t initiator, ecs_entity_t partner,
                              float exploration_rate)
{
    const Config *cfg = world_cfg(world);
    const LocationPrefs *lpa = ecs_get(world, initiator, LocationPrefs);
    const LocationPrefs *lpb = ecs_get(world, partner,   LocationPrefs);

    int explore = (rng_stream_float(&g_places_rng) < exploration_rate) ? 1 : 0;

    float weights[PLACES_COUNT];
    if (explore) {
        for (int i = 0; i < PLACES_COUNT; i++) weights[i] = 1.0f;
    } else {
        const float temperature = cfg->place_pref_temperature;
        for (int i = 0; i < PLACES_COUNT; i++) {
            float wa = lpa ? lpa->w[i] : 0.0f;
            float wb = lpb ? lpb->w[i] : 0.0f;
            float mean = 0.5f * (wa + wb);
            weights[i] = expf(temperature * mean);
        }
    }

    float total = 0.0f;
    for (int i = 0; i < PLACES_COUNT; i++) total += weights[i];
    if (total <= 0.0f) {
        /* Degenerate — pick uniformly. */
        return rng_stream_range_i(&g_places_rng, 0, PLACES_COUNT - 1);
    }

    float r = rng_stream_float(&g_places_rng) * total;
    float acc = 0.0f;
    for (int i = 0; i < PLACES_COUNT; i++) {
        acc += weights[i];
        if (r <= acc) return i;
    }
    return PLACES_COUNT - 1;
}

void places_update_pref_on_outcome(ecs_world_t *world,
                                   ecs_entity_t agent,
                                   int place_index, float delta)
{
    if (place_index < 0 || place_index >= PLACES_COUNT) return;
    const LocationPrefs *cur = ecs_get(world, agent, LocationPrefs);
    LocationPrefs next;
    if (cur) next = *cur;
    else     memset(&next, 0, sizeof next);
    next.w[place_index] = clampf(next.w[place_index] + delta, -1.0f, 1.0f);
    ecs_set_ptr(world, agent, LocationPrefs, &next);
}

ecs_entity_t places_compute_inherited_prior(ecs_world_t *world,
                                            const Config *cfg,
                                            LocationPrefs *out)
{
    memset(out, 0, sizeof *out);
    if (!cfg->places_enabled) return 0;
    if (!g_q_alive_prefs) return 0;

    /* Single-ancestor reservoir sampling over the recency-windowed cohort.

       Earlier we averaged the cohort's LocationPrefs and scaled by
       place_inherit_strength. That produced per-spawn variance of ~0.000079
       — essentially flat — because the population mean across places is
       itself flat (variance 0.000129). Individual agents have differentiated
       preferences (per-agent within-variance 0.0075), but their preferences
       are idiosyncratic noise on identical place-mechanics; averaging across
       agents cancels exactly the signal we wanted to inherit.

       Sampling one ancestor preserves the full per-agent within-variance.
       The new agent inherits one specific predecessor's pattern, scaled
       down by the strength coefficient. Lineages of place-preference
       carry forward; the "social ancestors" framing in the spec lands
       truthfully in biographies. */
    const int now    = world_state(world)->current_tick;
    const int window = cfg->place_inherit_window;

    long seen = 0;
    LocationPrefs picked = {0};
    ecs_entity_t  picked_id = 0;
    ecs_iter_t it = ecs_query_iter(world, g_q_alive_prefs);
    while (ecs_query_next(&it)) {
        const LocationPrefs *lp = ecs_field(&it, LocationPrefs, 0);
        const LastActive    *la = ecs_field(&it, LastActive,    1);
        for (int i = 0; i < it.count; i++) {
            if (now - la[i].tick >= window) continue;
            seen++;
            /* Reservoir sampling, k=1: replace the current pick with the
               new candidate with probability 1/seen. After the loop, every
               candidate has equal probability of having been the final
               pick. RNG draws come from the places sub-stream so toggling
               this mechanism doesn't perturb other modules. */
            if (rng_stream_range_i(&g_places_rng, 0, (int)(seen - 1)) == 0) {
                picked    = lp[i];
                picked_id = it.entities[i];
            }
        }
    }
    if (seen == 0) return 0;

    const float k = cfg->place_inherit_strength;
    for (int p = 0; p < PLACES_COUNT; p++) {
        out->w[p] = picked.w[p] * k;
    }

    /* Diagnostic: per-spawn variance across the 12 inherited weights.
       Flat priors ⇒ no preference signal carried to the new agent ⇒ the
       inheritance simplification is doing nothing and the
       windowed-cohort version is needed. */
    double pmean = 0.0;
    for (int p = 0; p < PLACES_COUNT; p++) pmean += out->w[p];
    pmean /= (double)PLACES_COUNT;
    double pvar = 0.0;
    for (int p = 0; p < PLACES_COUNT; p++) {
        double d = out->w[p] - pmean;
        pvar += d * d;
    }
    pvar /= (double)PLACES_COUNT;
    g_prior_var_sum    += pvar;
    g_prior_var_sum_sq += pvar * pvar;
    g_prior_var_count  += 1;

    return picked_id;
}

void places_log_summary(void *fp_) {
    FILE *fp = (FILE *)fp_;
    if (g_prior_var_count == 0) {
        fprintf(fp, "places: no inherited priors computed "
                    "(places_enabled=0, or no spawns).\n");
        return;
    }
    double mean = g_prior_var_sum / (double)g_prior_var_count;
    double mean_sq = g_prior_var_sum_sq / (double)g_prior_var_count;
    double v = mean_sq - mean * mean;
    if (v < 0.0) v = 0.0;
    double sd = sqrt(v);
    fprintf(fp,
        "places: %ld inherited priors at spawn — per-spawn variance over "
        "12 weights: mean=%.6f sd=%.6f\n",
        g_prior_var_count, mean, sd);
}
