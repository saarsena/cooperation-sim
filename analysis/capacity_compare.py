"""Compare per-capita strong ties between regimes at long horizon.
Loads any number of (prefix, label) pairs and produces a single overlay plot.
For asymmetric run lengths (some scenarios at 30k, some at 100k), each trace
plots over its own range.

Run from repo root:  python3 analysis/capacity_compare.py
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "analysis" / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def smooth(arr, window):
    return pd.Series(arr).rolling(window, center=True, min_periods=1).mean().values


def load_runs(prefix: str):
    runs = []
    for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}*"))):
        p = Path(d) / "metrics.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        runs.append(df)
    return runs


def cross_seed_per_capita(runs):
    if not runs:
        return None, None, None
    max_tick = max(int(r["tick"].max()) for r in runs)
    per = np.full((len(runs), max_tick + 1), np.nan)
    for i, df in enumerate(runs):
        L = len(df)
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.where(df["population"] > 0,
                         df["strong_edges"] / df["population"], np.nan)
        per[i, :L] = v
    mean = np.nanmean(per, axis=0)
    sd = np.nanstd(per, axis=0)
    return np.arange(max_tick + 1), mean, sd


def main():
    targets = [
        ("markers_off_100k",       "markers_off (16 seeds × 100k)", "#1f77b4"),
        ("easy_success_100k_pilot","easy_success pilot (1 seed × 100k)", "#d62728"),
        ("easy_success__seed",     "easy_success (16 seeds × 20k, prior run)", "#ff7f0e"),
        ("markers_off__seed",      "markers_off (16 seeds × 30k, baseline)", "#9467bd"),
    ]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    for prefix, label, color in targets:
        runs = load_runs(prefix)
        if not runs:
            print(f"  skip {prefix}: no runs")
            continue
        ticks, mean, sd = cross_seed_per_capita(runs)
        if ticks is None:
            continue
        win = max(200, ticks[-1] // 200)
        ax1.plot(ticks, smooth(mean, win), color=color, linewidth=1.6,
                 label=f"{label}, n={len(runs)}")
        ax2.semilogy(ticks, smooth(np.maximum(mean, 1e-4), win),
                     color=color, linewidth=1.6,
                     label=f"{label}, n={len(runs)}")
        print(f"{prefix}: {len(runs)} runs, max_tick {ticks[-1]}, "
              f"final per-capita = {mean[-1]:.4f}")

    for ax in (ax1, ax2):
        ax.set_xlabel("tick")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right")
    ax1.set_ylabel("strong ties per agent (linear)")
    ax2.set_ylabel("strong ties per agent (log, clipped at 1e-4)")
    ax1.set_title("Per-capita strong ties: capacity-law vs collapse regimes")
    fig.tight_layout()
    out = OUT_DIR / "09_asymptote_compare.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
