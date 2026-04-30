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
    /* If 1, also write a snapshot at tick 0 so the initial population's
       traits are captured before any of them die. Default 0 (off) so
       legacy scenarios on this branch still produce the same snapshot
       set as on main. Witness scenarios opt in. */
    int      snapshot_at_tick_zero; /* default 0 */

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

    /* --- Witness-world: places module knobs.
       Determinism is preserved across these toggles within witness-world,
       but flipping `places_enabled` changes the simulation trajectory. --- */
    int      places_enabled;               /* default 0; witness scenarios set 1 */
    int      place_inherit_window;         /* ticks of recent agents to inherit from; default = spawn_interval */
    float    place_inherit_strength;       /* coefficient on inherited mean weights; default 0.2 */
    float    place_pref_gain_on_success;   /* signed weight bump per success at a place; default 0.05 */
    float    place_pref_loss_on_failure;   /* magnitude of decrement per failure; default 0.07 */
    float    place_pref_decay;             /* per-tick drift toward 0; default 0.001 */
    /* Softmax temperature on the per-place selection probability:
       weight[p] = exp(temperature * mean(initiator.w[p], partner.w[p])).
       Higher → sharper preferences; 0 → uniform regardless of weights.
       Independent of the trust softmax temperature in partner selection so
       the two can be ablated separately. Default 2.0 mirrors that constant. */
    float    place_pref_temperature;       /* default 2.0 */

    /* --- Witness-world: world_events module (Phase 2). Touchstone events
       broadcast to multiple agents at once: fires at a place, notable deaths.
       Determinism preserved within witness-world via an isolated PCG sub-
       stream (toggling this module on/off does not perturb places' draws or
       the global stream). --- */
    int      world_events_enabled;         /* default 0; witness scenarios opt in */
    /* Fire trigger: per tick, draw from world-events stream; with this prob,
       a fire fires. Default 1e-4 ⇒ ~3 fires per 30k ticks. */
    float    fire_per_tick_prob;           /* default 1e-4 */
    /* Magnitude of LocationPrefs hit on fire. Each agent's weight at the
       burned place shifts by -fire_pref_hit * (1 + |prior_weight|). Strong
       priors take a larger hit (the place mattered to them); strangers
       take the floor hit. */
    float    fire_pref_hit;                /* default 0.3 */
    /* Notable death qualifier: how many strong bonds the deceased must
       have for their death to broadcast as a witnessed touchstone event. */
    int      notable_death_min_strong_bonds; /* default 3 */
    /* Trust threshold above which a relationship counts as "strong" for
       both the qualifier above and for selecting which surviving partners
       witness the death. */
    float    notable_death_trust_threshold;  /* default 0.5 */
    /* TrustBaseline hit per witnessing partner. Scaled by their pairwise
       trust to the deceased — closer bonds mourn more. */
    float    notable_death_baseline_hit;     /* default 0.05 */

    /* --- Witness-world: memory module (Phase 3). Cultural transmission of
       stories along the social-ancestor edge already used for LocationPrefs
       inheritance. Stories decay continuously from their origin event time
       (decay-per-year), not per-transmission, so two holders at the same
       moment see the same fidelity for the same story regardless of path. --- */
    int      memory_enabled;                 /* default 0; witness scenarios opt in */
    /* Per-year multiplicative decay applied to each story's fidelity:
         fidelity(t) = decay ^ ((t - origin_tick) / 365)
       0.92 ⇒ ~28-year half-life; 0.97 ⇒ ~76 years; 0.85 ⇒ ~13 years.
       Calibrated by sweep over {0.85, 0.90, 0.92, 0.95, 0.97} × 4 seeds:
       0.92 produced the cleanest tri-tier distribution at biography
       moment (~20% high / ~53% mid / ~27% dropped of inherited slots),
       with all three tiers represented in nontrivial proportion. 0.97
       saturates inventories; 0.85 strips too aggressively; 0.95 is
       defensible and close. */
    float    story_inherit_decay;            /* default 0.92 (sweep-calibrated) */
    /* Fidelity below which a story is dropped from inventory and not
       transmitted further. Acts as a floor on the integration. */
    float    story_min_fidelity;             /* default 0.10 */

    char     output_dir[512];
} Config;

/* Load a key=value scenario file. Exits the process on error. */
Config config_load(const char *path);

#endif
