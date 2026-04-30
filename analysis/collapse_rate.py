"""Fit the easy_success collapse rate from the long-horizon pilot trace.
The Phase 2 pilot is a single seed of easy_success at 100 000 ticks. If the
collapse-side dynamics follow d(S/N)/dt = -λ · (S/N), then ln(per-capita)
should fall linearly in tick. This script fits that line over windowed
ranges and checks whether the slope is constant.

Run from repo root:  python3 analysis/collapse_rate.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "analysis" / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PILOT = REPO / "output" / "easy_success_100k_pilot" / "metrics.csv"
WINDOWS = [(5_000, 15_000), (15_000, 25_000), (25_000, 40_000),
           (40_000, 70_000), (70_000, 100_000)]

# Asymptotic per-capita floor for easy_success regime, taken from
# the boundary-sweep mean-field fit (bsp_050 → S*/N ≈ 0.0186, but we
# expect the pilot at bsp=0.50 with infinite time to converge to that).
# We'll empirically fit S_INF below as well as use this as a starting point.
S_INF_CANDIDATES = [0.0, 0.005, 0.01, 0.012, 0.015, 0.018, 0.020, 0.025]


def fit_window(ticks, y, t0, t1, s_inf):
    mask = (ticks >= t0) & (ticks <= t1)
    x = ticks[mask].astype(float)
    yy = y[mask] - s_inf
    keep = (yy > 0) & np.isfinite(yy)
    if keep.sum() < 100:
        return None
    log_yy = np.log(yy[keep])
    slope, intercept = np.polyfit(x[keep], log_yy, 1)
    return slope, intercept, keep.sum()


def main():
    if not PILOT.exists():
        sys.exit(f"pilot not found: {PILOT}")
    df = pd.read_csv(PILOT)
    last_tick = int(df["tick"].max())
    print(f"loaded pilot: {len(df)} rows, max tick {last_tick}")

    pop = df["population"].astype(float).values
    strong = df["strong_edges"].astype(float).values
    ticks = df["tick"].astype(int).values
    with np.errstate(divide="ignore", invalid="ignore"):
        per_cap = np.where(pop > 0, strong / pop, np.nan)

    # smooth a bit so the fit isn't dominated by single-tick integer noise
    per_cap_smoothed = pd.Series(per_cap).rolling(
        window=200, center=True, min_periods=1).mean().values

    # ----- scan candidate S_INF values; pick the one that gives the most-constant
    # τ across windows (lowest spread of slopes) -----
    best_s_inf = 0.0
    best_spread = float("inf")
    print("\nscanning S_INF candidates (model: dS/dt = -1/τ · (S - S_INF)):")
    print(f"{'S_INF':>8} {'τ_5-15k':>10} {'τ_15-25k':>10} {'τ_25-40k':>10} "
          f"{'τ_40-70k':>10} {'τ_70+':>10} {'spread':>8}")
    scan_results = []
    for s_inf in S_INF_CANDIDATES:
        taus = []
        for t0, t1 in WINDOWS:
            if t1 > last_tick:
                t1 = last_tick
            if t1 - t0 < 1000:
                taus.append(None); continue
            r = fit_window(ticks, per_cap_smoothed, t0, t1, s_inf)
            if r is None:
                taus.append(None); continue
            slope, _, _ = r
            taus.append(-1.0 / slope if slope < 0 else float("inf"))
        finite_taus = [t for t in taus if t is not None and np.isfinite(t) and t > 0]
        if len(finite_taus) < 3:
            continue
        # compare on log-tau spread (since τ varies over orders of magnitude)
        log_taus = np.log(finite_taus)
        spread = float(log_taus.max() - log_taus.min())
        scan_results.append((s_inf, taus, spread))
        tau_strs = []
        for t in taus:
            if t is None or not np.isfinite(t):
                tau_strs.append("    -    ")
            else:
                tau_strs.append(f"{t:>10.0f}")
        print(f"{s_inf:>8.4f} {' '.join(tau_strs)} {spread:>8.2f}")
        if spread < best_spread:
            best_spread = spread
            best_s_inf = s_inf

    print(f"\n→ best S_INF = {best_s_inf:.4f} (log-τ spread = {best_spread:.2f})")
    print(f"→ S=0 baseline log-τ spread = "
          f"{[s for v,_,s in scan_results if v == 0.0][0]:.2f}")

    # final fits at best_s_inf
    print(f"\nfinal fits with S_INF = {best_s_inf:.4f}:")
    fits = []
    for t0, t1 in WINDOWS:
        if t1 > last_tick:
            t1 = last_tick
        if t1 - t0 < 1000:
            print(f"  skip {t0}-{t1}: too short"); continue
        r = fit_window(ticks, per_cap_smoothed, t0, t1, best_s_inf)
        if r is None:
            print(f"  skip {t0}-{t1}: too few positive samples"); continue
        slope, intercept, n_kept = r
        half_life = np.log(0.5) / slope if slope < 0 else float("inf")
        fits.append((t0, t1, slope, intercept, half_life))
        print(f"  window [{t0:>6},{t1:>6}]: "
              f"slope = {slope:+.3e}/tick, "
              f"τ = {-1/slope:>7.0f} ticks, "
              f"t_½ = {half_life:>7.0f} ticks   "
              f"({n_kept} samples)")

    if not fits:
        sys.exit("no usable fits")

    # ----- plot: per_cap, per_cap - S_INF (log), with windowed fits -----
    fig, (ax_raw, ax_shift) = plt.subplots(2, 1, figsize=(11, 8))

    ax_raw.plot(ticks, per_cap_smoothed, color="#4c72b0", linewidth=1.0,
                alpha=0.7, label="per-capita (smoothed w=200)")
    ax_raw.axhline(best_s_inf, color="#d62728", linestyle="--", linewidth=1.0,
                   label=f"S_INF = {best_s_inf:.4f}")
    ax_raw.set_yscale("log")
    ax_raw.set_xlabel("tick"); ax_raw.set_ylabel("per-capita strong ties (log)")
    ax_raw.set_title("pilot trace — per-capita over time")
    ax_raw.grid(True, which="both", alpha=0.3); ax_raw.legend(loc="upper right")

    shifted = per_cap_smoothed - best_s_inf
    ax_shift.plot(ticks, np.where(shifted > 0, shifted, np.nan),
                  color="#4c72b0", linewidth=1.0, alpha=0.7,
                  label=f"per-capita − S_INF (S_INF = {best_s_inf:.4f})")
    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(fits)))
    for (t0, t1, slope, intercept, _), color in zip(fits, colors):
        x = np.linspace(t0, t1, 200)
        y = np.exp(intercept + slope * x)
        ax_shift.plot(x, y, color=color, linewidth=2.0,
                      label=f"[{t0/1000:.0f}–{t1/1000:.0f}k] τ={-1/slope:.0f} ticks")
    ax_shift.set_yscale("log")
    ax_shift.set_xlabel("tick"); ax_shift.set_ylabel("per-capita − S_INF (log)")
    ax_shift.set_title(f"shifted trace — should be a straight line if dS/dt = (S_INF - S)/τ")
    ax_shift.grid(True, which="both", alpha=0.3); ax_shift.legend(loc="lower left", fontsize=8)

    fig.tight_layout()
    out = OUT_DIR / "11_collapse_rate.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  wrote {out}")

    # consistency check: are slopes in the windowed fits similar?
    slopes = [f[2] for f in fits]
    if len(slopes) >= 2:
        log_taus = [np.log(-1.0 / s) for s in slopes if s < 0]
        spread = max(log_taus) - min(log_taus)
        print(f"\nlog-τ spread across windows at S_INF={best_s_inf:.4f}: {spread:.2f}")
        if spread < 0.30:
            print("  → roughly constant τ — single-rate ODE dS/dt=(S_INF-S)/τ fits")
        elif spread < 0.7:
            print("  → modest τ drift — single-τ ODE is approximately right")
        else:
            print("  → large τ drift — model is more than one-rate; investigate")


if __name__ == "__main__":
    main()
