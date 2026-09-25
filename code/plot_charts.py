#!/usr/bin/env python3
"""Regenerate every chart and data table referenced by the weekly notes.

Usage (from the repository root)::

    python3 code/plot_charts.py

Outputs
-------
weeks/week-01/charts/emission_curve.png
weeks/week-01/charts/cumulative_supply.png
weeks/week-01/charts/uncle_pin_split.png
weeks/week-01/charts/fixed_point_drift.png
weeks/week-01/charts/l1_ceiling.png
data/emission_milestones.csv
data/emission_curve_sampled.csv
data/genesis_contracts.csv
data/l1_circuit_inventory.csv
data/l1_wire_formats.csv

Everything is derived from the integer consensus functions in
``darkwow_research`` -- the plots are just a projection of those numbers.
The exponential phase (~4.33 M blocks) is swept exactly, block by block;
that takes ~10-20 s of pure Python.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from darkwow_research import emission as em  # noqa: E402
from darkwow_research import genesis as g  # noqa: E402
from darkwow_research import l1_circuits as l1  # noqa: E402
from darkwow_research import uncle_split as us  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CHARTS = ROOT / "weeks" / "week-01" / "charts"
DATA = ROOT / "data"

DRKW = em.BASE_UNITS_PER_DRKW
SAMPLE_STEP = 2_630  # ~0.01 year

C_DARKWOW = "#7c3aed"
C_BITCOIN = "#f59e0b"
C_TAIL = "#059669"
C_GREY = "#6b7280"
C_CANON = "#1f2937"
C_UNCLE = "#a78bfa"


# --------------------------------------------------------------------------------------
# exact sweep of the exponential phase
# --------------------------------------------------------------------------------------


def sweep_exponential_phase(onset: int, step: int):
    """Return (heights, rewards, supplies) sampled every ``step`` blocks up to ``onset``."""
    hs, rs, ss = [], [], []
    total = 0
    for h in range(1, onset):
        r = em.expected_reward(h)
        total += r
        if h == 1 or h % step == 0:
            hs.append(h)
            rs.append(r)
            ss.append(total)
    hs.append(onset - 1)
    rs.append(em.expected_reward(onset - 1))
    ss.append(total)
    return np.array(hs), np.array(rs, dtype=np.float64), np.array(ss, dtype=np.float64), total


def supply_at(height: int, onset: int, supply_before_onset: int) -> int:
    if height < onset:
        raise ValueError("use the sweep for pre-onset heights")
    return supply_before_onset + (height - onset + 1) * em.TAIL_REWARD


def extend_with_tail(hs, rs, ss, onset, supply_before_onset, max_years, step):
    """Append closed-form tail samples so curves run out to ``max_years``."""
    max_h = em.height_at_years(max_years)
    tail_h = np.arange(onset, max_h + 1, step)
    if tail_h.size == 0 or tail_h[-1] != max_h:
        tail_h = np.append(tail_h, max_h)
    tail_s = supply_before_onset + (tail_h - onset + 1) * em.TAIL_REWARD
    tail_r = np.full(tail_h.shape, em.TAIL_REWARD, dtype=np.float64)
    return (
        np.concatenate([hs, tail_h]),
        np.concatenate([rs, tail_r]),
        np.concatenate([ss, tail_s.astype(np.float64)]),
    )


# --------------------------------------------------------------------------------------
# charts
# --------------------------------------------------------------------------------------


def chart_emission_curve(hs, rs, onset):
    years = hs / em.BLOCKS_PER_YEAR
    fig, ax = plt.subplots(figsize=(10, 5.2))

    # Bitcoin-style step halving of the same R0 for contrast (no tail floor).
    step_years = np.linspace(0, 25, 2_501)
    step_reward = em.INITIAL_REWARD * 0.5 ** np.floor(step_years * em.BLOCKS_PER_YEAR / em.HALF_LIFE_BLOCKS)
    ax.step(step_years, step_reward / DRKW, where="post", color=C_BITCOIN, lw=1.4, alpha=0.9,
            label="Bitcoin-style step halving (same R₀, H) — for contrast")

    ax.plot(years, rs / DRKW, color=C_DARKWOW, lw=2.4, label="DarkWow expected_reward(h) — consensus integers")
    ax.axhline(em.TAIL_REWARD / DRKW, color=C_TAIL, ls="--", lw=1.3,
               label=f"Tail floor R_tail = {em.TAIL_REWARD / DRKW:.4f} DRKW (1 %/yr of 21 M)")
    onset_years = onset / em.BLOCKS_PER_YEAR
    ax.axvline(onset_years, color=C_TAIL, ls=":", lw=1.1)
    ax.annotate(f"tail onset\nh = {onset:,}\n≈ {onset_years:.2f} yr", xy=(onset_years, em.TAIL_REWARD / DRKW),
                xytext=(onset_years + 0.6, 3.2), fontsize=8.5, color=C_TAIL,
                arrowprops=dict(arrowstyle="->", color=C_TAIL, lw=0.9))

    for k in (1, 2, 3, 4):
        y = k * em.HALF_LIFE_BLOCKS / em.BLOCKS_PER_YEAR
        ax.axvline(y, color=C_GREY, lw=0.6, alpha=0.5)
        ax.text(y, 0.15, f"{k} half-life", ha="center", va="bottom", fontsize=7.5, color=C_GREY)

    ax.set_xlim(0, 25)
    ax.set_ylim(0, 15)
    ax.set_xlabel("Years since genesis (120 s blocks, 262,980 blocks / year)")
    ax.set_ylabel("Block reward (DRKW)")
    ax.set_title("DarkWow emission: continuous 4-year half-life decay onto a perpetual tail")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper right", fontsize=8.5, frameon=True)
    fig.tight_layout()
    fig.savefig(CHARTS / "emission_curve.png", dpi=160)
    plt.close(fig)


def chart_cumulative_supply(hs, rs, ss, onset):
    years = hs / em.BLOCKS_PER_YEAR
    supply_m = ss / DRKW / 1e6
    inflation = 100.0 * rs * em.BLOCKS_PER_YEAR / ss

    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(years, supply_m, color=C_DARKWOW, lw=2.4, label="Cumulative supply (exact integer sum)")
    ax.axhline(21.0, color=C_GREY, ls="--", lw=1.1, label="21 M DRKW reference (not a hard cap)")
    onset_years = onset / em.BLOCKS_PER_YEAR
    ax.axvline(onset_years, color=C_TAIL, ls=":", lw=1.1, label=f"Tail onset ≈ {onset_years:.2f} yr")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, max(40, supply_m.max() * 1.05))
    ax.set_xlabel("Years since genesis")
    ax.set_ylabel("Total supply (millions of DRKW)", color=C_DARKWOW)
    ax.grid(alpha=0.25)

    ax2 = ax.twinx()
    mask = years >= 1.0  # inflation is undefined-ish in the first months
    ax2.plot(years[mask], inflation[mask], color=C_BITCOIN, lw=1.6, label="Annual inflation (forward 1 yr)")
    ax2.set_yscale("log")
    ax2.set_ylim(0.1, 100)
    ax2.set_ylabel("Annual inflation, % (log)", color=C_BITCOIN)

    lines, labels = ax.get_legend_handles_labels()
    l2, lb2 = ax2.get_legend_handles_labels()
    ax.legend(lines + l2, labels + lb2, loc="center right", fontsize=8.5)
    cross_21m = years[np.searchsorted(supply_m, 21.0)]
    ax.annotate(f"crosses 21 M ≈ yr {cross_21m:.1f}", xy=(cross_21m, 21.0), xytext=(cross_21m + 4, 14.5),
                fontsize=8.5, color=C_GREY, arrowprops=dict(arrowstyle="->", color=C_GREY, lw=0.8))
    ax.set_title("DarkWow supply over 100 years: ~19.8 M at tail onset, then +210 k DRKW / year forever")
    fig.tight_layout()
    fig.savefig(CHARTS / "cumulative_supply.png", dpi=160)
    plt.close(fig)


def chart_uncle_pin_split():
    rows = us.pin_table()
    depths = [f"depth {d}" for d, _, _ in rows]
    uncle = [u for _, u, _ in rows]
    canon = [c for _, _, c in rows]

    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(rows))
    ax.barh(y, canon, color=C_CANON, label="Canonical miner keeps")
    ax.barh(y, uncle, left=canon, color=C_UNCLE, label="Uncle pin (base / 2^depth)")
    for i, (u, c) in enumerate(zip(uncle, canon)):
        ax.text(c / 2, i, f"{c:.4g} %", va="center", ha="center", color="white", fontsize=9)
        if u >= 10:
            ax.text(c + u / 2, i, f"{u:.4g} %", va="center", ha="center", color="#111", fontsize=9)
        else:
            ax.text(101, i, f"{u:.4g} %", va="center", ha="left", color="#4c1d95", fontsize=9)
    ax.set_yticks(y, depths)
    ax.invert_yaxis()
    ax.set_xlim(0, 112)
    ax.set_xlabel("Share of the block's base reward (%) — always sums to exactly 100 %")
    ax.set_title("Uncle Merkle pin split: subtractive, no over-minting (MAX_UNCLE_DEPTH = 6)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=9, frameon=False)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "uncle_pin_split.png", dpi=160)
    plt.close(fig)


def chart_l1_ceiling():
    """Public inputs and witness-only values per L1 circuit against the Book's ceiling."""
    labels = [f"{c.contract.replace('promissory_note', 'PN')}\n{c.name}" for c in l1.CIRCUITS]
    pub = [len(c.public_inputs) for c in l1.CIRCUITS]
    wit = [c.witness_only for c in l1.CIRCUITS]

    fig, ax = plt.subplots(figsize=(11, 4.8))
    x = np.arange(len(labels))
    width = 0.38
    ax.bar(x - width / 2, pub, width, color=C_DARKWOW, label="public inputs (constrain_instance)")
    ax.bar(x + width / 2, wit, width, color=C_UNCLE, label="witness-only values")
    ax.axhline(l1.P_CEILING, color=C_DARKWOW, ls="--", lw=1)
    ax.axhline(l1.W_CEILING, color=C_UNCLE, ls="--", lw=1)
    ax.text(len(labels) - 0.5, l1.P_CEILING + 0.2, f"P_CEILING = {l1.P_CEILING}", ha="right", color=C_DARKWOW, fontsize=9)
    ax.text(len(labels) - 0.5, l1.W_CEILING + 0.2, f"W_CEILING = {l1.W_CEILING}", ha="right", color="#4c1d95", fontsize=9)
    for i, (p, w) in enumerate(zip(pub, wit)):
        ax.text(i - width / 2, p + 0.15, str(p), ha="center", fontsize=8, color=C_CANON)
        ax.text(i + width / 2, w + 0.15, str(w), ha="center", fontsize=8, color=C_CANON)
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylabel("count per circuit")
    ax.set_ylim(0, 15)
    ax.set_title("Halo2 L1 complexity ceiling — the Book triages Box and Purse; Promissory Note is L1 too")
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "l1_ceiling.png", dpi=160)
    plt.close(fig)


