# DarkWow Chain Research

Weekly, source‑verified research notes on **[DarkWow](https://github.com/PatrickMockridge/DarkWow)** — Patrick Mockridge's privacy‑first fork of DarkFi built around composable Object‑Capability (O‑Cap) primitives, Uncle Merkle proof‑of‑work consensus, a zero‑premine emission schedule and per‑block Pedersen supply audits.

Each week takes one slice of the chain, reads the primary sources (*The DarkWow Book* and the `linear-master` source tree), and writes it up with diagrams, tables and small programs that reproduce every number quoted. The goal is a reference that a newcomer can trust because every claim points at the line of code or spec page it came from.

> **Status:** independent research. Not affiliated with or endorsed by the DarkWow project. DarkWow itself is unaudited software (*"use at your own risk"* per its README); nothing here is investment or security advice.

## Weekly index

| Week | Dates | Topic | Artifacts |
|:---:|---|---|---|
| [**01**](weeks/week-01/README.md) | 2026‑09‑21 → 09‑27 | **Genesis block & architecture** — the nine genesis contracts, deterministic `ContractId`s, why only two are consensus‑critical, and the five structural breaks from DarkFi (O‑Cap vs DAO, the Money split, zero premine + emission, Uncle Merkle vs overlay‑DAG, ZK predicates vs ACLs) | 8 diagrams · 4 charts · 3 models · 26 tests · 6 findings |
| 02 | 2026‑09‑28 → 10‑04 | *planned* — verify the DarkFi side of the comparison at the fork point; regenerate all nine genesis IDs | |

## What's in the repository

```
.
├── README.md                     ← you are here
├── weeks/
│   └── week-01/
│       ├── README.md             ← the Week 1 write‑up (start here)
│       └── charts/*.png          ← generated figures embedded in the write‑up
├── code/
│   ├── darkwow_research/         ← pure‑Python ports of consensus rules
│   │   ├── emission.py           ←   expected_reward() / fixed_pow_decay(), integer‑exact
│   │   ├── uncle_split.py        ←   compute_reward() pin split + mass‑balance invariant
│   │   └── genesis.py            ←   the nine genesis contracts, counters, crates, roles
│   ├── plot_charts.py            ← regenerates every chart and data table
│   └── tests/                    ← pytest suite mirroring the upstream Rust unit tests
├── data/                         ← CSV outputs (emission milestones, sampled curve, genesis table)
└── sources/                      ← primary‑source snapshot + provenance (The DarkWow Book, PDF)
```

## Quick reference — numbers you will see quoted

All re‑derived from `src/sdk/src/blockchain.rs` and `src/sdk/src/crypto/contract_id.rs`; see [Week 1 §2.4](weeks/week-01/README.md#24-zero-premine-vs-insider-allocation--and-the-emission-that-replaces-it) for derivations.

| Parameter | Value |
|---|---|
| Block time | 120 s (262,980 blocks / year) |
| Proof of work | RandomX; Monero merge‑mining supported |
| Genesis | height 1, `timestamp = 0`, `target = u32::MAX`, 1 coinbase + 9 deployment txs |
| Genesis `ContractId` | `poseidon_hash([42, 0, counter])`, counters 2 … 10 |
| Consensus‑critical contracts | Deployooor (2), NativeToken (4) — the other seven are ecosystem primitives |
| Initial reward R₀ | 1,383,764,049 base units ≈ 13.8376 DRKW (1 DRKW = 10⁸) |
| Decay | continuous, half‑life 1,051,920 blocks ≈ 4 years, no step halvings |
| Tail emission | 79,853,981 base units ≈ 0.7985 DRKW / block, forever (≈ 210 k DRKW / yr) |
| Tail onset | height 4,327,299 ≈ 16.45 years; supply then ≈ 19.78 M DRKW |
| 21 M DRKW | a *reference* supply, crossed ≈ year 22 — **not** a hard cap |
| Uncle pins | `base / 2^depth`, depth 1 … 6; subtractive, `canonical + Σ pins == base` |

## Reproduce

```bash
python3 -m pip install -r code/requirements.txt
( cd code && python3 -m pytest )      # 26 tests
python3 code/plot_charts.py           # ~20 s; rewrites weeks/*/charts and data/
```

Python ≥ 3.10; the models themselves have no dependencies beyond the standard library — only the plotting script needs matplotlib/numpy.

## Sources

* **Code:** [PatrickMockridge/DarkWow](https://github.com/PatrickMockridge/DarkWow) (GitHub mirror of [codeberg.org/PatrickM123/darkwow](https://codeberg.org/PatrickM123/darkwow)), branch `linear-master`, AGPL‑3.0‑only. Short excerpts are quoted in the notes for commentary, with file paths.
* **Spec:** *The DarkWow Book*, the project's mdbook documentation, snapshotted as a PDF on 2026‑09‑03 — [`sources/`](sources/README.md) has the file, its checksum and how to rebuild a fresh copy from `doc/`.
* **Week 1 original notes:** [Google Doc](https://docs.google.com/document/d/1G5zCkHBF2VW92Cn9dtDrSdRFjtlWLs5aJD4qQeSaiHM/edit?usp=sharing).

## Conventions

* One directory per week: `weeks/week-NN/README.md` plus its `charts/`. Notes are written to stand alone.
* Every quantitative claim carries a tag — 📖 *Book*, 🦀 *Source*, 🧪 *Re‑derived* — and re‑derived claims have a test.
* Discrepancies between spec prose and code are recorded in each week's *Findings* section rather than silently corrected.
* Corrections and questions are welcome via issues.
