"""Test the simplest possible analytical model:
    α = c · N · venture_chance · base_success_prob   (formation events arrive
                                                       proportional to attempts × success)
    β = trust_decay                                   (one trust-decay-per-tick at the
                                                       threshold-crossing scale)
   ⇒ S* = α / β = c · N · vc · bsp / trust_decay
   ⇒ per-capita = S* / N = c · vc · bsp / trust_decay

The constant c we calibrate from a single anchor cell (bsp=0.30) and then
predict the rest. If it fits, we have a closed-form theory of f(bsp). If it
fails, the failure tells us what's missing.
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "analysis" / "plots"

CELLS = [
    ("bsp_030", 0.30), ("bsp_035", 0.35), ("bsp_036", 0.36),
    ("bsp_037", 0.37), ("bsp_038", 0.38), ("bsp_039", 0.39),
    ("bsp_040", 0.40), ("bsp_045", 0.45), ("bsp_050", 0.50),
]

VC = 0.4
TRUST_DECAY = 0.002
TAIL_TICKS = 5000
MIN_RUN_TICK = 50000 - TAIL_TICKS


def load_cell_summary(prefix):
    frames = []
    for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}__seed*"))):
        p = Path(d) / "metrics.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        last = int(df["tick"].max())
        if last < MIN_RUN_TICK:
            continue
        tail = df[df["tick"] > last - TAIL_TICKS]
        frames.append(tail)
    if not frames:
        return None
    tail = pd.concat(frames, ignore_index=True)
    return {
        "N": float(tail["population"].mean()),
        "S": float(tail["strong_edges"].mean()),
        "per_cap_meas": float((tail["strong_edges"] / tail["population"].clip(lower=1)).mean()),
    }


def main():
    rows = []
    for prefix, bsp in CELLS:
        s = load_cell_summary(prefix)
        if s is None: continue
        rows.append({"prefix": prefix, "bsp": bsp, **s})
    df = pd.DataFrame(rows)

    # calibrate c at the bsp=0.30 anchor: per-capita = c · vc · bsp / trust_decay
    anchor = df[df["bsp"] == 0.30].iloc[0]
    c = anchor["per_cap_meas"] * TRUST_DECAY / (VC * 0.30)
    print(f"calibrating at bsp=0.30: per_cap_meas = {anchor['per_cap_meas']:.4f}")
    print(f"  c = per_cap × trust_decay / (vc · bsp) = {c:.6f}")
    print()
    print(f"simplest model:  per_capita_pred = c · vc · bsp / trust_decay")
    print(f"with c = {c:.4f}, vc = {VC}, trust_decay = {TRUST_DECAY}")

    df["per_cap_pred_simplest"] = c * VC * df["bsp"] / TRUST_DECAY

    # also try a refined model: same form but β = trust_decay · k(N) with
    # k(N) = β_meas / trust_decay measured per cell. This isolates whether
    # α is really proportional to N · vc · bsp by inverting the empirical β.
    # If α / (N · vc · bsp) is constant across cells, the formation-rate
    # piece of the model is right and only β needs work.
    # We need α from previous fits — quickest is to recompute from the same tails:
    refined = []
    for prefix, bsp in CELLS:
        frames = []
        for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}__seed*"))):
            p = Path(d) / "metrics.csv"
            if not p.exists(): continue
            sub = pd.read_csv(p)
            last = int(sub["tick"].max())
            if last < MIN_RUN_TICK: continue
            sub = sub[sub["tick"] > last - TAIL_TICKS]
            frames.append(sub)
        if not frames: continue
        sub = pd.concat(frames, ignore_index=True)
        pos = sub[sub["strong_edges"] > 0]
        if len(pos) < 100: continue
        alpha_meas = float(pos["edges_crossed_up"].mean())
        beta_meas = float(pos["edges_crossed_down"].mean() / pos["strong_edges"].mean())
        N = float(pos["population"].mean())
        refined.append({"bsp": bsp, "N": N, "alpha": alpha_meas, "beta": beta_meas})
    rdf = pd.DataFrame(refined)
    rdf["alpha_norm"]    = rdf["alpha"] / (rdf["N"] * VC * rdf["bsp"])
    rdf["beta_decay_ratio"] = rdf["beta"] / TRUST_DECAY

    print(f"\n  bsp     N    α_meas   α / (N·vc·bsp)    β_meas   β / trust_decay")
    for _, r in rdf.iterrows():
        print(f"  {r['bsp']:.2f} {r['N']:>5.0f}  {r['alpha']:>8.4f}  "
              f"{r['alpha_norm']:>14.6f}    "
              f"{r['beta']:>8.4e}  {r['beta_decay_ratio']:>8.2f}")

    print()
    print("If α / (N·vc·bsp) is constant across cells, then α∝N·vc·bsp is correct")
    print("and only β needs to be modeled. Otherwise the formation-rate term is wrong too.")

    # ---- predicted-vs-measured plot ----
    fig, axes = plt.subplots(2, 1, figsize=(11, 8))
    ax = axes[0]
    ax.semilogy(df["bsp"], df["per_cap_meas"], "o-", color="#2ca02c",
                linewidth=1.6, label="measured")
    ax.semilogy(df["bsp"], df["per_cap_pred_simplest"], "s--",
                color="#d62728", linewidth=1.6,
                label="simplest model: c·vc·bsp / trust_decay")
    ax.set_xlabel("base_success_prob")
    ax.set_ylabel("per-capita strong ties (log)")
    ax.set_title("simplest analytical model (α∝N·vc·bsp, β=trust_decay) "
                 "— calibrated at bsp=0.30")
    ax.grid(True, which="both", alpha=0.3); ax.legend()

    ax = axes[1]
    ax.plot(rdf["bsp"], rdf["alpha_norm"], "o-", color="#1f77b4", linewidth=1.5,
            label="α_meas / (N·vc·bsp)")
    ax.set_xlabel("base_success_prob")
    ax.set_ylabel("α_meas / (N·vc·bsp)")
    ax.set_title("formation-rate term diagnostic — is α ∝ N·vc·bsp?")
    ax.grid(True, alpha=0.3); ax.legend()
    ax.set_yscale("log")

    fig.tight_layout()
    out = OUT_DIR / "14_simplest_model.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")

    # quantify the failure
    err_simplest = np.log(df["per_cap_pred_simplest"] / df["per_cap_meas"])
    print(f"\nlog-ratio (pred/meas) per cell:")
    for _, r in df.iterrows():
        ratio = r["per_cap_pred_simplest"] / r["per_cap_meas"]
        print(f"  bsp {r['bsp']:.2f}: pred = {r['per_cap_pred_simplest']:.4f}, "
              f"meas = {r['per_cap_meas']:.4f}, ratio = {ratio:.2f}× "
              f"({'overestimate' if ratio > 1 else 'underestimate'})")

    print(f"\nRatio range: {min(df['per_cap_pred_simplest']/df['per_cap_meas']):.1f}× "
          f"to {max(df['per_cap_pred_simplest']/df['per_cap_meas']):.1f}×")


if __name__ == "__main__":
    main()
