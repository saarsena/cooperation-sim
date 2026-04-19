# relationships

Agent-based model of pairwise trust dynamics under survival pressure. Text output only — no graphics, no space. C11 + Flecs, single executable, config-driven.

## Core dynamics

1. **Metabolism.** Each living agent loses `metabolism` resources per tick. At zero, they die.
2. **Ventures.** Each tick, living agents may initiate a joint venture with a partner. Both share the outcome: success returns resources, failure costs resources.
3. **Trust updates.** Venture outcomes update pairwise trust: success raises it, failure lowers it.
4. **Trust decay.** Pairwise trust drifts toward `trust_baseline` each tick if the relationship isn't reinforced.
5. **Partner selection.** Biased toward higher-trust partners via softmax on trust; `exploration_rate` controls the share of uniformly-random picks.
6. **Spawning.** New agents enter the population every `spawn_interval` ticks.

Each of those is one tight system in `src/modules/`. You can run the simulation with only those six mechanics active by using a scenario that leaves all extension knobs at their null values (see [scenarios/regression.conf](scenarios/regression.conf)).

## Extension mechanics

Every extension is off by default — omitting its config key, or setting it to the null value noted here, exactly reproduces the core dynamics.

- **Visible traits** (always on). Each agent carries `TRAIT_COUNT × TRAIT_LEVELS` = 3×4 = 64 discrete trait combinations, drawn uniformly at spawn. Traits only *affect* dynamics when another extension references them.
- **Hidden cooperative quality.** Each agent gets a `CoopQuality ∈ [0,1]` at spawn. Enabled by setting `coop_quality_success_weight > 0` or `coop_quality_payoff_scale > 0`. Optionally correlated with visible traits via `trait_quality_correlation` (0 = traits are pure markers, 1 = traits fully determine quality).
- **Trust generalization.** Each agent keeps a `TrustByTrait` table; venture outcomes nudge the prior for *all* trait values matching the partner's. Enabled by `trait_generalization_strength > 0`. Used as a fallback estimate during partner selection when no direct relationship exists.
- **Costly search with wealth-driven selectivity.** Enabled by `search_base_k > 0`. Effective search depth `k = clamp(base_k + slope · max(0, resources − wealth_threshold), min_k, max_k)`; each candidate evaluated deducts `search_cost_per_candidate` from resources. Wealth buys selectivity; poverty forces fewer looks.
- **Bimodal initial resources.** Enabled by `initial_resource_rich_frac > 0`. Fraction of new spawns start at `initial_resources_rich_[min|max]` rather than the base range.
- **Interventions.** At `intervention_tick`, override `exploration_rate`, force `trait_generalization_strength` to a new value, and/or multiply new-entrant spawn resources by `intervention_newentrant_boost`. Set `intervention_tick = -1` to disable.

## Build

```sh
cmake -B build-rel -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build-rel -j
```

A debug build (`cmake -B build -DCMAKE_BUILD_TYPE=Debug`) also works but runs ~5× slower.

## Run

```sh
./build-rel/relationships scenarios/default.conf
```

Outputs land in `cfg.output_dir`. The directory is created at startup; the program errors out if it already exists — rename or delete old runs before re-running. A scenario with no `output_dir` set will fail config validation, not silently clobber another run.

## Output files

All paths are relative to `cfg.output_dir`.

- `metrics.csv` — one row per tick. Columns: `tick, population, mean_trust, strong_edges, resources_gini, total_resources, within_group_trust, across_group_trust, trust_gap, gini_group_mean, mean_search_effort_q1, mean_search_effort_q4`. `strong_edges` counts relationships with `TrustStrength ≥ 0.5`. `within_group_trust` and `across_group_trust` split pairwise trust by whether the two endpoints share every trait. `trust_gap = within − across` is the headline discrimination signal. `gini_group_mean` is a Gini over the per-trait-group *mean* resources (stratification independent of within-group spread). `mean_search_effort_q*` records the average `k` candidates evaluated by agents in the top/bottom resource quartiles.
- `events.log` — tab-separated event stream (births, deaths, relationship creations/destructions, venture outcomes). Set `log_events = 0` in a scenario to skip this entirely; at large pop/tick counts it's the biggest output by far.
- `snapshots/tick_NNNNNN.tsv` — full state dumps every `snapshot_interval` ticks. Agent section includes traits, coop_quality, and group_key; relationship section includes TrustStrength, age, and last_reinforced tick.
- `summary.txt` — final tallies and full config echo (core and extension knobs) written when the run ends.

