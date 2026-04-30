"""Phase 4 mean-field α/β extraction.

For each bsp cell we have per-tick measurements of:
- edges_crossed_up: formation flux into strong (α-rate)
- edges_crossed_down: decay-out flux from strong (β·S rate)
- strong_edges: stock S
- population: N

In the steady state (or quasi-steady-state for the slow-collapse cells),
the model dS/dt = α(N,p) - β(p)·S predicts:
  S* = α / β
  β  = down_rate / S
  α  = up_rate at steady state

This script:
1. Computes time-averaged α and β from the last K ticks of each cell's
   metrics.csv, averaged across seeds.
2. Predicts S*_predicted = α / β and compares to S*_measured (=
   time-averaged strong_edges in the same window).
3. Plots predicted vs measured per-capita as a function of bsp.

The test of the framework: do the predicted points trace the same
curve as the measured points? If yes, the boundary curve is just a
direct consequence of how α and β depend on bsp.

Run from repo root:  python3 analysis/meanfield_fit.py
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "analysis" / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CELLS = [
    ("bsp_030", 0.30),
    ("bsp_035", 0.35),
    ("bsp_036", 0.36),
    ("bsp_037", 0.37),
    ("bsp_038", 0.38),
    ("bsp_039", 0.39),
    ("bsp_040", 0.40),
    ("bsp_045", 0.45),
    ("bsp_050", 0.50),
]

TAIL_TICKS = 5000  # window over which to compute steady-state α and β
MIN_RUN_TICK = 50000 - TAIL_TICKS


def load_cell_tail(prefix: str):
    """Return DataFrame of last TAIL_TICKS ticks across all seeds, with seed
    column. Skips runs that didn't reach MIN_RUN_TICK."""
    frames = []
    for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}__seed*"))):
        p = Path(d) / "metrics.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        last_tick = int(df["tick"].max())
        if last_tick < MIN_RUN_TICK:
            continue
        df["seed"] = int(d.split("seed")[-1])
        tail = df[df["tick"] > last_tick - TAIL_TICKS].copy()
        frames.append(tail)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def fit_alpha_beta(tail: pd.DataFrame):
    """Compute steady-state α (= mean up flux) and β (= mean down / mean
    strong_edges) using all rows where strong_edges > 0."""
    pos = tail[tail["strong_edges"] > 0]
    if len(pos) < 100:
        return None
    alpha = float(pos["edges_crossed_up"].mean())
    beta = float(pos["edges_crossed_down"].mean() / pos["strong_edges"].mean())
    s_meas = float(pos["strong_edges"].mean())
    n_meas = float(pos["population"].mean())
    s_pred = alpha / beta if beta > 0 else float("inf")
    return {
        "alpha": alpha,
        "beta": beta,
        "s_measured": s_meas,
        "s_predicted": s_pred,
        "n_measured": n_meas,
        "per_cap_measured": s_meas / n_meas if n_meas > 0 else float("nan"),
        "per_cap_predicted": s_pred / n_meas if n_meas > 0 else float("nan"),
    }


def main():
    rows = []
    for prefix, bsp in CELLS:
        tail = load_cell_tail(prefix)
        if tail is None:
            print(f"  skip {prefix}: no usable runs")
            continue
        fit = fit_alpha_beta(tail)
        if fit is None:
            print(f"  skip {prefix}: too few positive samples")
            continue
        fit["bsp"] = bsp
        fit["prefix"] = prefix
        rows.append(fit)

    if not rows:
        return

    df = pd.DataFrame(rows)

    print(f"\n{'cell':<8} {'bsp':>5} {'α':>9} {'β':>9} {'N':>7} "
          f"{'S_meas':>9} {'S_pred':>9} {'PC_meas':>9} {'PC_pred':>9} "
          f"{'ratio':>6}")
    for _, r in df.iterrows():
        ratio = r["s_predicted"] / r["s_measured"] if r["s_measured"] > 0 else float("inf")
        print(f"{r['prefix']:<8} {r['bsp']:>5.2f} "
              f"{r['alpha']:>9.4f} {r['beta']:>9.4e} "
              f"{r['n_measured']:>7.0f} {r['s_measured']:>9.2f} "
              f"{r['s_predicted']:>9.2f} "
              f"{r['per_cap_measured']:>9.4f} {r['per_cap_predicted']:>9.4f} "
              f"{ratio:>6.2f}")

    # ----- plot α, β vs bsp -----
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    ax = axes[0, 0]
    ax.semilogy(df["bsp"], df["alpha"], "o-", color="#d62728", linewidth=1.5)
    ax.set_xlabel("base_success_prob"); ax.set_ylabel("α (up-flux per tick)")
    ax.set_title("α(bsp): formation flux into strong")
    ax.grid(True, which="both", alpha=0.3)

    ax = axes[0, 1]
    ax.plot(df["bsp"], df["beta"], "o-", color="#1f77b4", linewidth=1.5)
    ax.set_xlabel("base_success_prob"); ax.set_ylabel("β (per-edge decay-out rate)")
    ax.set_title("β(bsp): per-edge decay rate")
    ax.grid(True, alpha=0.3)

    ax = axes[1, 0]
    ax.semilogy(df["bsp"], df["per_cap_measured"], "o-",
                color="#2ca02c", linewidth=1.6, label="measured")
    ax.semilogy(df["bsp"], df["per_cap_predicted"], "s--",
                color="#9467bd", linewidth=1.6, label="α/β / N (predicted)")
    ax.set_xlabel("base_success_prob"); ax.set_ylabel("per-capita strong ties (log)")
    ax.set_title("predicted vs measured per-capita asymptote")
    ax.grid(True, which="both", alpha=0.3); ax.legend()

    ax = axes[1, 1]
    # population vs bsp — drives the network's denominator
    ax.plot(df["bsp"], df["n_measured"], "o-", color="#ff7f0e", linewidth=1.5)
    ax.set_xlabel("base_success_prob"); ax.set_ylabel("population (steady-state mean)")
    ax.set_title("N(bsp): population (denominator of per-capita)")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out = OUT_DIR / "12_meanfield_fit.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")

    # ----- consistency check -----
    if "per_cap_predicted" in df.columns:
        rel_err = (df["per_cap_predicted"] - df["per_cap_measured"]) / df["per_cap_measured"]
        print(f"\nrelative error |pred - meas|/meas:")
        for _, r in df.iterrows():
            err = (r["per_cap_predicted"] - r["per_cap_measured"]) / r["per_cap_measured"]
            print(f"  bsp {r['bsp']:.2f}: {err*100:+.1f}%")
        print(f"  median |error| across cells: {np.median(np.abs(rel_err))*100:.1f}%")


if __name__ == "__main__":
    main()
