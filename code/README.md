# `code/` — reproducible models

Small, dependency‑free Python ports of the DarkWow consensus rules that the weekly notes quote numbers from. They exist so a reader can check a figure in thirty seconds rather than build a Rust node.

| Module | Ports | From |
|---|---|---|
| `darkwow_research/emission.py` | `expected_reward()`, `fixed_pow_decay()`, the `reward` constants, exact cumulative supply | `src/sdk/src/blockchain.rs` |
| `darkwow_research/uncle_split.py` | `compute_reward()`, `split_for_uncle()`, `verify_uncle_split()` | `src/linear/src/supply_chain.rs`, `src/sdk/src/blockchain.rs` |
| `darkwow_research/genesis.py` | the nine genesis contracts: counter, crate, role, deployment position, genesis header | `src/sdk/src/crypto/contract_id.rs`, `doc/src/arch/genesis.md` |
| `plot_charts.py` | regenerates `weeks/week-01/charts/*.png` and `data/*.csv` | — |
| `tests/` | pytest suite; the emission tests mirror the upstream Rust `reward_tests` module one‑for‑one | — |

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
```

## Design notes

* **Integers only** in anything that mirrors consensus. `emission.ideal_reward()` is the one float function and exists purely to measure the fixed‑point drift.
* Ports keep the Rust names and edge‑case behaviour (saturating shifts, `checked_sub().unwrap_or(0)`, depth ≥ 64 ⇒ 0) so that a diff against upstream stays readable.
* Poseidon over Pallas is *not* re‑implemented; `genesis.py` is a registry, not a hash oracle. Use the Rust crate to recompute 32‑byte IDs.