## Scenarios

Each `scenarios/*.conf` is a labeled experiment. Below is what's there now and what each one is set up to show.

| File | What it tests |
| --- | --- |
| [default.conf](scenarios/default.conf) | Baseline: core dynamics only, event log on |
| [mini.conf](scenarios/mini.conf) | 1000-tick smoke test for determinism checks |
| [profile.conf](scenarios/profile.conf) | 4000 ticks, sized for `perf record` runs |
| [regression.conf](scenarios/regression.conf) | **Experiment 1:** all extensions at null values; sanity check that dynamics still match default |
| [markers_off.conf](scenarios/markers_off.conf) | **Experiment 2 control:** trait_generalization = 0 |
| [markers_only.conf](scenarios/markers_only.conf) | **Experiment 2:** trait_generalization = 0.6 with zero correlation between traits and quality — tests whether discrimination emerges from pure markers |
| [inequality.conf](scenarios/inequality.conf) | **Experiment 3:** bimodal initial resources + costly search — rich can afford selectivity, poor can't |
| [new_entrant.conf](scenarios/new_entrant.conf) | **Experiment 4:** rapid spawning under active generalization — newcomers inherit their trait group's accumulated stigma or credit |
| [intervention_explore.conf](scenarios/intervention_explore.conf) | **Experiment 5a:** force `exploration_rate = 0.5` at tick 15000 |
| [intervention_no_gen.conf](scenarios/intervention_no_gen.conf) | **Experiment 5b:** force `trait_generalization_strength = 0` at tick 15000 |
| [intervention_subsidy.conf](scenarios/intervention_subsidy.conf) | **Experiment 5c:** 2× starting resources for new entrants after tick 15000 |
| [high_exploration.conf](scenarios/high_exploration.conf) | Regime sweep: `exploration_rate = 0.9` (near-random partners) |
| [low_exploration.conf](scenarios/low_exploration.conf) | Regime sweep: `exploration_rate = 0.01` (strong trust bias) |
| [easy_success.conf](scenarios/easy_success.conf) | Regime sweep: `base_success_prob = 0.5` (post-scarcity regime) |

## Analysis

- [`analysis/plot_metrics.py`](analysis/plot_metrics.py) — stack-plot any run's `metrics.csv` columns over time. Takes one or more run directories; if you pass several, they overlay on the same axes.

  ```sh
  python3 analysis/plot_metrics.py output/run_001 \
      -o analysis/plots/baseline.png
  python3 analysis/plot_metrics.py output/markers_off output/markers_only \
      -o analysis/plots/discrimination.png
  ```

- [`analysis/run_seeds.sh`](analysis/run_seeds.sh) — run a scenario across N seeds in parallel, writing to `output/<name>__seedK`.

  ```sh
  analysis/run_seeds.sh scenarios/markers_only.conf 16
  ```

- [`analysis/compare_seeds.py`](analysis/compare_seeds.py) — aggregate across seeds and plot mean ± 1σ for a chosen metric.

  ```sh
  python3 analysis/compare_seeds.py \
      --scenarios markers_off markers_only \
      --metric trust_gap \
      --out analysis/plots/discrimination.png
  ```

- [`analysis/flamegraphs/`](analysis/flamegraphs/) — SVG flame graphs from before/after the `find_relationship` hash-map fix. Open in a browser or VSCode; the search box highlights function names across the whole graph.

## Performance

The original `find_relationship` did an O(relationships) linear scan over every Flecs relationship entity per partner evaluation. On the default 20k-tick run at pop ~120 that was about 68% of wall time (per [`analysis/flamegraphs/flame-before.svg`](analysis/flamegraphs/flame-before.svg)). It was replaced with a `stb_ds` hash map keyed on the normalized pair, maintained in [`src/modules/relationships.c`](src/modules/relationships.c) in lockstep with Flecs storage — **roughly 29× speedup end-to-end** on the default scenario (190s → 6.6s in release).

Determinism is preserved across runs with the same `seed`; two runs of `scenarios/mini.conf` produce byte-identical `metrics.csv` and `events.log`.
