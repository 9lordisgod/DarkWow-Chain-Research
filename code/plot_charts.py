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
weeks/week-02/charts/composition_matrix.png
weeks/week-02/charts/dao_escrow_selectors.png
weeks/week-02/charts/circuit_constraints.png
weeks/week-02/charts/attestation_authority.png
weeks/week-02/charts/tx_binding_chain.png
weeks/week-02/charts/oracle_staleness.png
weeks/week-02/charts/manifest_surface.png
weeks/week-02/charts/hazop_status.png
data/emission_milestones.csv
data/emission_curve_sampled.csv
data/genesis_contracts.csv
data/l1_circuit_inventory.csv
data/l1_wire_formats.csv
data/ocap_circuit_stats.csv
data/composition_matrix.csv
data/dao_escrow_selectors.csv
data/attestation_authority.csv
data/manifest_surface.csv
data/oracle_staleness.csv

Everything is derived from the models in ``darkwow_research`` -- the plots
are just a projection of those numbers.  Week 1's exponential phase
(~4.33 M blocks) is swept exactly, block by block; that takes ~10-20 s of
pure Python.  Week 2's charts are drawn from the transcribed registries
(circuits, selectors, manifests) and a seeded oracle simulation.
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

from darkwow_research import binding as bd  # noqa: E402
from darkwow_research import emission as em  # noqa: E402
from darkwow_research import genesis as g  # noqa: E402
from darkwow_research import l1_circuits as l1  # noqa: E402
from darkwow_research import manifest_caps as mc  # noqa: E402
from darkwow_research import ocap_primitives as oc  # noqa: E402
from darkwow_research import oracle_freshness as of  # noqa: E402
from darkwow_research import uncle_split as us  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CHARTS = ROOT / "weeks" / "week-01" / "charts"
CHARTS2 = ROOT / "weeks" / "week-02" / "charts"
DATA = ROOT / "data"

DRKW = em.BASE_UNITS_PER_DRKW
SAMPLE_STEP = 2_630  # ~0.01 year

C_DARKWOW = "#7c3aed"
C_BITCOIN = "#f59e0b"
C_TAIL = "#059669"
C_GREY = "#6b7280"
C_CANON = "#1f2937"
C_UNCLE = "#a78bfa"
C_LILAC = "#ede9fe"
C_AMBER_BG = "#fef3c7"
C_RED = "#dc2626"
C_PAPER = "#f3f4f6"


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
# Week 2 charts -- O-Cap governance primitives
# --------------------------------------------------------------------------------------

from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch  # noqa: E402

FATE_COLOUR = {oc.Fate.KEPT: C_TAIL, oc.Fate.REWIRED: C_DARKWOW, oc.Fate.RETIRED: C_GREY}


def _short(name: str) -> str:
    return name.replace("promissory_note", "PN").replace("_", " ")


def chart_composition_matrix():
    """Which of the 32 contracts reference which primitive's *_CONTRACT_ID, and from where."""
    rows = list(oc.PRIMITIVE_ROWS)
    cols = list(oc.ALL_CONTRACTS)
    m = np.array(oc.composition_matrix(rows, cols))
    cmap = ListedColormap([C_PAPER, C_UNCLE, C_DARKWOW])

    fig, ax = plt.subplots(figsize=(14, 4.6))
    ax.imshow(m, cmap=cmap, vmin=0, vmax=2, aspect="auto")
    ax.set_xticks(range(len(cols)), [_short(c) for c in cols], rotation=90, fontsize=8)
    ax.set_yticks(range(len(rows)), [_short(r) for r in rows], fontsize=9)
    ax.set_xticks(np.arange(-0.5, len(cols)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(rows)), minor=True)
    ax.grid(which="minor", color="white", lw=1.2)
    ax.tick_params(which="minor", length=0)
    for (p, c) in oc.COMMENT_ONLY_REFS:
        ax.text(cols.index(c), rows.index(p), "✱", ha="center", va="center", fontsize=9, color="white")
    for name, colour in (("dao_escrow", C_BITCOIN), ("escrow", C_TAIL)):
        j = cols.index(name)
        ax.add_patch(FancyBboxPatch((j - 0.5, -0.5), 1, len(rows), boxstyle="square,pad=0", fill=False,
                                    ec=colour, lw=2.2))
    ax.text(cols.index("dao_escrow"), -0.9, "BUG-01's subject", ha="center", fontsize=8, color=C_BITCOIN)
    ax.text(cols.index("escrow"), -0.9, "the real Box+Purse composer", ha="center", fontsize=8, color=C_TAIL)
    ax.set_title("Composition matrix @ d775e37c — who references whose contract id "
                 "(✱ = mentioned only in a comment)", pad=40)
    ax.legend(handles=[Patch(color=C_DARKWOW, label="read from entrypoint.rs (child-call check)"),
                       Patch(color=C_UNCLE, label="constant in lib.rs only, never read"),
                       Patch(color=C_PAPER, label="no reference")],
              loc="lower center", bbox_to_anchor=(0.5, 1.09), ncol=3, fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS2 / "composition_matrix.png", dpi=160)
    plt.close(fig)


