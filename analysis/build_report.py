#!/usr/bin/env python3
"""Generate every plot used in analysis/FINDINGS.md from the seed sweeps.

Run from repo root:  python3 analysis/build_report.py
Outputs land in     analysis/plots/

This is purposefully a script, not a notebook — re-run it whenever you
add new seed sweeps.
"""
from __future__ import annotations

import csv
import glob
import os
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "analysis" / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load(prefix: str):
    """Return list of (seed, dict-of-arrays) for every output/<prefix>__seedN run."""
    runs = []
    for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}__seed*"))):
        seed = int(d.split("seed")[-1])
        cols: dict[str, list[float]] = {}
        with open(Path(d) / "metrics.csv") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for k, v in row.items():
                    cols.setdefault(k, []).append(float(v))
        runs.append((seed, {k: np.array(v) for k, v in cols.items()}))
    return runs


def mean_std(runs, metric):
    """Pad all seeds to the same length (extinct seeds drop out at their last tick)."""
    arrays = [r[metric] for _, r in runs]
    max_len = max(len(a) for a in arrays)
    padded = np.full((len(arrays), max_len), np.nan)
    for i, a in enumerate(arrays):
        padded[i, :len(a)] = a
    ticks = runs[0][1]["tick"][:max_len] if len(runs[0][1]["tick"]) == max_len \
            else np.arange(max_len)
    mean = np.nanmean(padded, axis=0)
    std  = np.nanstd(padded, axis=0)
    return ticks, mean, std


def plot_compare(scenarios, metric, title, fname, ylim=None):
    fig, ax = plt.subplots(figsize=(11, 4.2))
    for s in scenarios:
        runs = load(s)
        if not runs:
            print(f"  skip {s}: no runs")
            continue
        ticks, m, sd = mean_std(runs, metric)
        ax.plot(ticks, m, label=f"{s} (n={len(runs)})", linewidth=1.3)
        ax.fill_between(ticks, m - sd, m + sd, alpha=0.15)
    ax.axhline(0, color="k", linewidth=0.5, alpha=0.4)
    ax.set_xlabel("tick"); ax.set_ylabel(metric)
    ax.grid(True, alpha=0.3); ax.legend()
    ax.set_title(title)
    if ylim: ax.set_ylim(ylim)
    fig.tight_layout()
    out = OUT_DIR / fname
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


def plot_per_seed(scenarios, metric, title, fname):
    fig, axes = plt.subplots(1, len(scenarios), figsize=(5 * len(scenarios), 4),
                             sharey=True)
    if len(scenarios) == 1:
        axes = [axes]
    for ax, s in zip(axes, scenarios):
        for _, r in load(s):
            ax.plot(r["tick"], r[metric], linewidth=0.6, alpha=0.7)
        ax.axhline(0, color="k", linewidth=0.5, alpha=0.4)
        ax.set_title(s); ax.set_xlabel("tick")
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel(metric)
    fig.suptitle(title, y=1.02)
    fig.tight_layout()
    out = OUT_DIR / fname
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


def tail_summary(scenarios, tail_from=25000):
    """Print a markdown table of late-stage means per scenario."""
    rows = []
    for s in scenarios:
        runs = load(s)
        if not runs: continue
        per_seed = {}
        for seed, r in runs:
            mask = r["tick"] >= tail_from
            if not mask.any(): continue
            for k in ("population", "mean_trust", "within_group_trust",
                      "across_group_trust", "trust_gap", "resources_gini"):
                per_seed.setdefault(k, []).append(r[k][mask].mean())
            per_seed.setdefault("|gap|", []).append(np.abs(r["trust_gap"][mask].mean()))
            per_seed.setdefault("survived", []).append(1 if r["tick"][-1] >= tail_from else 0)
        n_survived = int(np.sum(per_seed.get("survived", [])))
        line = {"scenario": s, "n_survived": n_survived}
        for k in ("population", "mean_trust", "within_group_trust",
                  "across_group_trust", "trust_gap", "|gap|", "resources_gini"):
            vals = np.array(per_seed.get(k, []))
            line[k] = f"{vals.mean():+.3f}" if len(vals) else "—"
        rows.append(line)
    return rows


def print_table(rows, columns, header_label="scenario"):
    if not rows: return
    head = "| " + " | ".join([header_label] + columns) + " |"
    sep  = "| " + " | ".join(["---"] * (len(columns) + 1)) + " |"
    print(head); print(sep)
    for r in rows:
        cells = [r["scenario"]] + [str(r.get(c, "—")) for c in columns]
        print("| " + " | ".join(cells) + " |")


