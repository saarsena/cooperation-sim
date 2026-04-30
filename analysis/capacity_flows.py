"""Phase 1 capacity-flow analysis. Loads the 16-seed easy_success run with the
new flow-instrumentation columns, plots strong-edge stock alongside the
crossing-flow rates, and computes uniform vs strong-edge refresh rates.

Outputs three plots and prints a small numerical table for CAPACITY.md.

Run from the repo root:  python3 analysis/capacity_flows.py
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "analysis" / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load(prefix: str) -> pd.DataFrame:
    frames = []
    for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}__seed*"))):
        df = pd.read_csv(Path(d) / "metrics.csv")
        df["seed"] = int(d.split("seed")[-1])
        frames.append(df)
    if not frames:
        raise SystemExit(f"no runs found for prefix {prefix}")
    return pd.concat(frames, ignore_index=True)


def smooth(arr: np.ndarray, window: int) -> np.ndarray:
    """Centered rolling mean with edge handling (uses partial windows at the
    boundaries, so the trace doesn't dip toward zero at the start/end)."""
    if window <= 1:
        return arr
    return pd.Series(arr).rolling(window, center=True, min_periods=1).mean().values


def plot_flows(df: pd.DataFrame, prefix: str):
    """Panel A: strong-edge stock with up/down crossing flows overlaid.
    The flow-balance hypothesis predicts the strong-edge peak coincides with
    edges_crossed_up == edges_crossed_down (net flow into strong = 0)."""
    g = df.groupby("tick")
    ticks = np.array(g.groups.keys() if False else sorted(df["tick"].unique()))
    strong = g["strong_edges"].mean().values
    up     = g["edges_crossed_up"].mean().values
    down   = g["edges_crossed_down"].mean().values

    # Crossings are noisy at single-tick resolution. Use a 200-tick rolling
    # mean for visualization; raw counts are used for the crossover-tick
    # estimate below.
    win = 200
    up_s   = smooth(up,   win)
    down_s = smooth(down, win)
    net    = up_s - down_s

    peak_tick    = int(ticks[np.argmax(strong)])
    # Flow-balance crossover: first tick AFTER peak where up - down crosses
    # zero from positive to negative (smoothed).
    peak_idx = np.argmax(strong)
    cross_idx = peak_idx
    for i in range(peak_idx, len(net) - 1):
        if net[i] >= 0 and net[i + 1] < 0:
            cross_idx = i
            break
    cross_tick = int(ticks[cross_idx])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    ax1.plot(ticks, strong, color="#2ca02c", linewidth=1.5, label="strong_edges (mean over 16 seeds)")
    ax1.axvline(peak_tick, color="#2ca02c", linestyle="--", alpha=0.5,
                label=f"stock peak ≈ tick {peak_tick}")
    ax1.axvline(cross_tick, color="#1f77b4", linestyle=":", alpha=0.6,
                label=f"flow crossover (up=down) ≈ tick {cross_tick}")
    ax1.set_ylabel("strong edges")
    ax1.set_title(f"{prefix} — strong-edge stock")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right")

    ax2.plot(ticks, up_s,   color="#d62728", linewidth=1.2, label="edges_crossed_up (smoothed, w=200)")
    ax2.plot(ticks, down_s, color="#1f77b4", linewidth=1.2, label="edges_crossed_down (smoothed, w=200)")
    ax2.fill_between(ticks, up_s, down_s, where=up_s >= down_s,
                     color="#d62728", alpha=0.10)
    ax2.fill_between(ticks, up_s, down_s, where=up_s <  down_s,
                     color="#1f77b4", alpha=0.10)
    ax2.axvline(peak_tick, color="#2ca02c", linestyle="--", alpha=0.5)
    ax2.axvline(cross_tick, color="#1f77b4", linestyle=":", alpha=0.6)
    ax2.set_xlabel("tick")
    ax2.set_ylabel("crossings per tick")
    ax2.set_title(f"{prefix} — flow into strong (red) vs out of strong (blue)")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper right")

    fig.tight_layout()
    out = OUT_DIR / "06_capacity_flows.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")
    return peak_tick, cross_tick