def chart_fixed_point_drift(hs, rs, onset):
    ideal = np.array([em.ideal_reward(int(h)) for h in hs])
    ppm = (rs - ideal) / ideal * 1e6
    years = hs / em.BLOCKS_PER_YEAR

    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.plot(years, ppm, color=C_DARKWOW, lw=1.8)
    ax.axhline(0, color=C_GREY, lw=0.8)
    ax.set_xlim(0, onset / em.BLOCKS_PER_YEAR)
    ax.set_xlabel("Years since genesis (exponential phase only)")
    ax.set_ylabel("consensus − ideal, parts per million")
    ax.set_title("Q32 fixed-point truncation: consensus reward drifts below the ideal 2^(−(h−1)/H) curve")
    ax.grid(alpha=0.25)
    ax.annotate(f"at 1 half-life: {ppm[np.searchsorted(hs, em.HALF_LIFE_BLOCKS + 1)]:.0f} ppm\n"
                f"(R = {em.expected_reward(em.HALF_LIFE_BLOCKS + 1) / DRKW:.6f} vs "
                f"{em.INITIAL_REWARD / 2 / DRKW:.6f} DRKW)",
                xy=(4, ppm[np.searchsorted(hs, em.HALF_LIFE_BLOCKS + 1)]), xytext=(6, ppm.min() * 0.35),
                fontsize=8.5, arrowprops=dict(arrowstyle="->", lw=0.8))
    fig.tight_layout()
    fig.savefig(CHARTS / "fixed_point_drift.png", dpi=160)
    plt.close(fig)