def chart_dao_escrow_selectors():
    """The Book's seventeen dao_escrow selectors and what became of each."""
    sels = oc.BOOK_DAO_ESCROW
    ncol = 6
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 4.9), gridspec_kw={"width_ratios": [4.2, 1]})
    for i, s in enumerate(sels):
        r, c = divmod(i, ncol)
        x, y = c * 1.0, -r * 1.0
        ax.add_patch(FancyBboxPatch((x + 0.04, y + 0.06), 0.92, 0.88, boxstyle="round,pad=0.01,rounding_size=0.06",
                                    fc=FATE_COLOUR[s.fate], ec="white", lw=1.5))
        ax.text(x + 0.5, y + 0.74, f"0x{s.code:02X}", ha="center", va="center", fontsize=9, color="white",
                fontweight="bold")
        name = s.name.replace("V1", "")
        if len(name) > 18:
            name = name.replace("Capability", "Cap.").replace("Requirement", "Req.")
        ax.text(x + 0.5, y + 0.50, name, ha="center", va="center", fontsize=7.6, color="white")
        ax.text(x + 0.5, y + 0.25, s.book_capability.replace("via Box", "(Box)"), ha="center", va="center",
                fontsize=6.6, color="white", style="italic")
    ax.set_xlim(0, ncol)
    ax.set_ylim(-2.0, 1.0)
    ax.axis("off")
    ax.set_title("Book pp. 1145–1146: 17 selectors, capability column as written", fontsize=10.5, loc="left")

    r = oc.selector_retirement()
    fates = [oc.Fate.KEPT, oc.Fate.REWIRED, oc.Fate.RETIRED]
    counts = [len(r[f]) for f in fates]
    bottom = 0
    for f, n in zip(fates, counts):
        ax2.bar(0, n, bottom=bottom, color=FATE_COLOUR[f], width=0.6)
        ax2.text(0, bottom + n / 2, f"{f.value}\n{n}", ha="center", va="center", color="white", fontsize=9)
        bottom += n
    ax2.set_xlim(-0.6, 0.6)
    ax2.set_xticks([])
    ax2.set_ylabel("selectors")
    ax2.set_title(f"shipped: {len(oc.DAO_ESCROW.selectors)} of 17", fontsize=10.5)
    ax2.spines[["top", "right"]].set_visible(False)
    fig.suptitle("dao_escrow: the Book's O-Cap design vs the contract at d775e37c "
                 "(green kept · purple kept-but-rewired to MultiSig/proofs · grey retired)", fontsize=11)
    fig.tight_layout()
    fig.savefig(CHARTS2 / "dao_escrow_selectors.png", dpi=160)
    plt.close(fig)


