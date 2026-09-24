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

Useful page ranges in this snapshot (as extracted with `pypdf`): contract deployment pipeline & genesis table pp. 123–125; Uncle Merkle overview pp. 337–339; uncle reward split & formal spec pp. 366–368; consensus & coinbase — emission constants pp. 645–652; genesis specification pp. 903–907; history of the fork / philosophy pp. 1921–1923.

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
| `doc/src/arch/genesis.md`, `doc/src/arch/consensus/*`, `doc/src/arch/ocap.md`, `doc/src/about/differences_from_upstream.md`, `doc/src/philosophy/*` | spec text quoted in the notes |

## Week 1 original notes

Google Doc: <https://docs.google.com/document/d/1G5zCkHBF2VW92Cn9dtDrSdRFjtlWLs5aJD4qQeSaiHM/edit?usp=sharing> — the text that [`weeks/week-01/README.md`](../weeks/week-01/README.md) expands on.
