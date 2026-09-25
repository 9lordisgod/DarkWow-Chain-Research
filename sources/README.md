# Sources

Primary material the weekly notes are checked against.

## The DarkWow Book (PDF snapshot)

| | |
|---|---|
| File | [`The-DarkWow-Book-2026-09-03.pdf`](The-DarkWow-Book-2026-09-03.pdf) |
| What it is | The complete DarkWow mdbook documentation (`doc/` in the source tree — architecture, consensus & coinbase spec, contract catalogue, philosophy, verification register) printed to PDF |
| Pages | 2,014 |
| Produced | 2026‑09‑03 19:49 UTC (PDF metadata: producer `Skia/PDF m152`, i.e. a Chromium print‑to‑PDF of the served book) |
| Size | 45.2 MB |
| SHA‑256 | `2c80dc5c71c88f81f5f3bc8e0364ec04d68281d859c5d115df8f4d5b779faae6` |
| Describes | branch `linear-master` (Uncle Merkle consensus, RandomX PoW); states that the legacy overlay‑DAG (`src/validator/`) has been removed |

The snapshot is kept in‑tree deliberately: the research cites page numbers, and the live docs move with every commit. Verify the file with

```bash
shasum -a 256 sources/The-DarkWow-Book-2026-09-03.pdf
```

To build a current copy yourself:

```bash
git clone https://github.com/PatrickMockridge/DarkWow && cd DarkWow/doc
cargo install mdbook        # plus the preprocessors listed in book.toml; see doc/README.md
mdbook serve                # `make` instead for the full build including rustdoc
# then print the served book to PDF from a browser
```

Useful page ranges in this snapshot (as extracted with `pypdf`): contract deployment pipeline & genesis table pp. 123–125; Uncle Merkle overview pp. 337–339; uncle reward split & formal spec pp. 366–368; consensus & coinbase — emission constants pp. 645–652; genesis specification pp. 903–907; history of the fork / philosophy pp. 1921–1923; L1 privacy model, consume+create and the complexity ceiling pp. 195–197 (triage table pp. 1491–1492); Promissory Note chapter pp. 918–963 (Conder tokens and the three problems 918–919, receipt / `is_notequal` 931, issuer responsibility 921, selectors 959 and 962, residual risks 963); Purse chapter pp. 988–990; Box chapter pp. 992–994; transaction binding pp. 1249–1253; hardening heuristics (RC8) p. 1484; contract standards — `Encode ZK Inputs Only`, Schnorr prohibition p. 892.

## DarkWow source code

* GitHub mirror: <https://github.com/PatrickMockridge/DarkWow> · canonical: <https://codeberg.org/PatrickM123/darkwow>
* Branch: `linear-master` (development branch per the README)
* Licence: AGPL‑3.0‑only. Short excerpts are reproduced in the notes for commentary and are attributed by path.

Files cited most often:

| Path | Used for |
|---|---|
| `src/sdk/src/crypto/contract_id.rs` | genesis `ContractId` constants and derivation rule |
| `src/sdk/src/blockchain.rs` | `reward` constants, `expected_reward()`, `fixed_pow_decay()`, `BlockReward::split_for_uncle()` |
| `src/linear/src/supply_chain.rs` | `compute_reward()`, `verify_uncle_split()` |
| `bin/dwowd/src/lib.rs` | `init_genesis()`, `build_genesis_deployment_txs()` |
| `src/contract/README.md` | contract catalogue, token design philosophy |
| `src/contract/box/proof/{put,take}.zk`, `src/contract/purse/proof/{deposit,withdraw,balance}.zk`, `src/contract/promissory_note/proof/{register_type,issue,revoke,transfer,redeem}.zk` | the ten L1 circuits read in Week 1 §3 |
| `src/contract/{box,purse,promissory_note}/src/model/mod.rs`, `.../entrypoint/mod.rs`, `.../manifest.toml`, `.../README.md` | wire structs, Exec/Apply logic, `witness_map`, barb tables |
| `src/contract/promissory_note/src/lib.rs` | `PromissoryNoteFunction` selectors |
| `src/linear/src/chain_state.rs`, `src/linear/src/transaction.rs` | block‑level nullifier de‑duplication |
| `doc/src/arch/privacy.md`, `doc/src/arch/wallet.md`, `doc/src/arch/verification-hazop.md`, `doc/src/contract/{box,purse,promissory_note,tx-commitment}.md`, `doc/src/dev/contracts/{safety,contract-standards}.md` | L1 design text, generic prover, HAZOP obligations, complexity ceiling |
| `doc/src/arch/genesis.md`, `doc/src/arch/consensus/*`, `doc/src/arch/ocap.md`, `doc/src/about/differences_from_upstream.md`, `doc/src/philosophy/*` | spec text quoted in the notes |

## Week 1 original notes

Google Doc: <https://docs.google.com/document/d/1G5zCkHBF2VW92Cn9dtDrSdRFjtlWLs5aJD4qQeSaiHM/edit?usp=sharing> — the text that [`weeks/week-01/README.md`](../weeks/week-01/README.md) expands on.