def chart_circuit_constraints():
    """constrain_instance vs constrain_equal for all 41 circuits in the nine contracts."""
    cs = list(oc.CIRCUITS)
    x = np.arange(len(cs))
    ci = [c.constrain_instance for c in cs]
    ce = [c.constrain_equal for c in cs]
    tx_only = [c.only_tx_pair_is_public for c in cs]

    fig, ax = plt.subplots(figsize=(16, 5.2))
    width = 0.42
    ax.bar(x - width / 2, ci, width, color=[C_BITCOIN if t else C_DARKWOW for t in tx_only],
           label="constrain_instance (public inputs)")
    ax.bar(x + width / 2, ce, width, color=C_UNCLE, label="constrain_equal (in-circuit equalities)")
    ax.axhline(2, color=C_BITCOIN, ls="--", lw=1, label="2 public inputs = only (tx_binding, tx_nonce)")
    for i, c in enumerate(cs):
        if c.k != 11:
            ax.text(i, max(ci[i], ce[i]) + 0.35, f"k={c.k}", ha="center", fontsize=7.5, color=C_CANON)
    # contract group separators and labels
    bounds = []
    start = 0
    for i in range(1, len(cs) + 1):
        if i == len(cs) or cs[i].contract != cs[start].contract:
            bounds.append((start, i - 1, cs[start].contract))
            start = i
    for a, b, name in bounds:
        if a > 0:
            ax.axvline(a - 0.5, color=C_GREY, lw=0.6, alpha=0.6)
        ax.text((a + b) / 2, 13.6, _short(name), ha="center", fontsize=8.5, color=C_CANON, fontweight="bold")
    ax.set_xticks(x, [c.circuit for c in cs], rotation=90, fontsize=7.5)
    ax.set_ylim(0, 14.5)
    ax.set_ylabel("count per .zk file")
    n_tx = sum(tx_only)
    ax.set_title(f"Constraint profile of the 41 circuits — amber: the {n_tx} proofs whose only public inputs are "
                 "(tx_binding, tx_nonce) — eight in attestation, one in dao_escrow", pad=10)
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.92), fontsize=8.6, frameon=True, framealpha=0.95,
              edgecolor="#e5e7eb")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS2 / "circuit_constraints.png", dpi=160)
    plt.close(fig)


def chart_attestation_authority():
    """Fourteen attestation selectors: who they speak for and what binds that party."""
    ops = bd.ATTESTATION_OPS
    cols = ["circuit", "public inputs", "actor", "actor binding", "proof replayable", "writes state"]
    bind_colour = {bd.Bound.PROOF: C_TAIL, bd.Bound.STATE: C_BITCOIN, bd.Bound.NONE: C_RED}

    fig, ax = plt.subplots(figsize=(12.5, 6.4))
    ax.set_xlim(0, len(cols))
    ax.set_ylim(-len(ops), 0)
    for i, op in enumerate(ops):
        y = -i - 1
        writes = op.actor != "anyone" and op.name not in ("CheckAttestationV1", "ValidateClaimV1")
        cells = [
            (op.circuit or "—", C_LILAC if op.circuit else C_PAPER, C_CANON),
            (str(len(op.public_inputs)) if op.circuit else "—",
             C_AMBER_BG if len(op.public_inputs) == 2 else (C_LILAC if op.circuit else C_PAPER), C_CANON),
            (op.actor, C_PAPER, C_CANON),
            (op.actor_binding.value.upper(), bind_colour[op.actor_binding], "white"),
            ("yes" if op.replayable_proof else ("n/a" if not op.circuit else "no"),
             C_AMBER_BG if op.replayable_proof else C_PAPER, C_CANON),
            ("yes" if writes else "read-only", C_LILAC if writes else C_PAPER, C_CANON),
        ]
        for j, (txt, bg, fg) in enumerate(cells):
            ax.add_patch(FancyBboxPatch((j + 0.02, y + 0.06), 0.96, 0.88, boxstyle="square,pad=0", fc=bg, ec="white"))
            ax.text(j + 0.5, y + 0.5, txt, ha="center", va="center", fontsize=8.2, color=fg)
        ax.text(-0.08, y + 0.5, f"0x{op.code:02X} {op.name}", ha="right", va="center", fontsize=8.6, color=C_CANON)
    ax.set_xticks([j + 0.5 for j in range(len(cols))], cols, fontsize=9)
    ax.xaxis.tick_top()
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    s = bd.authority_summary()
    ax.set_title(f"Attestation authority @ d775e37c — {s['with_circuit']}/{s['selectors']} selectors carry a proof, "
                 f"{s['publish_only_tx_pair']} publish only the tx pair, {s['actor_bound_by_proof']} binds its actor",
                 pad=28, fontsize=11)
    ax.legend(handles=[Patch(color=C_TAIL, label="PROOF: a secret is proven in-circuit"),
                       Patch(color=C_BITCOIN, label="STATE: wire field compared to a stored *public* value"),
                       Patch(color=C_RED, label="NONE: wire field taken at face value")],
              loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=3, fontsize=8.5, frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS2 / "attestation_authority.png", dpi=160)
    plt.close(fig)


