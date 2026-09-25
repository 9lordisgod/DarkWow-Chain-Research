# `code/` — reproducible models

Small, dependency‑free Python ports of the DarkWow consensus rules that the weekly notes quote numbers from. They exist so a reader can check a figure in thirty seconds rather than build a Rust node.

| Module | Ports | From |
|---|---|---|
| `darkwow_research/emission.py` | `expected_reward()`, `fixed_pow_decay()`, the `reward` constants, exact cumulative supply | `src/sdk/src/blockchain.rs` |
| `darkwow_research/uncle_split.py` | `compute_reward()`, `split_for_uncle()`, `verify_uncle_split()` | `src/linear/src/supply_chain.rs`, `src/sdk/src/blockchain.rs` |
| `darkwow_research/genesis.py` | the nine genesis contracts: counter, crate, role, deployment position, genesis header | `src/sdk/src/crypto/contract_id.rs`, `doc/src/arch/genesis.md` |
| `darkwow_research/l1_circuits.py` | the ten Box / Purse / Promissory Note Halo2 circuits (witness slots, public inputs in `constrain_instance` order, Poseidon / EC / range‑check counts, leaf and nullifier formulas), the Book's L1 complexity ceiling and tier triage, function selectors, and the byte layout of the params‑based wire structs | `src/contract/{box,purse,promissory_note}/proof/*.zk`, `src/contract/{box,purse}/src/model/mod.rs`, `src/contract/promissory_note/src/lib.rs`, `doc/src/arch/privacy.md`, `doc/src/dev/contracts/safety.md` |
| `plot_charts.py` | regenerates `weeks/week-01/charts/*.png` and `data/*.csv` | — |
| `tests/` | pytest suite; the emission tests mirror the upstream Rust `reward_tests` module one‑for‑one, `test_l1_circuits.py` asserts every count and byte offset quoted in Week 1 §3 | — |

## Run

```bash
python3 -m pip install -r requirements.txt   # matplotlib + numpy (plots only) and pytest
python3 -m pytest                            # from this directory
python3 ../code/plot_charts.py               # from anywhere; writes relative to the repo root
```

```bash
# CLI helpers
python3 -m darkwow_research.emission 1 2 1051921 4327299     # rewards at given heights
python3 -m darkwow_research.uncle_split                       # worked pin‑split example
python3 -m darkwow_research.genesis                           # genesis registry table
python3 -m darkwow_research.l1_circuits                       # L1 circuit inventory, tiers, wire-format offsets
```

## Design notes

* **Integers only** in anything that mirrors consensus. `emission.ideal_reward()` is the one float function and exists purely to measure the fixed‑point drift.
* Ports keep the Rust names and edge‑case behaviour (saturating shifts, `checked_sub().unwrap_or(0)`, depth ≥ 64 ⇒ 0) so that a diff against upstream stays readable.
* Poseidon over Pallas is *not* re‑implemented; `genesis.py` is a registry, not a hash oracle. Use the Rust crate to recompute 32‑byte IDs.
* `l1_circuits.py` is likewise a *description* of the circuits, transcribed from the `.zk` sources and checked by counting, not a zkas parser or a prover. The wire‑format offsets follow the hand‑written `encode()` implementations in `model/mod.rs`, including the vestigial 1‑byte `proof` length prefix.
