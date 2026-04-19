#!/usr/bin/env python3
"""Aggregate per-tick metrics across seeds and plot mean +/- 1 std per scenario.

Usage:
    analysis/compare_seeds.py --scenarios markers_off markers_only \
        --metric trust_gap --out analysis/plots/discrimination.png

Each scenario name is a PREFIX — all directories matching
``output/<prefix>__seed*`` are loaded and combined.
"""
from __future__ import annotations

import argparse
import csv
import glob
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


def load_scenario(prefix: str):
    dirs = sorted(glob.glob(f"output/{prefix}__seed*"))
    if not dirs:
        raise SystemExit(f"no runs found for prefix '{prefix}' under output/")
    per_tick = {}
    for d in dirs:
        with open(Path(d) / "metrics.csv") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t = int(row["tick"])
                per_tick.setdefault(t, []).append(
                    {k: float(v) for k, v in row.items() if k != "tick"}
                )
    return per_tick, len(dirs)


def reduce_metric(per_tick, metric):
    ticks = sorted(per_tick.keys())
    means = []
    stds = []
    for t in ticks:
        vals = np.array([row[metric] for row in per_tick[t]])
        means.append(vals.mean())
        stds.append(vals.std())
    return np.array(ticks), np.array(means), np.array(stds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", nargs="+", required=True,
                    help="scenario output prefixes (from run_seeds.sh)")
    ap.add_argument("--metric", default="trust_gap",
                    help="metrics.csv column to aggregate (default trust_gap)")
    ap.add_argument("--out", default="analysis/plots/compare.png")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    fig, ax = plt.subplots(figsize=(12, 4.5))
    for prefix in args.scenarios:
        per_tick, n = load_scenario(prefix)
        ticks, m, s = reduce_metric(per_tick, args.metric)
        label = f"{prefix} (n={n})"
        ax.plot(ticks, m, label=label, linewidth=1.2)
        ax.fill_between(ticks, m - s, m + s, alpha=0.15)

    ax.axhline(0, color="k", linewidth=0.5, alpha=0.4)
    ax.set_xlabel("tick")
    ax.set_ylabel(args.metric)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.suptitle(args.title or f"{args.metric} across seeds (mean ± 1 std)", y=0.98)
    fig.tight_layout()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
