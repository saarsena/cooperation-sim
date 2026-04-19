#include "output/per_tick_metrics.h"

#include "core/world.h"
#include "modules/agents.h"
#include "modules/relationships.h"

#include "stb_ds.h"

#include <stdio.h>
#include <stdlib.h>

static FILE        *g_fp = NULL;
static ecs_query_t *q_agents = NULL;
static ecs_query_t *q_rels   = NULL;
static float       *g_res_buf = NULL;
static int          g_res_cap = 0;

/* entity_id → trait group key; used to classify relationship endpoints as
   within-group or across-group. Rebuilt each tick to stay in sync with
   births/deaths without worrying about recycled entity IDs. */
typedef struct { ecs_entity_t key; int value; } EntGroup;
static EntGroup *g_ent_group = NULL;

int per_tick_metrics_open(const char *path) {
    g_fp = fopen(path, "w");
    if (!g_fp) return -1;
    fprintf(g_fp,
        "tick,population,mean_trust,strong_edges,resources_gini,total_resources,"
        "within_group_trust,across_group_trust,trust_gap,"
        "gini_group_mean,mean_search_effort_q1,mean_search_effort_q4\n");
    return 0;
}

void per_tick_metrics_close(void) {
    if (g_fp) {
        fclose(g_fp);
        g_fp = NULL;
    }
    free(g_res_buf);
    g_res_buf = NULL;
    g_res_cap = 0;
    hmfree(g_ent_group);
    g_ent_group = NULL;
}

static int cmp_float(const void *a, const void *b) {
    float fa = *(const float *)a, fb = *(const float *)b;
    if (fa < fb) return -1;
    if (fa > fb) return  1;
    return 0;
}

static float gini(float *values, int n) {
    if (n <= 1) return 0.0f;
    float min = values[0];
    for (int i = 1; i < n; i++) if (values[i] < min) min = values[i];
    if (min < 0) {
        for (int i = 0; i < n; i++) values[i] -= min;
    }
    qsort(values, n, sizeof(float), cmp_float);
    double sum = 0.0, weighted = 0.0;
    for (int i = 0; i < n; i++) {
        sum      += values[i];
        weighted += (double)(i + 1) * values[i];
    }
    if (sum <= 0.0) return 0.0f;
    double g = (2.0 * weighted) / ((double)n * sum) - (double)(n + 1) / (double)n;
    return (float)g;
}

