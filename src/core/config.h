#ifndef RELATIONSHIPS_CORE_CONFIG_H
#define RELATIONSHIPS_CORE_CONFIG_H

#include <stdint.h>

typedef struct Config {
    uint64_t seed;
    int      max_ticks;
    int      initial_population;

    float    initial_resources_min;
    float    initial_resources_max;
    float    metabolism;

    float    venture_cost;
    float    venture_reward;
    float    base_success_prob;
    float    trust_success_weight;

    float    trust_gain_on_success;
    float    trust_loss_on_failure;
    float    trust_decay;
    float    trust_baseline;

    float    exploration_rate;
    float    venture_chance;

    int      spawn_interval;
    int      snapshot_interval;
    int      log_events;            /* 0 = skip events.log entirely, 1 = write */

    /* --- 7-rule extension knobs; all default to "disabled" so omitting them
       reproduces the pre-extension dynamics exactly. --- */

    /* Hidden cooperative quality drawn at spawn. Two uses:
       - Shifts venture success probability by coop_quality_success_weight * mean(qA,qB).
       - Scales payoff by (1 + coop_quality_payoff_scale * mean(qA,qB)).
       When both weights are 0, CoopQuality has no effect.                              */
    float    coop_quality_mean;            /* default 0.5  */
    float    coop_quality_sigma;           /* default 0.0 → all agents identical */
    float    coop_quality_success_weight;  /* default 0.0 → hidden quality ignored */
    float    coop_quality_payoff_scale;    /* default 0.0 → flat reward regardless of q */
    /* Correlation between visible traits and hidden quality:
       0 → traits are pure markers (recommended default)
       1 → traits fully determine quality.                                               */
    float    trait_quality_correlation;    /* default 0.0 */

    /* Rule 4: trust generalization strength. 0 disables. */
    float    trait_generalization_strength; /* default 0.0 */

    /* Rule 5/6: costly search with wealth-driven selectivity.
       Effective search depth k = clamp(base_k + slope*max(0, resources-wealth_threshold),
                                       min_k, max_k).
       Search cost = k * cost_per_candidate, deducted from searcher's resources. */
    int      search_base_k;                /* default 0 → use legacy linear scan */
    int      search_min_k;                 /* default 1 */
    int      search_max_k;                 /* default 1024 */
    float    search_slope;                 /* candidates per resource-unit over threshold */
    float    search_wealth_threshold;      /* resource level above which selectivity grows */
    float    search_cost_per_candidate;    /* per-candidate energy cost */

    /* Rule 7 / stratification lever: if > 0, draw initial_resources_min/max from
       a bimodal distribution where a fraction `initial_resource_rich_frac` of new
       spawns start at `initial_resources_rich_*`. Default 0 disables. */
    float    initial_resource_rich_frac;   /* default 0.0 */
    float    initial_resources_rich_min;   /* default = initial_resources_min */
    float    initial_resources_rich_max;   /* default = initial_resources_max */

    /* Intervention lever: from this tick onward, force exploration_rate to the
       given value. -1 disables the intervention. */
    int      intervention_tick;            /* default -1 */
    float    intervention_exploration_rate;/* default 0.0 */
    float    intervention_generalization;  /* default -1 → leave unchanged */
    float    intervention_newentrant_boost;/* multiplier for new-spawn initial resources, default 1.0 */

    char     output_dir[512];
} Config;

/* Load a key=value scenario file. Exits the process on error. */
Config config_load(const char *path);

#endif