def plot_strong_refresh(df: pd.DataFrame, prefix: str):
    """Strong-edge-specific refresh rate vs uniform-edge refresh rate.
    Tests the FINDINGS prediction: strong edges get refreshed more often than
    average because partner selection is trust-biased (weight = exp(2*trust))."""
    g = df.groupby("tick")
    ticks = np.array(sorted(df["tick"].unique()))
    refresh_existing = g["refreshes_existing"].mean().values
    refresh_strong   = g["refreshes_strong"].mean().values
    total_edges      = g["total_edges"].mean().values
    strong_edges     = g["strong_edges"].mean().values

    with np.errstate(divide="ignore", invalid="ignore"):
        rate_uniform = np.where(total_edges  > 0, refresh_existing / total_edges,  np.nan)
        rate_strong  = np.where(strong_edges > 0, refresh_strong   / strong_edges, np.nan)

    # smooth — single-tick rates are noisy
    win = 200
    rate_uniform_s = smooth(rate_uniform, win)
    rate_strong_s  = smooth(rate_strong,  win)

    maint_threshold = 0.018
    trust_decay     = 0.002

    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.plot(ticks, rate_uniform_s, color="#2ca02c", linewidth=1.5,
            label="uniform: refreshes_existing / total_edges")
    ax.plot(ticks, rate_strong_s, color="#9467bd", linewidth=1.5,
            label="strong: refreshes_strong / strong_edges")
    ax.axhline(maint_threshold, color="#1f77b4", linestyle=":",
               label=f"single-edge maintenance threshold ≈ {maint_threshold}")
    ax.axhline(trust_decay, color="#d62728", linestyle="--",
               label=f"trust_decay floor = {trust_decay}")
    ax.set_yscale("log")
    ax.set_xlabel("tick"); ax.set_ylabel("refresh rate per edge per tick (log)")
    ax.set_title(f"{prefix} — strong-edge refresh rate vs uniform average")
    ax.grid(True, which="both", alpha=0.3); ax.legend(loc="lower left")
    fig.tight_layout()
    out = OUT_DIR / "07_capacity_strong_refresh.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")

    # Compute a few snapshot rows for the CAPACITY.md table.
    snapshots = [1000, 3000, 6500, 10000, 15000, 19000]
    rows = []
    for t in snapshots:
        if t > ticks[-1]:
            continue
        idx = int(np.argmin(np.abs(ticks - t)))
        rows.append({
            "tick":              ticks[idx],
            "total_edges":       float(total_edges[idx]),
            "strong_edges":      float(strong_edges[idx]),
            "rate_uniform":      float(rate_uniform_s[idx]),
            "rate_strong":       float(rate_strong_s[idx]),
            "ratio":             float(rate_strong_s[idx] / rate_uniform_s[idx])
                                 if rate_uniform_s[idx] > 0 else float("nan"),
        })
    print("\nrefresh-rate snapshot (smoothed, 16-seed mean):")
    print(f"{'tick':>6} {'total':>8} {'strong':>7} {'uniform':>10} {'strong_r':>10} {'ratio':>6}")
    for r in rows:
        print(f"{r['tick']:>6} {r['total_edges']:>8.0f} {r['strong_edges']:>7.0f} "
              f"{r['rate_uniform']:>10.4g} {r['rate_strong']:>10.4g} {r['ratio']:>6.1f}x")


def main():
    prefix = "easy_success"
    df = load(prefix)
    n_seeds = df["seed"].nunique()
    print(f"loaded {prefix}: {n_seeds} seeds, {df['tick'].max()} max tick")
    if "edges_crossed_up" not in df.columns:
        raise SystemExit("metrics.csv missing flow columns — re-run with new instrumentation")
    peak_tick, cross_tick = plot_flows(df, prefix)
    print(f"\nflow-balance check:")
    print(f"  strong-edge stock peak     ≈ tick {peak_tick}")
    print(f"  flow crossover (up == down) ≈ tick {cross_tick}")
    print(f"  delta = {cross_tick - peak_tick} ticks "
          f"({100.0 * (cross_tick - peak_tick) / peak_tick:+.1f}%)")
    plot_strong_refresh(df, prefix)


if __name__ == "__main__":
    main()
