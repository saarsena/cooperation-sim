"""Phase 3 boundary diagnostic. Loads the 5-cell base_success_prob sweep
(scenarios bsp_030 ... bsp_050, 8 seeds × 50k ticks per cell) and asks:
where between markers_off (bsp=0.30) and easy_success (bsp=0.50) does the
system bifurcate from a stable per-capita strong-tie floor to exponential
collapse?

Diagnostic plot: per-capita strong ties at tick ~50k vs base_success_prob,
with each seed as a dot, cross-seed mean line, ±1σ band. Also prints a
summary table flagging:
  - sharp drops in mean between adjacent grid points (transition location)
  - high σ at any cell (variance spike near the boundary)
  - bistable cells: same parameters, some seeds collapse and some don't

Run from repo root:  python3 analysis/boundary_sweep.py
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

# tick window over which to average per-capita for the asymptote estimate
ASYMPTOTE_TAIL_TICKS = 500
# minimum tick the run must have reached for the asymptote estimate to be
# meaningful — anything less and we're reading the rising phase, not the tail
MIN_RUN_TICK = 50000 - ASYMPTOTE_TAIL_TICKS


def per_capita_at_tail(metrics_path: Path) -> float | None:
    """Returns the per-capita mean over the last ASYMPTOTE_TAIL_TICKS ticks of
    the run, or None if the run hasn't reached MIN_RUN_TICK (still in
    rising phase — tail estimate would be misleading)."""
    df = pd.read_csv(metrics_path)
    last_tick = int(df["tick"].max())
    if last_tick < MIN_RUN_TICK:
        return None
    tail = df[df["tick"] > last_tick - ASYMPTOTE_TAIL_TICKS]
    pop = tail["population"].astype(float).values
    strong = tail["strong_edges"].astype(float).values
    with np.errstate(divide="ignore", invalid="ignore"):
        per = np.where(pop > 0, strong / pop, np.nan)
    return float(np.nanmean(per))


def load_cell(prefix: str):
    """Return list of (seed, per_capita_tail) for a scenario prefix.
    Skips seeds that haven't reached MIN_RUN_TICK — partial runs are dropped,
    not silently mixed in."""
    rows = []
    skipped = 0
    for d in sorted(glob.glob(str(REPO / "output" / f"{prefix}__seed*"))):
        p = Path(d) / "metrics.csv"
        if not p.exists():
            continue
        try:
            seed = int(d.split("seed")[-1])
        except ValueError:
            seed = -1
        v = per_capita_at_tail(p)
        if v is None:
            skipped += 1
            continue
        rows.append((seed, v))
    if skipped:
        print(f"  {prefix}: skipped {skipped} seeds (run < tick {MIN_RUN_TICK})")
    return rows


def main():
    cells_data = []
    for prefix, bsp in CELLS:
        rows = load_cell(prefix)
        if not rows:
            print(f"  skip {prefix}: no runs")
            continue
        seeds, vals = zip(*rows)
        cells_data.append({
            "prefix": prefix,
            "bsp": bsp,
            "seeds": list(seeds),
            "vals": np.array(vals, dtype=float),
        })

    if not cells_data:
        raise SystemExit("no cells loaded")

    # ----- diagnostic plot -----
    fig, (ax_lin, ax_log) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    for d in cells_data:
        bsp_pts = np.full(len(d["vals"]), d["bsp"])
        for ax in (ax_lin, ax_log):
            ax.scatter(bsp_pts, d["vals"], color="#9467bd",
                       s=42, edgecolor="white", linewidth=0.6,
                       alpha=0.85, zorder=3)
    bsps = np.array([d["bsp"] for d in cells_data])
    means = np.array([np.nanmean(d["vals"]) for d in cells_data])
    stds = np.array([np.nanstd(d["vals"]) for d in cells_data])

    ax_lin.errorbar(bsps, means, yerr=stds, color="#1f77b4",
                    linewidth=2.0, capsize=4, marker="o", markersize=8,
                    label="cross-seed mean ±1σ", zorder=2)
    ax_log.errorbar(bsps, np.maximum(means, 1e-3), yerr=stds,
                    color="#1f77b4", linewidth=2.0, capsize=4,
                    marker="o", markersize=8,
                    label="cross-seed mean ±1σ (clipped at 1e-3)", zorder=2)
    ax_log.set_yscale("log")

    for ax in (ax_lin, ax_log):
        ax.set_xlabel("base_success_prob")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left")
        ax.set_xticks(bsps)
    ax_lin.set_ylabel("per-capita strong ties (linear)")
    ax_log.set_ylabel("per-capita strong ties (log)")
    ax_lin.set_title(
        "Phase boundary along base_success_prob — per-capita strong ties at tick ~50k")
    fig.tight_layout()
    out = OUT_DIR / "10_boundary_diagnostic.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")

    # ----- summary table -----
    print()
    print(f"{'cell':<8} {'bsp':>5} {'n':>3} {'mean':>8} {'std':>8} "
          f"{'median':>8} {'min':>8} {'max':>8} {'CV':>6}")
    for d in cells_data:
        v = d["vals"]
        n = len(v)
        m, s = np.nanmean(v), np.nanstd(v)
        cv = s / m if m > 0 else float("inf")
        print(f"{d['prefix']:<8} {d['bsp']:>5.2f} {n:>3d} "
              f"{m:>8.4f} {s:>8.4f} {np.nanmedian(v):>8.4f} "
              f"{np.nanmin(v):>8.4f} {np.nanmax(v):>8.4f} {cv:>6.2f}")

    # ----- diagnostics -----
    print("\n=== boundary diagnostics ===")

    # 1. Adjacent gradient
    print("\nadjacent-cell drop in mean per-capita:")
    for i in range(1, len(cells_data)):
        a, b = cells_data[i - 1], cells_data[i]
        m_a, m_b = np.nanmean(a["vals"]), np.nanmean(b["vals"])
        drop = m_a - m_b
        rel = drop / m_a if m_a > 0 else float("inf")
        flag = " ← largest drop so far" if i > 1 and abs(drop) > max(
            abs(np.nanmean(cells_data[j-1]["vals"])
                - np.nanmean(cells_data[j]["vals"]))
            for j in range(1, i)
        ) else ""
        print(f"  bsp {a['bsp']:.2f} → {b['bsp']:.2f}: "
              f"{m_a:.4f} → {m_b:.4f} (Δ = {drop:+.4f}, {rel*100:+.1f}%)"
              f"{flag}")

    # 2. Variance spike
    print("\nvariance check (CV = σ/μ — high = noisy regime, "
          "could indicate critical point):")
    cvs = []
    for d in cells_data:
        v = d["vals"]
        m, s = np.nanmean(v), np.nanstd(v)
        cv = s / m if m > 0 else float("inf")
        cvs.append((d["bsp"], cv))
    max_cv = max(cvs, key=lambda x: x[1] if np.isfinite(x[1]) else -1)
    for bsp, cv in cvs:
        flag = " ← peak CV" if (bsp, cv) == max_cv else ""
        print(f"  bsp {bsp:.2f}: CV = {cv:.3f}{flag}")

    # 3. Bistability
    print("\nbistability check (any cell with both 'collapse' and 'stable' seeds):")
    COLLAPSE_THRESHOLD = 0.05
    STABLE_THRESHOLD = 0.5
    found_bistable = False
    for d in cells_data:
        v = d["vals"]
        n_collapse = int(np.sum(v < COLLAPSE_THRESHOLD))
        n_stable = int(np.sum(v > STABLE_THRESHOLD))
        n_other = len(v) - n_collapse - n_stable
        flag = " ← BISTABLE" if (n_collapse > 0 and n_stable > 0) else ""
        if flag:
            found_bistable = True
        print(f"  bsp {d['bsp']:.2f}: "
              f"{n_collapse} collapse (<{COLLAPSE_THRESHOLD}), "
              f"{n_stable} stable (>{STABLE_THRESHOLD}), "
              f"{n_other} intermediate{flag}")
    if not found_bistable:
        print("  no bistable cells — every cell's seeds are in the same regime")

    print("\nrecommended next move:")
    if found_bistable:
        print("  - upgrade the bistable cell(s) to 16 seeds to estimate basin sizes")
    elif np.argmax([cvs[i][1] - cvs[i-1][1] if i > 0 else 0
                    for i in range(len(cvs))]) > 0:
        # variance pickup between cells suggests refining grid
        print("  - consider refining grid between the two cells with the "
              "highest variance gap")
    else:
        # smooth transition; either the grid is too coarse or it's truly gradual
        print("  - transition looks smooth across the 5 grid points; either")
        print("    (a) we already see the boundary clearly, no refinement needed, or")
        print("    (b) refine to 9 points (add 0.325/0.375/0.425/0.475) to "
              "characterize shape")


if __name__ == "__main__":
    main()
