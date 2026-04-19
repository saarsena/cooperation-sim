#include "core/config.h"

#include <ctype.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void trim(char *s) {
    size_t n = strlen(s);
    while (n > 0 && isspace((unsigned char)s[n - 1])) s[--n] = '\0';
    size_t i = 0;
    while (s[i] && isspace((unsigned char)s[i])) i++;
    if (i > 0) memmove(s, s + i, strlen(s + i) + 1);
}

static void die(const char *path, int lineno, const char *msg) {
    fprintf(stderr, "config error (%s:%d): %s\n", path, lineno, msg);
    exit(1);
}

typedef enum { T_U64, T_INT, T_FLOAT, T_STR } Ty;

typedef struct {
    const char *key;
    Ty          ty;
    size_t      off;
    size_t      cap;
    int         required;    /* 1 = must appear; 0 = optional (defaulted) */
    int         seen;
} Slot;

#define OFF(f) offsetof(Config, f)
#define REQ 1
#define OPT 0

Config config_load(const char *path) {
    Config cfg;
    memset(&cfg, 0, sizeof cfg);

    /* Defaults for optional keys. Set before parsing; parser overwrites when seen. */
    cfg.coop_quality_mean             = 0.5f;
    cfg.coop_quality_sigma            = 0.0f;
    cfg.coop_quality_success_weight   = 0.0f;
    cfg.coop_quality_payoff_scale     = 0.0f;
    cfg.trait_quality_correlation     = 0.0f;
    cfg.trait_generalization_strength = 0.0f;
    cfg.search_base_k                 = 0;      /* 0 ⇒ legacy linear-scan partner pick */
    cfg.search_min_k                  = 1;
    cfg.search_max_k                  = 1024;
    cfg.search_slope                  = 0.0f;
    cfg.search_wealth_threshold       = 0.0f;
    cfg.search_cost_per_candidate     = 0.0f;
    cfg.initial_resource_rich_frac    = 0.0f;
    cfg.initial_resources_rich_min    = 0.0f;   /* resolved after parse */
    cfg.initial_resources_rich_max    = 0.0f;
    cfg.intervention_tick             = -1;
    cfg.intervention_exploration_rate = 0.0f;
    cfg.intervention_generalization   = -1.0f;
    cfg.intervention_newentrant_boost = 1.0f;

    Slot slots[] = {
        { "seed",                   T_U64,   OFF(seed),                   0,   REQ, 0 },
        { "max_ticks",              T_INT,   OFF(max_ticks),              0,   REQ, 0 },
        { "initial_population",     T_INT,   OFF(initial_population),     0,   REQ, 0 },
        { "initial_resources_min",  T_FLOAT, OFF(initial_resources_min),  0,   REQ, 0 },
        { "initial_resources_max",  T_FLOAT, OFF(initial_resources_max),  0,   REQ, 0 },
        { "metabolism",             T_FLOAT, OFF(metabolism),             0,   REQ, 0 },
        { "venture_cost",           T_FLOAT, OFF(venture_cost),           0,   REQ, 0 },
        { "venture_reward",         T_FLOAT, OFF(venture_reward),         0,   REQ, 0 },
        { "base_success_prob",      T_FLOAT, OFF(base_success_prob),      0,   REQ, 0 },
        { "trust_success_weight",   T_FLOAT, OFF(trust_success_weight),   0,   REQ, 0 },
        { "trust_gain_on_success",  T_FLOAT, OFF(trust_gain_on_success),  0,   REQ, 0 },
        { "trust_loss_on_failure",  T_FLOAT, OFF(trust_loss_on_failure),  0,   REQ, 0 },
        { "trust_decay",            T_FLOAT, OFF(trust_decay),            0,   REQ, 0 },
        { "trust_baseline",         T_FLOAT, OFF(trust_baseline),         0,   REQ, 0 },
        { "exploration_rate",       T_FLOAT, OFF(exploration_rate),       0,   REQ, 0 },
        { "venture_chance",         T_FLOAT, OFF(venture_chance),         0,   REQ, 0 },
        { "spawn_interval",         T_INT,   OFF(spawn_interval),         0,   REQ, 0 },
        { "snapshot_interval",      T_INT,   OFF(snapshot_interval),      0,   REQ, 0 },
        { "log_events",             T_INT,   OFF(log_events),             0,   REQ, 0 },
        { "output_dir",             T_STR,   OFF(output_dir),             sizeof cfg.output_dir, REQ, 0 },

        /* Optional — all default sensibly so existing .conf files still work. */
        { "coop_quality_mean",             T_FLOAT, OFF(coop_quality_mean),             0, OPT, 0 },
        { "coop_quality_sigma",            T_FLOAT, OFF(coop_quality_sigma),            0, OPT, 0 },
        { "coop_quality_success_weight",   T_FLOAT, OFF(coop_quality_success_weight),   0, OPT, 0 },
        { "coop_quality_payoff_scale",     T_FLOAT, OFF(coop_quality_payoff_scale),     0, OPT, 0 },
        { "trait_quality_correlation",     T_FLOAT, OFF(trait_quality_correlation),     0, OPT, 0 },
        { "trait_generalization_strength", T_FLOAT, OFF(trait_generalization_strength), 0, OPT, 0 },
        { "search_base_k",                 T_INT,   OFF(search_base_k),                 0, OPT, 0 },
        { "search_min_k",                  T_INT,   OFF(search_min_k),                  0, OPT, 0 },
        { "search_max_k",                  T_INT,   OFF(search_max_k),                  0, OPT, 0 },
        { "search_slope",                  T_FLOAT, OFF(search_slope),                  0, OPT, 0 },
        { "search_wealth_threshold",       T_FLOAT, OFF(search_wealth_threshold),       0, OPT, 0 },
        { "search_cost_per_candidate",     T_FLOAT, OFF(search_cost_per_candidate),     0, OPT, 0 },
        { "initial_resource_rich_frac",    T_FLOAT, OFF(initial_resource_rich_frac),    0, OPT, 0 },
        { "initial_resources_rich_min",    T_FLOAT, OFF(initial_resources_rich_min),    0, OPT, 0 },
        { "initial_resources_rich_max",    T_FLOAT, OFF(initial_resources_rich_max),    0, OPT, 0 },
        { "intervention_tick",             T_INT,   OFF(intervention_tick),             0, OPT, 0 },
        { "intervention_exploration_rate", T_FLOAT, OFF(intervention_exploration_rate), 0, OPT, 0 },
        { "intervention_generalization",   T_FLOAT, OFF(intervention_generalization),   0, OPT, 0 },
        { "intervention_newentrant_boost", T_FLOAT, OFF(intervention_newentrant_boost), 0, OPT, 0 },
    };
    const int nslots = (int)(sizeof slots / sizeof slots[0]);

    FILE *f = fopen(path, "r");
    if (!f) {
        fprintf(stderr, "config error: cannot open '%s'\n", path);
        exit(1);
    }

    char line[1024];
    int lineno = 0;
    while (fgets(line, sizeof line, f)) {
        lineno++;
        char *hash = strchr(line, '#');
        if (hash) *hash = '\0';
        trim(line);
        if (line[0] == '\0') continue;

        char *eq = strchr(line, '=');
        if (!eq) die(path, lineno, "missing '='");
        *eq = '\0';
        char *key = line;
        char *val = eq + 1;
        trim(key);
        trim(val);
        if (!*key) die(path, lineno, "empty key");
        if (!*val) die(path, lineno, "empty value");

        Slot *s = NULL;
        for (int i = 0; i < nslots; i++) {
            if (strcmp(slots[i].key, key) == 0) { s = &slots[i]; break; }
        }
        if (!s) {
            fprintf(stderr, "config error (%s:%d): unknown key '%s'\n", path, lineno, key);
            exit(1);
        }
        if (s->seen) {
            fprintf(stderr, "config error (%s:%d): duplicate key '%s'\n", path, lineno, key);
            exit(1);
        }

        char *dst = (char *)&cfg + s->off;
        char *end = NULL;
        switch (s->ty) {
            case T_U64: {
                unsigned long long v = strtoull(val, &end, 10);
                if (end == val || *end != '\0') die(path, lineno, "invalid integer");
                *(uint64_t *)dst = (uint64_t)v;
                break;
            }
            case T_INT: {
                long v = strtol(val, &end, 10);
                if (end == val || *end != '\0') die(path, lineno, "invalid integer");
                *(int *)dst = (int)v;
                break;
            }
            case T_FLOAT: {
                float v = strtof(val, &end);
                if (end == val || *end != '\0') die(path, lineno, "invalid float");
                *(float *)dst = v;
                break;
            }
            case T_STR: {
                size_t n = strlen(val);
                if (n + 1 > s->cap) die(path, lineno, "string value too long");
                memcpy(dst, val, n + 1);
                break;
            }
        }
        s->seen = 1;
    }
    fclose(f);

    for (int i = 0; i < nslots; i++) {
        if (slots[i].required && !slots[i].seen) {
            fprintf(stderr, "config error: missing required key '%s'\n", slots[i].key);
            exit(1);
        }
    }

    /* Default rich-tier resource bounds to the normal tier when unspecified. */
    if (cfg.initial_resource_rich_frac > 0.0f) {
        if (cfg.initial_resources_rich_min <= 0.0f)
            cfg.initial_resources_rich_min = cfg.initial_resources_min;
        if (cfg.initial_resources_rich_max <= 0.0f)
            cfg.initial_resources_rich_max = cfg.initial_resources_max;
    }

    if (cfg.initial_resources_min > cfg.initial_resources_max)
        die(path, 0, "initial_resources_min > initial_resources_max");
    if (cfg.exploration_rate < 0.0f || cfg.exploration_rate > 1.0f)
        die(path, 0, "exploration_rate must be in [0,1]");
    if (cfg.venture_chance < 0.0f || cfg.venture_chance > 1.0f)
        die(path, 0, "venture_chance must be in [0,1]");
    if (cfg.base_success_prob < 0.0f || cfg.base_success_prob > 1.0f)
        die(path, 0, "base_success_prob must be in [0,1]");
    if (cfg.spawn_interval <= 0) die(path, 0, "spawn_interval must be > 0");
    if (cfg.snapshot_interval <= 0) die(path, 0, "snapshot_interval must be > 0");
    if (cfg.max_ticks <= 0) die(path, 0, "max_ticks must be > 0");
    if (cfg.initial_population <= 0) die(path, 0, "initial_population must be > 0");

    return cfg;
}