def chart_tx_binding_chain():
    """The four stages the tx_binding design needs and the one that does not exist."""
    stages = bd.TX_BINDING_CHAIN
    fig, ax = plt.subplots(figsize=(14, 4.2))
    ax.set_xlim(0, len(stages) * 3.4)
    ax.set_ylim(0, 3)
    for i, st in enumerate(stages):
        x = i * 3.4 + 0.2
        ok = st.implemented
        ax.add_patch(FancyBboxPatch((x, 1.15), 2.9, 1.5, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    fc=C_DARKWOW if ok else C_AMBER_BG, ec="#4c1d95" if ok else C_BITCOIN,
                                    lw=1.6, ls="-" if ok else "--"))
        ax.text(x + 1.45, 2.38, f"stage {st.n} · {st.who}", ha="center", va="center", fontsize=9.5,
                color="white" if ok else C_CANON, fontweight="bold")
        claim = st.claim.replace("poseidon_hash(3, tx_commitment, tx_nonce)", "H(3, tx_commitment, tx_nonce)")
        ax.text(x + 1.45, 1.86, _wrap(claim, 44), ha="center", va="center", fontsize=7.6,
                color="white" if ok else C_CANON)
        where = st.implemented_in or "not found anywhere in bin/, src/linear, src/runtime, src/zk"
        ax.text(x + 1.45, 0.75, _wrap(where, 48), ha="center", va="center", fontsize=7.2, color=C_GREY)
        ax.text(x + 1.45, 0.25, _wrap(st.effect, 52), ha="center", va="center", fontsize=7.2,
                color=C_TAIL if ok else C_RED, style="italic")
        if i < len(stages) - 1:
            ax.add_patch(FancyArrowPatch((x + 2.95, 1.9), (x + 3.4 + 0.15, 1.9), arrowstyle="-|>",
                                         mutation_scale=16, color=C_GREY, lw=1.4))
    ax.axis("off")
    st = bd.tx_binding_chain_status()
    ax.set_title(f"tx_binding verification chain — {st['implemented']} of {st['stages']} stages exist; "
                 f"no host import exposes tx_commitment (checked {len(bd.HOST_IMPORTS)} imports)", fontsize=11)
    src = bd.tx_binding_source_counts()
    fig.text(0.5, 0.015,
             f"what stage 2 actually publishes, per contract (32): {src['constant']} compute the constant "
             f"H(3, 0, 0) · {src['echo']} echo params.tx_binding from the wire · {src['mixed']} mixed · "
             f"{src['no circuits']} has no circuits",
             ha="center", fontsize=8.8, color=C_CANON)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(CHARTS2 / "tx_binding_chain.png", dpi=160)
    plt.close(fig)


def _wrap(text: str, width: int) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return "\n".join(lines)


def chart_oracle_staleness(rows):
    """Left: what a max_age window buys and costs.  Right: the age a reader actually sees."""
    hist = of.age_histogram()
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 4.8), gridspec_kw={"width_ratios": [1.15, 1]})

    finite = [r for r in rows if r.max_age is not None]
    xs = [r.max_age for r in finite]
    ax.plot(xs, [100 * r.stale_rate for r in finite], "o-", color=C_RED, lw=1.8, label="stale value accepted (operator withholding)")
    ax.plot(xs, [100 * r.false_reject_rate for r in finite], "s-", color=C_DARKWOW, lw=1.8,
            label="honest value rejected (cadence slower than window)")
    none = next(r for r in rows if r.max_age is None)
    ax.axhline(100 * none.stale_rate, color=C_RED, ls=":", lw=1.2)
    ax.text(xs[-1], 100 * none.stale_rate + 1.2, f"no window (today): {100 * none.stale_rate:.1f} % stale reads",
            ha="right", fontsize=8.5, color=C_RED)
    ax.axvspan(0, 5, color=C_AMBER_BG, alpha=0.8, lw=0)
    ax.text(2.5, 92, "brief's\n'< 5 blocks'", ha="center", fontsize=8, color=C_BITCOIN)
    ax.axvline(10, color=C_GREY, ls="--", lw=1)
    ax.text(10.4, 92, "honest push cadence\n(mean 10 blocks)", fontsize=8, color=C_GREY)
    ax.set_xscale("log")
    ax.set_xlabel("max_age window (blocks, log scale)")
    ax.set_ylabel("% of consumer reads")
    ax.set_ylim(0, 100)
    ax.set_title("A freshness window is a liveness/safety dial — nobody turns it today")
    ax.legend(loc="center right", fontsize=8.5, frameon=False)
    ax.grid(alpha=0.25, which="both")

    ages = sorted(hist)
    total = sum(hist.values())
    cols = [C_DARKWOW if a <= 10 else (C_BITCOIN if a <= 40 else C_RED) for a in ages]
    ax2.bar(ages, [100 * hist[a] / total for a in ages], width=1.0, color=cols)
    ax2.set_xlim(-0.5, 60)
    ax2.set_xlabel("age of oracle.value at read time (blocks since updated_at)")
    ax2.set_ylabel("% of reads")
    ax2.set_title("The only freshness datum is updated_at — and no contract reads it")
    ax2.legend(handles=[Patch(color=C_DARKWOW, label="≤ 10 blocks (within cadence)"),
                        Patch(color=C_BITCOIN, label="11–40 blocks (withholding episode)"),
                        Patch(color=C_RED, label="> 40 blocks")], fontsize=8.5, frameon=False)
    ax2.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS2 / "oracle_staleness.png", dpi=160)
    plt.close(fig)


