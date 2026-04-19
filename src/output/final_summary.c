#include "output/final_summary.h"

#include "core/world.h"
#include "modules/agents.h"
#include "modules/relationships.h"

#include <stdio.h>

void final_summary_write(ecs_world_t *world, const Config *cfg, const char *path) {
    SimState *st = world_state(world);

    /* Final population count. */
    int pop = 0;
    ecs_query_t *q = ecs_query(world, {
        .terms = { { .id = Alive } }
    });
    ecs_iter_t it = ecs_query_iter(world, q);
    while (ecs_query_next(&it)) pop += it.count;
    ecs_query_fini(q);

    int edges = 0;
    ecs_query_t *qr = ecs_query(world, {
        .terms = { { .id = ecs_id(TrustStrength), .inout = EcsIn } }
    });
    ecs_iter_t rit = ecs_query_iter(world, qr);
    while (ecs_query_next(&rit)) edges += rit.count;
    ecs_query_fini(qr);

    FILE *fp = fopen(path, "w");
    if (!fp) return;

    fprintf(fp, "=== simulation summary ===\n");
    fprintf(fp, "ticks_run             %d\n",  st->current_tick);
    fprintf(fp, "final_population      %d\n",  pop);
    fprintf(fp, "peak_population       %d\n",  st->peak_population);
    fprintf(fp, "total_births          %ld\n", st->births);
    fprintf(fp, "total_deaths          %ld\n", st->deaths);
    fprintf(fp, "final_relationships   %d\n",  edges);
    fprintf(fp, "ventures_attempted    %ld\n", st->ventures_attempted);
    fprintf(fp, "ventures_succeeded    %ld\n", st->ventures_succeeded);
    fprintf(fp, "ventures_failed       %ld\n", st->ventures_failed);
    if (st->ventures_attempted > 0) {
        fprintf(fp, "success_rate          %.4f\n",
                (double)st->ventures_succeeded / (double)st->ventures_attempted);
    }

    fprintf(fp, "\n=== config echo ===\n");
    fprintf(fp, "seed                     %llu\n", (unsigned long long)cfg->seed);
    fprintf(fp, "max_ticks                %d\n",   cfg->max_ticks);
    fprintf(fp, "initial_population       %d\n",   cfg->initial_population);
    fprintf(fp, "initial_resources_min    %.4f\n", (double)cfg->initial_resources_min);
    fprintf(fp, "initial_resources_max    %.4f\n", (double)cfg->initial_resources_max);
    fprintf(fp, "metabolism               %.4f\n", (double)cfg->metabolism);
    fprintf(fp, "venture_cost             %.4f\n", (double)cfg->venture_cost);
    fprintf(fp, "venture_reward           %.4f\n", (double)cfg->venture_reward);
    fprintf(fp, "base_success_prob        %.4f\n", (double)cfg->base_success_prob);
    fprintf(fp, "trust_success_weight     %.4f\n", (double)cfg->trust_success_weight);
    fprintf(fp, "trust_gain_on_success    %.4f\n", (double)cfg->trust_gain_on_success);
    fprintf(fp, "trust_loss_on_failure    %.4f\n", (double)cfg->trust_loss_on_failure);
    fprintf(fp, "trust_decay              %.6f\n", (double)cfg->trust_decay);
    fprintf(fp, "trust_baseline           %.4f\n", (double)cfg->trust_baseline);
    fprintf(fp, "exploration_rate         %.4f\n", (double)cfg->exploration_rate);
    fprintf(fp, "venture_chance           %.4f\n", (double)cfg->venture_chance);
    fprintf(fp, "spawn_interval           %d\n",   cfg->spawn_interval);
    fprintf(fp, "snapshot_interval        %d\n",   cfg->snapshot_interval);

    fprintf(fp, "\n=== extension knobs ===\n");
    fprintf(fp, "coop_quality_mean              %.4f\n", (double)cfg->coop_quality_mean);
    fprintf(fp, "coop_quality_sigma             %.4f\n", (double)cfg->coop_quality_sigma);
    fprintf(fp, "coop_quality_success_weight    %.4f\n", (double)cfg->coop_quality_success_weight);
    fprintf(fp, "coop_quality_payoff_scale      %.4f\n", (double)cfg->coop_quality_payoff_scale);
    fprintf(fp, "trait_quality_correlation      %.4f\n", (double)cfg->trait_quality_correlation);
    fprintf(fp, "trait_generalization_strength  %.4f\n", (double)cfg->trait_generalization_strength);
    fprintf(fp, "search_base_k                  %d\n",   cfg->search_base_k);
    fprintf(fp, "search_min_k                   %d\n",   cfg->search_min_k);
    fprintf(fp, "search_max_k                   %d\n",   cfg->search_max_k);
    fprintf(fp, "search_slope                   %.4f\n", (double)cfg->search_slope);
    fprintf(fp, "search_wealth_threshold        %.4f\n", (double)cfg->search_wealth_threshold);
    fprintf(fp, "search_cost_per_candidate      %.4f\n", (double)cfg->search_cost_per_candidate);
    fprintf(fp, "initial_resource_rich_frac     %.4f\n", (double)cfg->initial_resource_rich_frac);
    fprintf(fp, "initial_resources_rich_min     %.4f\n", (double)cfg->initial_resources_rich_min);
    fprintf(fp, "initial_resources_rich_max     %.4f\n", (double)cfg->initial_resources_rich_max);
    fprintf(fp, "intervention_tick              %d\n",   cfg->intervention_tick);
    fprintf(fp, "intervention_exploration_rate  %.4f\n", (double)cfg->intervention_exploration_rate);
    fprintf(fp, "intervention_generalization    %.4f\n", (double)cfg->intervention_generalization);
    fprintf(fp, "intervention_newentrant_boost  %.4f\n", (double)cfg->intervention_newentrant_boost);

    fclose(fp);
}
