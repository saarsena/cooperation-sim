# Relationships ABM — project summary

## Goal

Build the smallest possible agent-based model that lets us probe how individual-level trust update rules produce (or fail to produce) group-level discrimination. The simulation is the experiment — we're not trying to ship a product, we're running parameter sweeps and reading what comes out.

## Stack

- **C11 + Flecs ECS** for the simulation core. Single binary, no graphics, text/CSV output only.
- **PCG32 deterministic RNG**, seeded from config. Two runs at the same seed produce byte-identical metrics.csv.
- **stb_ds** hash maps for relationship lookup.
- **16-seed Monte-Carlo sweeps** via `analysis/run_seeds.sh <scenario.conf> 16`. Each seed gets its own `output/<scenario>__seed<N>/` directory.
- **Python (pandas/numpy/matplotlib)** for analysis. Single script (`analysis/build_report.py`) generates every plot in the findings doc. Tried Jupyter, abandoned — too many indirection layers for what's basically "load CSVs and plot lines."

## The model

Six core rules that form the minimum closed loop:

1. **Metabolism** — every agent loses `metabolism` resources per tick; ≤0 = death.
2. **Ventures** — agents probabilistically initiate joint actions; both succeed or fail; success returns resources, failure costs them.
3. **Trust updates from outcomes** — success raises pairwise trust, failure lowers it.
4. **Trust decay** — trust drifts toward `trust_baseline` each tick.
5. **Partner selection** — biased by trust, with `exploration_rate` chance of random.
6. **Spawning** — every `spawn_interval` ticks, one fresh agent.

Extensions added on top of v1 to enable specific experiments:

- **Trait labels + generalization priors** (markers experiments)
- **Loss-aversion** (`trust_loss_on_failure > trust_gain_on_success`)
- **Bimodal initial wealth + wealth-scaled partner search** (inequality experiment)

## What we've found so far

(Full version in `analysis/FINDINGS.md`.)

1. **Pure trait-generalization does NOT produce stigma.** With identical hidden behavior across groups, generalization homogenizes priors toward the population mean. Within-group and across-group trust track each other.
2. **Loss-aversion DOES produce stigma — with a twist.** Asymmetric trust updates (loss > gain) make early random fluctuations pin into stable distrust. But the *target* of distrust is random per seed: |gap| jumps ~9× over control, while signed average gap stays near zero.
3. **Wealth inequality alone doesn't lock onto traits.** Gini climbs to 0.36 and stays, but between-group Gini stays near zero. Money sorts itself, but not onto identity labels.
4. **Fast newcomer turnover doesn't produce inherited reputation either** under these settings. Same homogenization as static populations.
5. **The system has a viability cliff.** Below `base_success_prob ≈ 0.3` with stock parameters, populations go extinct. This constrains which loss-aversion settings we can even test — we had to bump base_success_prob to 0.4 to keep loss-averse worlds alive.
6. **Trust-biased partner selection is load-bearing.** When `exploration_rate=0.9` (random partners), populations crash to ~8 agents and inequality jumps. The "trust network" is doing real survival work.

## Open questions / where to go next

- **Disentangle loss-aversion's stigma effect from population shrinkage.** Currently `markers_lossaverse` runs at smaller pop than control — some of |gap| could be small-N noise. Need a control where we shrink pop without loss-aversion.
- **Trait-correlated hidden quality.** All experiments so far have identical-by-design groups. What if group A is genuinely 5% better at ventures? Does generalization track the real signal, overshoot, or amplify?
- **Asymmetric trust** (a→b ≠ b→a). Currently symmetric, which is unrealistic.
- **Recovery / interventions.** Once a loss-averse seed has pinned distrust to group A, can policy interventions pull it out? Not yet tested.
- **Why does `easy_success` not show stigma either?** Larger populations + more headroom should make the simulation more sensitive to subtle effects, not less. Worth a closer look.

## Repo layout

```
relationships/
├── src/                      # C source: core/, modules/, output/
├── scenarios/                # *.conf files, one per experiment
├── analysis/
│   ├── build_report.py       # generates all plots + tables
│   ├── compare_seeds.py      # ad-hoc per-metric mean±std plots
│   ├── plot_metrics.py       # single-run plots
│   ├── run_seeds.sh          # batch-run a scenario across N seeds
│   ├── FINDINGS.md           # narrated results doc
│   └── plots/                # generated PNGs
└── output/                   # gitignored; <scenario>__seed<N>/ per run
```

## Status

- v1 simulation: complete, deterministic, parameterized.
- Six 16-seed scenarios run: markers_off, markers_only, markers_lossaverse, inequality, new_entrant, low_exploration, high_exploration, easy_success.
- Findings doc written.
- No automated tests — the simulation *is* the test, validated by determinism + sanity checks on dynamics.