def chart_manifest_surface():
    """Thirty-two manifests: how much they declare, which ones are typed, and name reuse."""
    ms = sorted(mc.MANIFESTS, key=lambda m: (-m.functions, m.contract))
    x = np.arange(len(ms))
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15, 5), gridspec_kw={"width_ratios": [3.2, 1]})
    ax.bar(x, [m.requires_proof for m in ms], color=C_DARKWOW, label="functions with requires_proof")
    ax.bar(x, [m.functions - m.requires_proof for m in ms], bottom=[m.requires_proof for m in ms],
           color=C_UNCLE, label="functions without a proof")
    ax.plot(x, [m.capabilities for m in ms], "o", color=C_BITCOIN, ms=5, label="[[capabilities]] entries")
    for i, m in enumerate(ms):
        if m.typed:
            ax.text(i, m.functions + 0.5, "★", ha="center", fontsize=10, color=C_TAIL)
        if m.contract in oc.CONTRACTS and oc.CONTRACTS[m.contract].genesis_counter is not None:
            ax.get_xticklabels()
    ax.set_xticks(x, [_short(m.contract) for m in ms], rotation=90, fontsize=8)
    typed, total = mc.typed_coverage()
    ax.set_ylabel("count")
    ax.set_title(f"manifest.toml surface — ★ = declares typed primitives/note_schema ({typed}/{total}; "
                 f"all genesis contracts except identity)")
    ax.legend(loc="upper right", fontsize=8.5, frameon=False)
    ax.grid(axis="y", alpha=0.25)

    names = sorted(mc.SHARED_CAPABILITY_NAMES.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ax2.barh([n for n, _ in names][::-1], [len(v) for _, v in names][::-1], color=C_BITCOIN)
    for i, (n, v) in enumerate(names[::-1]):
        ax2.text(len(v) + 0.08, i, ", ".join(_short(c) for c in v), va="center", fontsize=7.2, color=C_CANON)
    ax2.set_xlim(0, 9.5)
    ax2.set_xlabel("manifests using the same capability name")
    ax2.set_title(f"{mc.TOTAL_CAPABILITY_DECLARATIONS} declarations, {mc.DISTINCT_CAPABILITY_NAMES} distinct names",
                  fontsize=10)
    ax2.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(CHARTS2 / "manifest_surface.png", dpi=160)
    plt.close(fig)


def chart_hazop_status():
    """The project's own verification register by status."""
    resolved = {"CLOSED", "SATISFIED", "FIXED", "MECHANIZED", "DEFINITIONAL"}
    items = sorted(bd.HAZOP_STATUS.items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(10, 4.4))
    colours = [C_TAIL if k in resolved else (C_RED if k == "FAILS" else C_BITCOIN) for k, _ in items]
    ax.barh([k for k, _ in items][::-1], [v for _, v in items][::-1], color=colours[::-1])
    for i, (k, v) in enumerate(items[::-1]):
        ax.text(v + 0.6, i, str(v), va="center", fontsize=9, color=C_CANON)
    for i, (k, v) in enumerate(items[::-1]):
        if k == "FAILS":
            ax.text(v + 4, i, "  ".join(i_ for i_, _ in bd.HAZOP_FAILS), va="center", fontsize=8, color=C_RED)
    total = sum(bd.HAZOP_STATUS.values())
    ax.set_xlabel("rows in doc/src/arch/verification-hazop.md")
    ax.set_title(f"Verification register @ d775e37c — {total} obligations, "
                 f"{100 * bd.hazop_resolved_share():.0f} % resolved (green), 3 recorded as FAILS", fontsize=11)
    ax.legend(handles=[Patch(color=C_TAIL, label="resolved (closed / satisfied / fixed / mechanized / definitional)"),
                       Patch(color=C_BITCOIN, label="open / partly / accepted-with-reason / restated"),
                       Patch(color=C_RED, label="FAILS")], loc="lower right", fontsize=8.5, frameon=False)
    ax.grid(axis="x", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(CHARTS2 / "hazop_status.png", dpi=160)
    plt.close(fig)


# --------------------------------------------------------------------------------------
# Week 2 data tables
# --------------------------------------------------------------------------------------


def write_week2_tables():
    with (DATA / "ocap_circuit_stats.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["contract", "circuit", "k", "witnesses", "constrain_instance", "constrain_equal", "poseidon",
                    "ec_mul", "merkle_root", "range_checks", "statements", "only_tx_pair_public", "binds_a_secret",
                    "public_inputs_in_order"])
        for c in oc.CIRCUITS:
            w.writerow([c.contract, c.circuit, c.k, c.witnesses, c.constrain_instance, c.constrain_equal, c.poseidon,
                        c.ec_mul, c.merkle_root, c.range_checks, c.statements, c.only_tx_pair_is_public,
                        c.binds_a_secret, " ".join(c.public_inputs)])
    with (DATA / "composition_matrix.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["primitive", *oc.ALL_CONTRACTS])
        for p, row in zip(oc.PRIMITIVE_ROWS, oc.composition_matrix()):
            w.writerow([p, *row])
    with (DATA / "dao_escrow_selectors.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "book_name", "book_capability", "fate", "shipped", "note"])
        shipped = oc.shipped_codes()
        for s in oc.BOOK_DAO_ESCROW:
            w.writerow([f"0x{s.code:02x}", s.name, s.book_capability, s.fate.value, s.code in shipped, s.note])
    with (DATA / "attestation_authority.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "name", "circuit", "public_inputs", "actor", "actor_binding", "replayable_proof",
                    "state_checks", "note"])
        for op in bd.ATTESTATION_OPS:
            w.writerow([f"0x{op.code:02x}", op.name, op.circuit or "", " ".join(op.public_inputs), op.actor,
                        op.actor_binding.value, op.replayable_proof, "; ".join(op.state_checks), op.note])
    with (DATA / "manifest_surface.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["contract", "functions", "requires_proof", "capabilities", "actions", "parameters", "circuits",
                    "trees", "typed_capability_fields", "trust_tier_shown", "capability_names"])
        for m in mc.MANIFESTS:
            w.writerow([m.contract, m.functions, m.requires_proof, m.capabilities, m.actions, m.parameters,
                        m.circuits, m.trees, m.typed, mc.resolve_show_trust(m.contract).value, " ".join(m.cap_names)])


def write_oracle_table(rows):
    with (DATA / "oracle_staleness.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["max_age_blocks", "reads", "accepted", "stale_accepted", "false_rejected", "stale_rate",
                    "false_reject_rate"])
        for r in rows:
            w.writerow(["none" if r.max_age is None else r.max_age, r.reads, r.accepted, r.stale_accepted,
                        r.false_rejected, f"{r.stale_rate:.4f}", f"{r.false_reject_rate:.4f}"])


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
    CHARTS2.mkdir(parents=True, exist_ok=True)
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

    # week 2
    chart_composition_matrix()
    chart_dao_escrow_selectors()
    chart_circuit_constraints()
    chart_attestation_authority()
    chart_tx_binding_chain()
    staleness = of.tradeoff()
    chart_oracle_staleness(staleness)
    chart_manifest_surface()
    chart_hazop_status()
    write_week2_tables()
    write_oracle_table(staleness)
    print(f"\nwrote charts to {CHARTS.relative_to(ROOT)}/, {CHARTS2.relative_to(ROOT)}/ "
          f"and tables to {DATA.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
