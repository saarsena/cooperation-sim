"""Compare 8-seed and 16-seed estimates at bsp 0.38, 0.39, 0.40 to test
whether the variance bump at bsp=0.39 (CV = 0.21 in 8-seed data) is a
genuine critical-region signature or finite-sample noise."""
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "analysis" / "plots"

CELLS = [
    ("bsp_038", "bsp_038_n16", 0.38),
    ("bsp_039", "bsp_039_n16", 0.39),
    ("bsp_040", "bsp_040_n16", 0.40),
]

TAIL = 500
MIN_TICK = 50000 - TAIL


def per_capita_at_tail(metrics_path):
    df = pd.read_csv(metrics_path)
    last = int(df["tick"].max())
    if last < MIN_TICK:
        return None
    tail = df[df["tick"] > last - TAIL]
    pop = tail["population"].astype(float).values
    strong = tail["strong_edges"].astype(float).values
    return float(np.where(pop > 0, strong / pop, np.nan).mean())


def load_cell(prefix):
    vals = []
    for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}__seed*"))):
        p = Path(d) / "metrics.csv"
        if not p.exists(): continue
        v = per_capita_at_tail(p)
        if v is None: continue
        vals.append(v)
    return np.array(vals)


def stats(vals):
    if len(vals) == 0:
        return None
    return {
        "n": len(vals),
        "mean": float(np.mean(vals)),
        "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
        "cv": float(np.std(vals, ddof=1) / np.mean(vals)) if len(vals) > 1 and np.mean(vals) > 0 else 0.0,
        "median": float(np.median(vals)),
        "min": float(np.min(vals)),
        "max": float(np.max(vals)),
    }


def main():
    rows = []
    print(f"{'cell':<6} {'bsp':>5} {'n':>3} {'mean':>9} {'std':>9} {'cv':>6} "
          f"{'median':>9} {'min':>9} {'max':>9}")
    for n8_prefix, n16_prefix, bsp in CELLS:
        for label, prefix in [("8-seed", n8_prefix), ("16-seed", n16_prefix)]:
            vals = load_cell(prefix)
            s = stats(vals)
            if s is None:
                print(f"  {label:<6} bsp {bsp:.2f}: no data")
                continue
            rows.append({"label": label, "bsp": bsp, "vals": vals, **s})
            print(f"{label:<6} {bsp:>5.2f} {s['n']:>3d} {s['mean']:>9.4f} "
                  f"{s['std']:>9.4f} {s['cv']:>6.3f} "
                  f"{s['median']:>9.4f} {s['min']:>9.4f} {s['max']:>9.4f}")

    df = pd.DataFrame(rows)

    # ---- plot per-seed values, 8-seed and 16-seed, side by side ----
    fig, ax = plt.subplots(figsize=(11, 5.5))
    bsps = sorted(set(r["bsp"] for r in rows))
    for r in rows:
        offset = -0.005 if r["label"] == "8-seed" else 0.005
        color = "#1f77b4" if r["label"] == "8-seed" else "#d62728"
        x = np.full(len(r["vals"]), r["bsp"] + offset)
        ax.scatter(x, r["vals"], color=color, s=30, alpha=0.7, zorder=3,
                   label=f"{r['label']} (n={r['n']})" if r["bsp"] == bsps[0] else None)
        ax.errorbar([r["bsp"] + offset], [r["mean"]], yerr=[r["std"]],
                    color=color, fmt="o", markersize=10, capsize=4, zorder=2)
    ax.set_yscale("log")
    ax.set_xlabel("base_success_prob")
    ax.set_ylabel("per-capita strong ties (log)")
    ax.set_title("8-seed vs 16-seed: variance bump robustness check at the boundary")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    ax.set_xticks(bsps)
    fig.tight_layout()
    out = OUT_DIR / "15_n16_compare.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  wrote {out}")

    # CV comparison
    print("\nCV comparison (8-seed vs 16-seed):")
    for bsp in bsps:
        cv8 = next((r["cv"] for r in rows
                    if r["bsp"] == bsp and r["label"] == "8-seed"), None)
        cv16 = next((r["cv"] for r in rows
                     if r["bsp"] == bsp and r["label"] == "16-seed"), None)
        if cv8 is not None and cv16 is not None:
            print(f"  bsp {bsp:.2f}: 8-seed CV = {cv8:.3f}, 16-seed CV = {cv16:.3f} "
                  f"({'consistent' if abs(cv16-cv8)/max(cv8,1e-3) < 0.4 else 'differs >40%'})")


if __name__ == "__main__":
    main()