def main():
    print("=== markers (Experiment 2): does pure-marker stigma emerge? ===")
    markers = ["markers_off", "markers_only", "markers_lossaverse"]
    plot_compare(markers, "within_group_trust",
                 "Within-group trust over time",
                 "01_markers_within.png")
    plot_compare(markers, "across_group_trust",
                 "Across-group trust over time",
                 "01_markers_across.png")
    plot_compare(markers, "trust_gap",
                 "Trust gap (within − across) over time",
                 "01_markers_gap.png")
    plot_per_seed(markers, "trust_gap",
                  "Trust gap per seed (16 lines per panel)",
                  "01_markers_per_seed.png")
    print()
    print_table(tail_summary(markers),
                ["n_survived", "population", "mean_trust", "within_group_trust",
                 "across_group_trust", "trust_gap", "|gap|"])
    print()

    print("=== inequality (Experiment 3): wealth-driven selectivity ===")
    plot_compare(["inequality"], "resources_gini",
                 "Resources Gini coefficient over time",
                 "02_inequality_gini.png")
    plot_compare(["inequality"], "gini_group_mean",
                 "Between-group Gini (per-trait stratification)",
                 "02_inequality_group_gini.png")
    plot_compare(["inequality"], "mean_search_effort_q1",
                 "Search effort: bottom resource quartile",
                 "02_inequality_search_q1.png")
    plot_compare(["inequality"], "mean_search_effort_q4",
                 "Search effort: top resource quartile",
                 "02_inequality_search_q4.png")
    plot_compare(["inequality"], "trust_gap",
                 "Trust gap (does inequality lock into traits?)",
                 "02_inequality_gap.png")
    print()
    print_table(tail_summary(["inequality"]),
                ["n_survived", "population", "mean_trust", "trust_gap",
                 "|gap|", "resources_gini"])
    print()

    print("=== new_entrant (Experiment 4): inherited reputation ===")
    plot_compare(["new_entrant"], "within_group_trust",
                 "Within-group trust under fast spawning + generalization",
                 "03_newentrant_within.png")
    plot_compare(["new_entrant"], "trust_gap",
                 "Trust gap with rapid newcomer inflow",
                 "03_newentrant_gap.png")
    plot_per_seed(["new_entrant"], "trust_gap",
                  "Per-seed trust_gap traces",
                  "03_newentrant_per_seed.png")
    print()
    print_table(tail_summary(["new_entrant"], tail_from=15000),
                ["n_survived", "population", "mean_trust", "trust_gap",
                 "|gap|", "resources_gini"])
    print()

    print("=== regime sweeps: exploration_rate and base_success_prob ===")
    regimes = ["low_exploration", "high_exploration", "easy_success"]
    plot_compare(regimes + ["markers_off"], "population",
                 "Population trajectory across regimes",
                 "04_regime_population.png")
    plot_compare(regimes + ["markers_off"], "mean_trust",
                 "Mean trust across regimes",
                 "04_regime_meantrust.png")
    plot_compare(regimes + ["markers_off"], "strong_edges",
                 "Strong relationships (TrustStrength ≥ 0.5) across regimes",
                 "04_regime_strongedges.png")
    plot_compare(regimes + ["markers_off"], "resources_gini",
                 "Resource inequality across regimes",
                 "04_regime_gini.png")
    print()
    print_table(tail_summary(regimes + ["markers_off"], tail_from=15000),
                ["n_survived", "population", "mean_trust", "trust_gap",
                 "resources_gini"])
    print()

    print("=== capacity: per-edge refresh budget vs trust decay ===")
    plot_capacity_percapita()
    plot_capacity_total_vs_strong()
    plot_capacity_refresh()
    print()

    print("done. plots in", OUT_DIR.relative_to(REPO))


def _per_capita_strong(runs):
    """Return (ticks, mean_per_capita, std_per_capita) across seeds."""
    series = []
    max_len = 0
    for _, r in runs:
        if "strong_edges" not in r or "population" not in r:
            continue
        pop = r["population"]
        # avoid /0; treat extinct ticks as nan so they don't drag the mean
        pc = np.where(pop > 0, r["strong_edges"] / np.maximum(pop, 1), np.nan)
        series.append(pc)
        max_len = max(max_len, len(pc))
    padded = np.full((len(series), max_len), np.nan)
    for i, a in enumerate(series):
        padded[i, :len(a)] = a
    ticks = runs[0][1]["tick"][:max_len] if len(runs[0][1]["tick"]) >= max_len \
            else np.arange(max_len)
    return ticks, np.nanmean(padded, axis=0), np.nanstd(padded, axis=0)


def plot_capacity_percapita():
    fig, ax = plt.subplots(figsize=(11, 4.2))
    for s in ["easy_success", "markers_off"]:
        runs = load(s)
        if not runs:
            print(f"  skip {s}: no runs"); continue
        ticks, m, sd = _per_capita_strong(runs)
        ax.plot(ticks, m, label=f"{s} (n={len(runs)})", linewidth=1.4)
        ax.fill_between(ticks, m - sd, m + sd, alpha=0.15)
    ax.set_xlabel("tick"); ax.set_ylabel("strong_edges / population")
    ax.set_title("Per-capita strong ties — easy_success collapses while markers_off holds")
    ax.grid(True, alpha=0.3); ax.legend()
    fig.tight_layout()
    out = OUT_DIR / "05_capacity_percapita.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