static void PerTickMetricsSystem(ecs_iter_t *it) {
    if (!g_fp) return;

    ecs_world_t *world = it->world;
    SimState    *st    = world_state(world);
    const int    tick  = st->current_tick;

    int   pop = 0;
    float total_res = 0.0f;

    /* Per-group tallies for resource-Gini aggregation. */
    float group_sum[TRAITS_GROUP_COUNT];
    int   group_cnt[TRAITS_GROUP_COUNT];
    for (int gi = 0; gi < TRAITS_GROUP_COUNT; gi++) {
        group_sum[gi] = 0.0f;
        group_cnt[gi] = 0;
    }

    /* Rebuild the entity→group map from scratch each tick. Keeps us safe from
       stale relationship-pair endpoints (agents die mid-run). */
    hmfree(g_ent_group);
    g_ent_group = NULL;

    ecs_iter_t ait = ecs_query_iter(world, q_agents);
    while (ecs_query_next(&ait)) {
        Resources *r  = ecs_field(&ait, Resources, 0);
        Traits    *tr = ecs_field(&ait, Traits,    1);
        for (int i = 0; i < ait.count; i++) {
            if (pop >= g_res_cap) {
                g_res_cap = g_res_cap ? g_res_cap * 2 : 64;
                g_res_buf = realloc(g_res_buf, (size_t)g_res_cap * sizeof(float));
            }
            g_res_buf[pop++] = r[i].amount;
            total_res += r[i].amount;

            int gk = traits_group_key(&tr[i]);
            group_sum[gk] += r[i].amount;
            group_cnt[gk] += 1;
            hmput(g_ent_group, ait.entities[i], gk);
        }
    }

    /* Trust aggregation, split by whether the pair shares all traits. */
    double trust_sum      = 0.0;
    double within_sum     = 0.0;
    double across_sum     = 0.0;
    int    edges  = 0;
    int    within = 0;
    int    across = 0;
    int    strong = 0;
    const float strong_threshold = 0.5f;

    ecs_iter_t rit = ecs_query_iter(world, q_rels);
    while (ecs_query_next(&rit)) {
        RelationshipPair *p = ecs_field(&rit, RelationshipPair, 0);
        TrustStrength    *t = ecs_field(&rit, TrustStrength,    1);
        for (int i = 0; i < rit.count; i++) {
            float tv = t[i].value;
            trust_sum += tv;
            edges++;
            if (tv >= strong_threshold) strong++;

            ptrdiff_t ia = hmgeti(g_ent_group, p[i].a);
            ptrdiff_t ib = hmgeti(g_ent_group, p[i].b);
            if (ia >= 0 && ib >= 0) {
                int ga = g_ent_group[ia].value;
                int gb = g_ent_group[ib].value;
                if (ga == gb) { within_sum += tv; within++; }
                else          { across_sum += tv; across++; }
            }
        }
    }

    float mean_trust   = (edges > 0) ? (float)(trust_sum / edges) : 0.0f;
    float within_trust = (within > 0) ? (float)(within_sum / within) : 0.0f;
    float across_trust = (across > 0) ? (float)(across_sum / across) : 0.0f;
    float trust_gap    = within_trust - across_trust;

    /* Per-group mean resources, then Gini over those group means.
       Interpretation: the higher this is, the more stratified resources are
       across trait groups (independent of within-group spread). */
    float group_means[TRAITS_GROUP_COUNT];
    int   n_nonempty = 0;
    for (int gi = 0; gi < TRAITS_GROUP_COUNT; gi++) {
        if (group_cnt[gi] > 0) {
            group_means[n_nonempty++] = group_sum[gi] / (float)group_cnt[gi];
        }
    }
    float gini_group_mean = (n_nonempty >= 2) ? gini(group_means, n_nonempty) : 0.0f;

    /* Mean search effort by wealth quartile — a direct check on Rule 6. */
    float q1_effort = 0.0f, q4_effort = 0.0f;
    const Config *cfg = world_cfg(world);
    if (cfg && cfg->search_base_k > 0 && pop >= 4) {
        float sorted[pop];
        for (int i = 0; i < pop; i++) sorted[i] = g_res_buf[i];
        qsort(sorted, pop, sizeof(float), cmp_float);
        int q1_top = pop / 4;
        int q4_bot = pop - pop / 4;
        float s1 = 0.0f, s4 = 0.0f;
        int   c1 = 0, c4 = 0;
        for (int i = 0; i < q1_top; i++) {
            float over = sorted[i] - cfg->search_wealth_threshold;
            if (over < 0.0f) over = 0.0f;
            float k = (float)cfg->search_base_k + cfg->search_slope * over;
            if (k < (float)cfg->search_min_k) k = (float)cfg->search_min_k;
            if (k > (float)cfg->search_max_k) k = (float)cfg->search_max_k;
            s1 += k; c1++;
        }
        for (int i = q4_bot; i < pop; i++) {
            float over = sorted[i] - cfg->search_wealth_threshold;
            if (over < 0.0f) over = 0.0f;
            float k = (float)cfg->search_base_k + cfg->search_slope * over;
            if (k < (float)cfg->search_min_k) k = (float)cfg->search_min_k;
            if (k > (float)cfg->search_max_k) k = (float)cfg->search_max_k;
            s4 += k; c4++;
        }
        q1_effort = (c1 > 0) ? s1 / c1 : 0.0f;
        q4_effort = (c4 > 0) ? s4 / c4 : 0.0f;
    }

    float g = gini(g_res_buf, pop);

    fprintf(g_fp, "%d,%d,%.6f,%d,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.4f,%.4f\n",
            tick, pop, mean_trust, strong, g, total_res,
            within_trust, across_trust, trust_gap,
            gini_group_mean, q1_effort, q4_effort);

    if (pop > st->peak_population) st->peak_population = pop;
}

void per_tick_metrics_register(ecs_world_t *world) {
    q_agents = ecs_query(world, {
        .terms = {
            { .id = ecs_id(Resources), .inout = EcsIn },
            { .id = ecs_id(Traits),    .inout = EcsIn },
            { .id = Alive }
        }
    });
    q_rels = ecs_query(world, {
        .terms = {
            { .id = ecs_id(RelationshipPair), .inout = EcsIn },
            { .id = ecs_id(TrustStrength),    .inout = EcsIn }
        }
    });

    ecs_system(world, {
        .entity = ecs_entity(world, {
            .name = "PerTickMetricsSystem",
            .add  = ecs_ids(ecs_dependson(EcsOnStore))
        }),
        .callback = PerTickMetricsSystem
    });
}