# --------------------------------------------------------------------------------------
# data tables
# --------------------------------------------------------------------------------------


def write_milestones(hs, ss, onset, supply_before_onset):
    def exact_supply(h: int) -> int:
        if h >= onset:
            return supply_at(h, onset, supply_before_onset)
        # nearest sampled point at or below h, then top up exactly
        i = int(np.searchsorted(hs, h, side="right") - 1)
        total = int(ss[i])
        for hh in range(int(hs[i]) + 1, h + 1):
            total += em.expected_reward(hh)
        return total

    years = [1, 2, 4, 8, 12, 16, None, 20, 50, 100, 200]
    rows = []
    for y in years:
        h = onset if y is None else em.height_at_years(y)
        r = em.expected_reward(h)
        s = exact_supply(h)
        rows.append({
            "label": "tail onset" if y is None else f"{y} yr",
            "years": round(h / em.BLOCKS_PER_YEAR, 3),
            "height": h,
            "reward_base_units": r,
            "reward_drkw": round(r / DRKW, 8),
            "supply_base_units": s,
            "supply_drkw": round(s / DRKW, 2),
            "annual_inflation_pct": round(100.0 * r * em.BLOCKS_PER_YEAR / s, 3),
        })
    with (DATA / "emission_milestones.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def write_sampled_curve(hs, rs, ss):
    with (DATA / "emission_curve_sampled.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["height", "years", "reward_base_units", "supply_base_units"])
        for h, r, s in zip(hs, rs, ss):
            w.writerow([int(h), f"{h / em.BLOCKS_PER_YEAR:.4f}", int(r), int(s)])


def write_genesis_table():
    with (DATA / "genesis_contracts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["genesis_tx_position", "counter", "name", "crate", "role", "derivation", "purpose"])
        for c in g.GENESIS_CONTRACTS:
            w.writerow([c.genesis_position, c.counter, c.name, c.crate, c.role.value, c.derivation, c.purpose])


def write_l1_tables():
    with (DATA / "l1_circuit_inventory.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "contract", "circuit", "source", "k", "witness_slots", "public_inputs", "witness_only",
            "public_input_tier", "witness_tier", "consumes", "creates", "poseidon_calls", "ec_ops",
            "range_checks", "merkle_roots", "leaf_binds_owner", "max_nullifiers_per_leaf", "public_inputs_in_order",
        ])
        for c in l1.CIRCUITS:
            nf = c.max_nullifiers_per_leaf
            w.writerow([
                c.contract, c.name, c.source, c.k, len(c.witnesses), len(c.public_inputs), c.witness_only,
                c.public_input_tier.value, c.witness_tier.value, c.consumes, c.creates, c.poseidon_calls,
                c.ec_ops, c.range_checks, c.merkle_roots, c.leaf_binds_owner,
                "unbounded" if nf is None else nf, " ".join(c.public_inputs),
            ])
    with (DATA / "l1_wire_formats.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["contract", "struct", "offset", "field", "bytes", "plaintext_witness", "note"])
        for fmt in l1.WIRE_FORMATS:
            off = 0
            for fld in fmt.fields:
                w.writerow([fmt.contract, fmt.struct, off, fld.name, fld.size, fld.witness_only, fld.note])
                off += fld.size
            w.writerow([fmt.contract, fmt.struct, off, "(total, excluding proof bytes)", fmt.encoded_size(), "", f"hdr={fmt.header_bytes}"])


def print_markdown_milestones(rows):
    print("\n| Milestone | Height | Block reward (DRKW) | Total supply (DRKW) | Annual inflation |")
    print("|---|---:|---:|---:|---:|")
    for r in rows:
        print(f"| {r['label']} (≈{r['years']:.2f} yr) | {r['height']:,} | {r['reward_drkw']:.6f} | "
              f"{r['supply_drkw']:,.0f} | {r['annual_inflation_pct']:.2f} % |")


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    onset = em.tail_onset_height()
    hs, rs, ss, supply_before_onset = sweep_exponential_phase(onset, SAMPLE_STEP)
    print(f"tail onset height {onset:,} (~{onset / em.BLOCKS_PER_YEAR:.3f} yr); "
          f"supply before onset {supply_before_onset / DRKW:,.2f} DRKW; sweep {time.time() - t0:.1f}s")

    chart_fixed_point_drift(hs, rs, onset)
    hs_all, rs_all, ss_all = extend_with_tail(hs, rs, ss, onset, supply_before_onset, 200, SAMPLE_STEP)
    chart_emission_curve(hs_all, rs_all, onset)
    chart_cumulative_supply(hs_all, rs_all, ss_all, onset)
    chart_uncle_pin_split()
    chart_l1_ceiling()

    rows = write_milestones(hs, ss, onset, supply_before_onset)
    write_sampled_curve(hs_all, rs_all, ss_all)
    write_genesis_table()
    write_l1_tables()
    print_markdown_milestones(rows)
    print(f"\nwrote charts to {CHARTS.relative_to(ROOT)}/ and tables to {DATA.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