def plot_capacity_total_vs_strong():
    runs = load("easy_success")
    if not runs:
        print("  skip easy_success total_vs_strong: no runs"); return
    if "total_edges" not in runs[0][1]:
        print("  skip easy_success total_vs_strong: no total_edges column "
              "(re-run scenario after exposing total_edges in CSV)")
        return
    fig, ax = plt.subplots(figsize=(11, 4.2))
    for metric, color, label in (("total_edges",  "#1f77b4", "total_edges"),
                                 ("strong_edges", "#d62728", "strong_edges (≥0.5)")):
        ticks, m, sd = mean_std(runs, metric)
        ax.plot(ticks, m, color=color, linewidth=1.4, label=label)
        ax.fill_between(ticks, m - sd, m + sd, color=color, alpha=0.15)
    ax.set_xlabel("tick"); ax.set_ylabel("edge count")
    ax.set_title("easy_success — total edges keep growing while strong edges collapse")
    ax.grid(True, alpha=0.3); ax.legend()
    fig.tight_layout()
    out = OUT_DIR / "05_capacity_total_vs_strong.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


def plot_capacity_refresh():
    """Refreshes per edge per tick (= venture_chance * pop / total_edges).

    Two reference lines:
      - trust_decay (= 0.002): the asymptotic floor; rate must stay above it
        for any non-trivial trust signal to survive at all.
      - analytical maintenance threshold (~0.018): the rate at which a single
        edge sitting right at the strong threshold (trust=0.5) breaks even
        between expected venture-gain and decay-drag. Below this, individual
        strong edges become hard to sustain — though stock can still grow if
        new-edge formation outpaces strong→weak decay.
    """
    venture_chance = 0.4
    trust_decay    = 0.002
    # back-of-envelope: at trust=0.5 with base_success_prob=0.5 and
    # trust_success_weight=0.5, P(success) ≈ 0.625, expected gain per refresh
    # ≈ 0.15*0.625 - 0.10*0.375 ≈ 0.057. Decay drag at trust=0.5 ≈ 0.5*0.002
    # = 0.001. Balance: r * 0.057 = 0.001 → r ≈ 0.018.
    maint_threshold = 0.018

    runs = load("easy_success")
    if not runs:
        print("  skip easy_success refresh: no runs"); return
    if "total_edges" not in runs[0][1]:
        print("  skip easy_success refresh: no total_edges column "
              "(re-run scenario after exposing total_edges in CSV)")
        return

    series = []
    max_len = 0
    for _, r in runs:
        with np.errstate(divide="ignore", invalid="ignore"):
            rate = np.where(r["total_edges"] > 0,
                            venture_chance * r["population"] / r["total_edges"],
                            np.nan)
        series.append(rate)
        max_len = max(max_len, len(rate))
    padded = np.full((len(series), max_len), np.nan)
    for i, a in enumerate(series):
        padded[i, :len(a)] = a
    ticks = runs[0][1]["tick"][:max_len] if len(runs[0][1]["tick"]) >= max_len \
            else np.arange(max_len)
    m = np.nanmean(padded, axis=0)
    sd = np.nanstd(padded, axis=0)

    # find tick where mean strong_edges peaks (across seeds)
    strong_padded = np.full((len(runs), max_len), np.nan)
    for i, (_, r) in enumerate(runs):
        L = len(r["strong_edges"])
        strong_padded[i, :L] = r["strong_edges"]
    strong_mean = np.nanmean(strong_padded, axis=0)
    peak_tick = int(ticks[np.nanargmax(strong_mean)])

    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(ticks, m, color="#2ca02c", linewidth=1.5,
            label="refreshes per edge per tick")
    ax.fill_between(ticks, m - sd, m + sd, color="#2ca02c", alpha=0.15)
    ax.axhline(maint_threshold, color="#1f77b4", linewidth=1.0, linestyle=":",
               label=f"single-edge maintenance threshold ≈ {maint_threshold}")
    ax.axhline(trust_decay, color="#d62728", linewidth=1.0, linestyle="--",
               label=f"trust_decay floor = {trust_decay}")
    ax.axvline(peak_tick, color="k", linewidth=0.8, alpha=0.5)
    ax.annotate(f"strong-edge peak\n≈ tick {peak_tick}",
                xy=(peak_tick, m[np.argmin(np.abs(ticks - peak_tick))]),
                xytext=(peak_tick + 1000, 0.02),
                arrowprops=dict(arrowstyle="->", color="k", alpha=0.5),
                fontsize=9)
    ax.set_yscale("log")
    ax.set_xlabel("tick"); ax.set_ylabel("rate per edge per tick (log scale)")
    ax.set_title("easy_success — refresh budget per edge declines as 1/density")
    ax.grid(True, which="both", alpha=0.3); ax.legend(loc="lower left")
    fig.tight_layout()
    out = OUT_DIR / "05_capacity_refresh.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
