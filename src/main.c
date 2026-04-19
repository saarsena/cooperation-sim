#include "flecs.h"

#include "core/config.h"
#include "core/rng.h"
#include "core/world.h"
#include "modules/agents.h"
#include "modules/relationships.h"
#include "modules/ventures.h"
#include "output/final_summary.h"
#include "output/output.h"

#include <stdio.h>

static int count_alive(ecs_world_t *world) {
    ecs_query_t *q = ecs_query(world, {
        .terms = { { .id = Alive } }
    });
    int total = 0;
    ecs_iter_t it = ecs_query_iter(world, q);
    while (ecs_query_next(&it)) total += it.count;
    ecs_query_fini(q);
    return total;
}

int main(int argc, char **argv) {
    const char *scenario = (argc > 1) ? argv[1] : "scenarios/default.conf";

    Config cfg = config_load(scenario);
    rng_seed(cfg.seed);

    ecs_world_t *world = ecs_init();

    world_register_singletons(world);
    world_set_config(world, &cfg);

    ECS_IMPORT(world, AgentsModule);
    ECS_IMPORT(world, RelationshipsModule);
    ECS_IMPORT(world, VenturesModule);

    output_register_systems(world);

    if (output_open(&cfg) != 0) {
        ecs_fini(world);
        return 1;
    }

    for (int i = 0; i < cfg.initial_population; i++) {
        spawn_agent(world, &cfg);
    }

    SimState *st = world_state(world);

    for (int tick = 0; tick < cfg.max_ticks; tick++) {
        st->current_tick = tick;
        ecs_progress(world, 1.0);
        if (count_alive(world) == 0) {
            fprintf(stderr, "extinction at tick %d\n", tick);
            break;
        }
    }

    char summary_path[768];
    snprintf(summary_path, sizeof summary_path, "%s/summary.txt", cfg.output_dir);
    final_summary_write(world, &cfg, summary_path);

    output_close();
    relationships_cleanup();
    ecs_fini(world);
    return 0;
}
