# `code/` — reproducible models

Small, dependency‑free Python ports of the DarkWow consensus rules that the weekly notes quote numbers from. They exist so a reader can check a figure in thirty seconds rather than build a Rust node.

| Module | Ports | From |
|---|---|---|
| `darkwow_research/emission.py` | `expected_reward()`, `fixed_pow_decay()`, the `reward` constants, exact cumulative supply | `src/sdk/src/blockchain.rs` |
| `darkwow_research/uncle_split.py` | `compute_reward()`, `split_for_uncle()`, `verify_uncle_split()` | `src/linear/src/supply_chain.rs`, `src/sdk/src/blockchain.rs` |
| `darkwow_research/genesis.py` | the nine genesis contracts: counter, crate, role, deployment position, genesis header | `src/sdk/src/crypto/contract_id.rs`, `doc/src/arch/genesis.md` |
| `darkwow_research/l1_circuits.py` | the ten Box / Purse / Promissory Note Halo2 circuits (witness slots, public inputs in `constrain_instance` order, Poseidon / EC / range‑check counts, leaf and nullifier formulas), the Book's L1 complexity ceiling and tier triage, function selectors, and the byte layout of the params‑based wire structs | `src/contract/{box,purse,promissory_note}/proof/*.zk`, `src/contract/{box,purse}/src/model/mod.rs`, `src/contract/promissory_note/src/lib.rs`, `doc/src/arch/privacy.md`, `doc/src/dev/contracts/safety.md` |
| `darkwow_research/ocap_primitives.py` | the six O‑Cap governance primitives (Purse, Box, Identity, MultiSig, Oracle, Attestation) plus Promissory Note, `dao_escrow` and `escrow`: selectors, the 41 Halo2 circuits with their `constrain_instance` lists, leaf formulas at `d775e37c`, the Book‑era 17‑selector `dao_escrow` table vs. the shipped 10 (kept / rewired / retired), and the entrypoint‑vs‑`lib.rs` composition matrix across all 32 contracts | `src/contract/*/src/lib.rs`, `manifest.toml`, `proof/*.zk`, `entrypoint*.rs`; Book pp. 1142–1172 |
| `darkwow_research/call_tree.py` | DarkTree DFS post‑order flattening and reconciliation, `MIN/MAX_TX_CALLS`, a checkpoint/revert executor with per‑call handlers, and transcriptions of `escrow::ClaimV1` and the Book‑era `dao_escrow::TreasurySpendV1` child checks (slot, selector, contract id, self‑asserted params) | `src/sdk/src/dark_tree.rs`, `src/tx/mod.rs`, `src/linear/src/{execution,zk_verifier}.rs`, `src/contract/escrow/src/entrypoint.rs` |
| `darkwow_research/binding.py` | the attestation authority table (14 selectors: actor, how bound, public‑input count, replayable), the forgery path and the secrets it needs, the four‑stage `tx_binding` chain with its missing node stage, the 25 host imports, and the per‑contract source of the published `tx_binding` (19 constant · 11 echo · 1 mixed · 1 none) | `src/contract/attestation/src/entrypoint.rs`, `proof/*.zk`, `src/runtime/import/*.rs`, every `entrypoint*.rs`, `doc/src/contract/tx-commitment.md` |
| `darkwow_research/oracle_freshness.py` | `OracleRecord` / `push()` (last‑write‑wins, value nullifier), `ReadPolicy(max_age)`, and a seeded withholding‑operator simulation returning stale‑accept vs. false‑reject rates for twelve windows | `src/contract/oracle/src/entrypoint.rs`, `doc/src/contract/oracle.md`; Book p. 979 |
| `darkwow_research/manifest_caps.py` | manifest wire prefix `0x4D`, trust tiers and the three trust layers with their implementation status, a name‑aliasing checker (`alias()`), what the chain dispatches on vs. what the manifest controls, and totals over the 32 shipped manifests (functions, proofs, capabilities, typed coverage, shared names) | `src/sdk/src/manifest.rs`, `bin/dww/src/{dispatch,manifest_resolver}.rs`, `src/contract/*/manifest.toml`, `doc/src/arch/manifest.md` |
| `plot_charts.py` | regenerates `weeks/week-0{1,2}/charts/*.png` and `data/*.csv` | — |
| `tests/` | pytest suite (158 tests); the emission tests mirror the upstream Rust `reward_tests` module one‑for‑one, `test_l1_circuits.py` asserts every count and byte offset quoted in Week 1 §3, and `test_{ocap_primitives,call_tree,binding,oracle_freshness,manifest_caps}.py` pin every number and verdict quoted in Week 2 | — |

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
python3 -m darkwow_research.ocap_primitives                   # six primitives, dao_escrow Book-vs-code, composition matrix
python3 -m darkwow_research.call_tree                         # post-order traces: escrow ClaimV1, swapped siblings, lying box wire
python3 -m darkwow_research.binding                           # attestation authority, forgery path, tx_binding chain and sources
python3 -m darkwow_research.oracle_freshness                  # staleness vs false-reject table for twelve windows
python3 -m darkwow_research.manifest_caps                     # manifest totals, typed coverage, alias demo, trust layers
```

## Design notes

* **Integers only** in anything that mirrors consensus. `emission.ideal_reward()` is the one float function and exists purely to measure the fixed‑point drift.
* Ports keep the Rust names and edge‑case behaviour (saturating shifts, `checked_sub().unwrap_or(0)`, depth ≥ 64 ⇒ 0) so that a diff against upstream stays readable.
* Poseidon over Pallas is *not* re‑implemented; `genesis.py` is a registry, not a hash oracle. Use the Rust crate to recompute 32‑byte IDs.
* The Week 2 modules follow the same rule: `ocap_primitives.py`, `binding.py` and `manifest_caps.py` are registries checked by counting; `call_tree.py` and `oracle_freshness.py` are executable models of the *rules* (post‑order, slot checks, checkpoint/revert, last‑write‑wins) with no cryptography — a nullifier is a string, a proof is the set of fields the real circuit would publish.
* `l1_circuits.py` is likewise a *description* of the circuits, transcribed from the `.zk` sources and checked by counting, not a zkas parser or a prover. The wire‑format offsets follow the hand‑written `encode()` implementations in `model/mod.rs`, including the vestigial 1‑byte `proof` length prefix.
