"""Phase 2 asymptote analysis. Loads a long-horizon easy_success run (or runs)
and asks the binary question: does per-capita strong ties stabilize at some
floor, or keep collapsing toward zero?

Three outcomes get distinct visual signatures:
  1. Stabilizes at a clear floor  -> per-capita trace levels off
  2. Keeps collapsing toward zero -> trace continues toward zero
  3. Something weird              -> oscillation, non-convergence

Run from the repo root:  python3 analysis/capacity_asymptote.py [PREFIX]
Default PREFIX = easy_success_100k.
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "analysis" / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load(prefix: str) -> pd.DataFrame:
    frames = []
    for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}*"))):
        p = Path(d) / "metrics.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        # try to extract a seed from the dir name; fall back to 0
        try:
            df["seed"] = int(d.split("seed")[-1])
        except ValueError:
            df["seed"] = 0
        df["run_dir"] = d
        frames.append(df)
    if not frames:
        raise SystemExit(f"no runs found for prefix {prefix}")
    return pd.concat(frames, ignore_index=True)


def smooth(arr, window):
    if window <= 1:
        return np.asarray(arr)
    return pd.Series(arr).rolling(window, center=True, min_periods=1).mean().values


def plot_asymptote(df: pd.DataFrame, prefix: str):
    """Per-capita strong ties = strong_edges / population, vs tick.
    Each seed plotted faintly; cross-seed mean overlaid bold."""
    seeds = sorted(df["seed"].unique())
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

    # individual seeds
    all_per = []
    max_tick = 0
    for s in seeds:
        sub = df[df["seed"] == s].sort_values("tick").reset_index(drop=True)
        pop = sub["population"].values.astype(float)
        strong = sub["strong_edges"].values.astype(float)
        per = np.where(pop > 0, strong / pop, np.nan)
        all_per.append((sub["tick"].values, per))
        max_tick = max(max_tick, int(sub["tick"].max()))
        axes[0].plot(sub["tick"], per, linewidth=0.6, alpha=0.35)
        axes[1].plot(sub["tick"], strong, linewidth=0.6, alpha=0.35)

    # cross-seed mean
    common_ticks = np.arange(0, max_tick + 1)
    per_grid = np.full((len(seeds), len(common_ticks)), np.nan)
    strong_grid = np.full((len(seeds), len(common_ticks)), np.nan)
    pop_grid = np.full((len(seeds), len(common_ticks)), np.nan)
    for i, s in enumerate(seeds):
        sub = df[df["seed"] == s].sort_values("tick").reset_index(drop=True)
        L = len(sub)
        per_grid[i, :L] = np.where(sub["population"] > 0,
                                   sub["strong_edges"] / sub["population"],
                                   np.nan)
        strong_grid[i, :L] = sub["strong_edges"]
        pop_grid[i, :L] = sub["population"]

    per_mean = np.nanmean(per_grid, axis=0)
    strong_mean = np.nanmean(strong_grid, axis=0)
    pop_mean = np.nanmean(pop_grid, axis=0)

    win = max(200, max_tick // 200)  # adapt smoothing to run length
    axes[0].plot(common_ticks, smooth(per_mean, win),
                 color="#2ca02c", linewidth=2.0,
                 label=f"cross-seed mean (n={len(seeds)}, smoothed w={win})")
    axes[1].plot(common_ticks, smooth(strong_mean, win),
                 color="#2ca02c", linewidth=2.0,
                 label=f"cross-seed mean (n={len(seeds)})")

    axes[0].set_ylabel("strong ties per agent")
    axes[0].set_title(f"{prefix} — per-capita strong ties")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="upper right")
    axes[1].set_ylabel("strong edges (absolute)")
    axes[1].set_xlabel("tick")
    axes[1].set_title(f"{prefix} — absolute strong-edge stock")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="upper right")

    fig.tight_layout()
    out = OUT_DIR / f"08_asymptote_{prefix}.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")

    # decision-table snapshot (cross-seed mean)
    snapshots = [1000, 5000, 10000, 20000, 30000, 50000, 70000, 100000]
    print(f"\nasymptote snapshot (cross-seed mean, prefix={prefix}):")
    print(f"{'tick':>7} {'pop':>6} {'strong':>7} {'per_capita':>11}")
    for t in snapshots:
        if t > max_tick:
            continue
        i = t
        pop_v = pop_mean[i] if not np.isnan(pop_mean[i]) else float("nan")
        s_v = strong_mean[i] if not np.isnan(strong_mean[i]) else float("nan")
        per_v = per_mean[i] if not np.isnan(per_mean[i]) else float("nan")
        print(f"{t:>7} {pop_v:>6.0f} {s_v:>7.0f} {per_v:>11.4f}")

    # late-window stability check: does per-capita stabilize over the last
    # 20% of the run? Compare mean(last 5%) vs mean(80-95% window).
    if max_tick >= 20000:
        late_a = per_mean[int(max_tick * 0.80):int(max_tick * 0.95)]
        late_b = per_mean[int(max_tick * 0.95):]
        slope = (np.nanmean(late_b) - np.nanmean(late_a)) / max(1, len(late_b))
        print(f"\nlate-window stability:")
        print(f"  mean per-capita @ 80-95%: {np.nanmean(late_a):.4f}")
        print(f"  mean per-capita @ 95-100%: {np.nanmean(late_b):.4f}")
        print(f"  per-tick drift (last 5% vs prior window): {slope:.2e}")


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "easy_success_100k"
    df = load(prefix)
    print(f"loaded {prefix}: {df['seed'].nunique()} seeds, "
          f"max tick {df['tick'].max()}")
    if "edges_crossed_up" not in df.columns:
        print("note: no flow columns (older run)")
    plot_asymptote(df, prefix)


if __name__ == "__main__":
    main()
