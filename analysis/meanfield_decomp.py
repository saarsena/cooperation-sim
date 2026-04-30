"""Decompose α(bsp), β(bsp), N(bsp) — see if any of them follow simple
analytical forms or if the structure has to be eyeballed.

Run after meanfield_fit.py.
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

TAIL_TICKS = 5000
MIN_RUN_TICK = 50000 - TAIL_TICKS
TRUST_DECAY = 0.002


def load_tail(prefix):
    frames = []
    for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}__seed*"))):
        p = Path(d) / "metrics.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        last = int(df["tick"].max())
        if last < MIN_RUN_TICK:
            continue
        df["seed"] = int(d.split("seed")[-1])
        tail = df[df["tick"] > last - TAIL_TICKS].copy()
        frames.append(tail)
    return pd.concat(frames, ignore_index=True) if frames else None


def main():
    rows = []
    for prefix, bsp in CELLS:
        tail = load_tail(prefix)
        if tail is None: continue
        pos = tail[tail["strong_edges"] > 0]
        if len(pos) < 100: continue
        alpha = float(pos["edges_crossed_up"].mean())
        beta = float(pos["edges_crossed_down"].mean() / pos["strong_edges"].mean())
        s_meas = float(pos["strong_edges"].mean())
        n_meas = float(pos["population"].mean())
        e_meas = float(pos["total_edges"].mean())
        # strong-edge refresh rate measured directly
        ref_strong = float(pos["refreshes_strong"].mean() / pos["strong_edges"].mean())
        # uniform refresh rate
        ref_uniform = float(pos["refreshes_existing"].mean() / pos["total_edges"].mean())
        rows.append({
            "bsp": bsp, "prefix": prefix,
            "alpha": alpha, "beta": beta,
            "N": n_meas, "S": s_meas, "E": e_meas,
            "S_per_N": s_meas / n_meas,
            "E_per_N2": e_meas / (n_meas * (n_meas - 1) / 2),  # network density
            "ref_strong": ref_strong,
            "ref_uniform": ref_uniform,
            "ratio_ref": ref_strong / ref_uniform if ref_uniform > 0 else float("nan"),
        })
    df = pd.DataFrame(rows)

    print(f"\n{'bsp':>5} {'N':>5} {'E':>7} {'E/Nmax':>7} "
          f"{'r_uni':>8} {'r_str':>8} {'r_str/r_uni':>10} "
          f"{'β':>9} {'β/decay':>8}")
    for _, r in df.iterrows():
        print(f"{r['bsp']:>5.2f} {r['N']:>5.0f} {r['E']:>7.0f} "
              f"{r['E_per_N2']:>7.3f} "
              f"{r['ref_uniform']:>8.4f} {r['ref_strong']:>8.4f} "
              f"{r['ratio_ref']:>10.2f} "
              f"{r['beta']:>9.4e} {r['beta']/TRUST_DECAY:>8.2f}")

    print()
    print("β should be ~constant if it depends only on local edge dynamics.")
    print("β/trust_decay tells us how much the actual decay-out rate exceeds")
    print("the bare trust_decay floor. A ratio of 1 = pure decay; >1 = failure-driven.")

    # α decomposition: α = (strong-formation events per tick)
    # Hypothesis: α = (rate of ventures on near-strong-pair-eligible edges)
    #            ≈ ventures_total × P(touches near-strong edge that gets pushed across)
    # Empirically check: α / N (per-agent rate of contributing strong-tie growth)
    print("\nα decomposition:")
    print(f"{'bsp':>5} {'α':>8} {'α/N':>9} {'α/E':>11} "
          f"{'α/(refs×fract_near)':>20}")
    for _, r in df.iterrows():
        print(f"{r['bsp']:>5.2f} {r['alpha']:>8.4f} {r['alpha']/r['N']:>9.4e} "
              f"{r['alpha']/r['E']:>11.4e}")

    # plot α/N and β/trust_decay vs bsp
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    ax = axes[0, 0]
    ax.plot(df["bsp"], df["alpha"] / df["N"], "o-", color="#d62728", linewidth=1.5)
    ax.set_xlabel("base_success_prob")
    ax.set_ylabel("α / N (per-agent contribution to strong formation)")
    ax.set_title("normalized α — per-agent strong-formation flux")
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    ax.plot(df["bsp"], df["beta"] / TRUST_DECAY, "o-", color="#1f77b4", linewidth=1.5)
    ax.axhline(1.0, color="k", linestyle=":", alpha=0.5,
               label="β = trust_decay (pure-decay floor)")
    ax.set_xlabel("base_success_prob"); ax.set_ylabel("β / trust_decay")
    ax.set_title("normalized β — multiple of pure-decay rate")
    ax.grid(True, alpha=0.3); ax.legend()

    ax = axes[1, 0]
    ax.semilogy(df["bsp"], df["ref_uniform"], "o-",
                color="#2ca02c", label="uniform refresh per edge")
    ax.semilogy(df["bsp"], df["ref_strong"], "s-",
                color="#9467bd", label="strong-edge refresh per edge")
    ax.set_xlabel("base_success_prob"); ax.set_ylabel("refreshes per edge per tick (log)")
    ax.set_title("refresh rate per edge")
    ax.grid(True, which="both", alpha=0.3); ax.legend()

    ax = axes[1, 1]
    # network density
    ax.plot(df["bsp"], df["E_per_N2"], "o-", color="#ff7f0e", linewidth=1.5)
    ax.set_xlabel("base_success_prob")
    ax.set_ylabel("E / [N(N-1)/2]   (network density)")
    ax.set_title("connectivity — fraction of possible pairs realized")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1)

    fig.tight_layout()
    out = OUT_DIR / "13_meanfield_decomp.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()
