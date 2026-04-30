#include "output/snapshots.h"

#include "core/world.h"
#include "modules/agents.h"
#include "modules/memory.h"
#include "modules/places.h"
#include "modules/relationships.h"

#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static char         g_dir[512];
static ecs_query_t *q_agents = NULL;
static ecs_query_t *q_rels   = NULL;
static ecs_query_t *q_locprefs = NULL;
static ecs_query_t *q_stories  = NULL;

int snapshots_init(const char *dir) {
    size_t n = strlen(dir);
    if (n + 1 > sizeof g_dir) return -1;
    memcpy(g_dir, dir, n + 1);
    if (mkdir(dir, 0755) != 0) {
        /* Already existing is fine — parent creation handles first-run check. */
    }
    return 0;
}

static void SnapshotsSystem(ecs_iter_t *it) {
    ecs_world_t  *world = it->world;
    const Config *cfg   = world_cfg(world);
    SimState     *st    = world_state(world);
    const int     tick  = st->current_tick;

    /* Skip negative ticks (defensive). Tick 0 fires only when the scenario
       opts in via snapshot_at_tick_zero=1; that way legacy main-branch
       scenarios run on this branch produce the same snapshot set they
       always did, while witness scenarios get the initial population's
       traits captured before any of them die. */
    if (tick < 0) return;
    if (tick == 0 && !cfg->snapshot_at_tick_zero) return;
    if (tick % cfg->snapshot_interval != 0) return;

    char path[768];
    snprintf(path, sizeof path, "%s/tick_%06d.tsv", g_dir, tick);
    FILE *fp = fopen(path, "w");
    if (!fp) return;

    fprintf(fp, "# tick %d\n", tick);
    fprintf(fp, "[agents]\n");
    fprintf(fp, "entity\tresources\ttrust_baseline\tage\tventure_chance"
                "\ttraits\tcoop_quality\tgroup_key\n");

    ecs_iter_t ait = ecs_query_iter(world, q_agents);
    while (ecs_query_next(&ait)) {
        Resources     *r  = ecs_field(&ait, Resources,     0);
        TrustBaseline *tb = ecs_field(&ait, TrustBaseline, 1);
        Age           *a  = ecs_field(&ait, Age,           2);
        VentureChance *vc = ecs_field(&ait, VentureChance, 3);
        Traits        *tr = ecs_field(&ait, Traits,        4);
        CoopQuality   *cq = ecs_field(&ait, CoopQuality,   5);
        for (int i = 0; i < ait.count; i++) {
            char traits_str[TRAIT_COUNT * 3 + 1];
            int  off = 0;
            for (int d = 0; d < TRAIT_COUNT; d++) {
                off += snprintf(traits_str + off, sizeof traits_str - off,
                                d ? ",%u" : "%u", (unsigned)tr[i].v[d]);
            }
            fprintf(fp, "%llu\t%.4f\t%.4f\t%d\t%.4f\t%s\t%.4f\t%d\n",
                    (unsigned long long)ait.entities[i],
                    (double)r[i].amount, (double)tb[i].value,
                    a[i].ticks, (double)vc[i].p,
                    traits_str, (double)cq[i].value,
                    traits_group_key(&tr[i]));
        }
    }

    fprintf(fp, "\n[relationships]\n");
    fprintf(fp, "entity\tagent_a\tagent_b\ttrust\tage\tlast_reinforced\n");

    ecs_iter_t rit = ecs_query_iter(world, q_rels);
    while (ecs_query_next(&rit)) {
        RelationshipPair *p   = ecs_field(&rit, RelationshipPair, 0);
        TrustStrength    *ts  = ecs_field(&rit, TrustStrength,    1);
        RelationshipAge  *age = ecs_field(&rit, RelationshipAge,  2);
        LastReinforced   *lr  = ecs_field(&rit, LastReinforced,   3);
        for (int i = 0; i < rit.count; i++) {
            fprintf(fp, "%llu\t%llu\t%llu\t%.4f\t%d\t%d\n",
                    (unsigned long long)rit.entities[i],
                    (unsigned long long)p[i].a,
                    (unsigned long long)p[i].b,
                    (double)ts[i].value,
                    age[i].ticks,
                    lr[i].tick);
        }
    }

    /* Witness-world: places + per-agent location preferences. Sections are
       written even when places_enabled=0 so the format is stable; in that
       case the [places] section is empty and [location_prefs] has no rows. */
    fprintf(fp, "\n[places]\n");
    fprintf(fp, "place_index\tname\ttype\tfires\tdeaths\ttotal_ventures\n");
    if (cfg->places_enabled) {
        for (int i = 0; i < PLACES_COUNT; i++) {
            ecs_entity_t pe = places_entity_at(i);
            const PlaceMark *pm = pe ? ecs_get(world, pe, PlaceMark) : NULL;
            int fires  = pm ? pm->fires  : 0;
            int deaths = pm ? pm->deaths : 0;
            fprintf(fp, "%d\t%s\t%s\t%d\t%d\t%ld\n",
                    i, places_name(i), places_type(i),
                    fires, deaths, places_total_ventures_at(i));
        }
    }

    fprintf(fp, "\n[location_prefs]\n");
    fprintf(fp, "entity\tweights\n");
    if (cfg->places_enabled && q_locprefs) {
        ecs_iter_t lit = ecs_query_iter(world, q_locprefs);
        while (ecs_query_next(&lit)) {
            LocationPrefs *lp = ecs_field(&lit, LocationPrefs, 0);
            for (int i = 0; i < lit.count; i++) {
                fprintf(fp, "%llu\t",
                        (unsigned long long)lit.entities[i]);
                for (int p = 0; p < PLACES_COUNT; p++) {
                    fprintf(fp, p ? ",%.4f" : "%.4f", (double)lp[i].w[p]);
                }
                fputc('\n', fp);
            }
        }
    }

    /* Phase 3 stories. One row per (agent, slot). Format mirrors the
       events.log story_inherited rows so analysis scripts can either
       reconstruct from events or read snapshots directly. */
    fprintf(fp, "\n[stories]\n");
    fprintf(fp, "entity\torigin_tick\torigin_kind\torigin_place\t"
                "was_direct\tsource_was_origin\torigin_magnitude\tsource_id\n");
    if (cfg->memory_enabled && q_stories) {
        ecs_iter_t sit = ecs_query_iter(world, q_stories);
        while (ecs_query_next(&sit)) {
            Stories *st = ecs_field(&sit, Stories, 0);
            for (int i = 0; i < sit.count; i++) {
                for (int j = 0; j < st[i].n; j++) {
                    const Story *s = &st[i].slots[j];
                    fprintf(fp, "%llu\t%d\t%u\t%d\t%u\t%u\t%.4f\t%llu\n",
                            (unsigned long long)sit.entities[i],
                            s->origin_tick,
                            (unsigned)s->origin_kind,
                            (int)s->origin_place,
                            (unsigned)s->was_direct_witness,
                            (unsigned)s->source_was_origin_witness,
                            (double)s->origin_magnitude,
                            (unsigned long long)s->source_id);
                }
            }
        }
    }

    fclose(fp);
}

