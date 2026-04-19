#!/usr/bin/env python3
"""Plot per-tick metrics from one or more relationships runs.

Usage:
    python analysis/plot_metrics.py output/run_001
    python analysis/plot_metrics.py output/run_001 output/high_exploration -o analysis/plots/sweep.png
"""
import argparse
import csv
from pathlib import Path
import matplotlib.pyplot as plt

METRICS = [
    ("population",         "population"),
    ("mean_trust",         "mean trust"),
    ("strong_edges",       "strong edges (trust >= 0.5)"),
    ("resources_gini",     "resources Gini"),
    ("total_resources",    "total resources"),
    ("within_group_trust", "within-group trust"),
    ("across_group_trust", "across-group trust"),
    ("trust_gap",          "within − across trust"),
    ("gini_group_mean",    "Gini of per-group mean resources"),
]


def load(path):
    csv_path = Path(path)
    if csv_path.is_dir():
        csv_path = csv_path / "metrics.csv"
    ticks = []
    cols = {name: [] for name, _ in METRICS}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            ticks.append(int(row["tick"]))
            for name, _ in METRICS:
                cols[name].append(float(row[name]))
    return csv_path.parent.name, ticks, cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="run directory or metrics.csv path")
    ap.add_argument("-o", "--output", default="analysis/plots/comparison.png")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    loaded = [load(r) for r in args.runs]

    fig, axes = plt.subplots(
        len(METRICS), 1, figsize=(12, 2.2 * len(METRICS)), sharex=True
    )

    for ax, (name, ylabel) in zip(axes, METRICS):
        for label, ticks, cols in loaded:
            ax.plot(ticks, cols[name], label=label, linewidth=1)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)

    if len(loaded) > 1:
        axes[0].legend(loc="upper left", fontsize=9)
    axes[-1].set_xlabel("tick")
    fig.suptitle(args.title or "metrics over time", y=0.995)
    fig.tight_layout()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