void snapshots_register(ecs_world_t *world) {
    q_agents = ecs_query(world, {
        .terms = {
            { .id = ecs_id(Resources),     .inout = EcsIn },
            { .id = ecs_id(TrustBaseline), .inout = EcsIn },
            { .id = ecs_id(Age),           .inout = EcsIn },
            { .id = ecs_id(VentureChance), .inout = EcsIn },
            { .id = ecs_id(Traits),        .inout = EcsIn },
            { .id = ecs_id(CoopQuality),   .inout = EcsIn },
            { .id = Alive }
        }
    });
    q_rels = ecs_query(world, {
        .terms = {
            { .id = ecs_id(RelationshipPair), .inout = EcsIn },
            { .id = ecs_id(TrustStrength),    .inout = EcsIn },
            { .id = ecs_id(RelationshipAge),  .inout = EcsIn },
            { .id = ecs_id(LastReinforced),   .inout = EcsIn }
        }
    });

    q_locprefs = ecs_query(world, {
        .terms = {
            { .id = ecs_id(LocationPrefs), .inout = EcsIn },
            { .id = Alive }
        }
    });

    q_stories = ecs_query(world, {
        .terms = {
            { .id = ecs_id(Stories), .inout = EcsIn },
            { .id = Alive }
        }
    });

    ecs_system(world, {
        .entity = ecs_entity(world, {
            .name = "SnapshotsSystem",
            .add  = ecs_ids(ecs_dependson(EcsOnStore))
        }),
        .callback = SnapshotsSystem
    });
}
