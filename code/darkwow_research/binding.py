"""Who is bound to what: the Attestation contract's authority table and the
``tx_binding`` verification chain.

Two questions from the Week 2 brief are really the same question -- *which
party does a proof bind, and who checks it?* -- so they share a module.

**Attestation (BUG-02).**  For each of the fourteen selectors of
``src/contract/attestation`` at ``d775e37c`` the table records what the proof
publishes (from ``get_metadata``, entrypoint.rs 145-355, and the ``.zk``
sources), which state checks ``exec`` performs, and therefore which actor --
attestor, claimant, verifier -- is cryptographically bound.  The answer is
"only the consumer, at ``ConsumeClaimV1``".

**tx_binding (cross-cutting).**  ``doc/src/contract/tx-commitment.md`` and the
Book (p. 1251) describe a four-stage chain: the circuit derives
``tx_binding = H(3, tx_commitment, tx_nonce)``; the contract's metadata echoes
the wire value as a public input; the VM checks instances against the proof;
and the *node* recomputes ``H(3, tx.tx_commitment, tx_nonce)`` and compares.
The last stage does not exist in ``src/linear`` / ``src/runtime`` / ``src/zk``,
and no host import exposes ``tx_commitment`` to WASM.  ``tx_binding_chain``
lists the stages with the file that implements each, or ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Bound(str, Enum):
    """How an actor named by a call is tied to the call."""

    PROOF = "proof"      # a secret is proven in-circuit and its derivation published
    STATE = "state"      # exec compares a wire field against stored state (self-asserted field)
    NONE = "none"        # nothing binds the actor; the wire field is taken at face value


@dataclass(frozen=True)
class AttestationOp:
    code: int
    name: str
    circuit: str | None
    public_inputs: tuple[str, ...]      # what the proof publishes (metadata arm)
    actor: str                           # the party the call speaks for
    actor_binding: Bound
    state_checks: tuple[str, ...]        # exec-side checks, in order
    replayable_proof: bool               # can the same proof be re-submitted in another tx?
    note: str = ""

    @property
    def unauthenticated(self) -> bool:
        """A STATE binding against a public value is not authentication either."""
        return self.actor_binding is not Bound.PROOF


_TX = ("tx_binding", "tx_nonce")
_CONST_TXB = "tx_binding = poseidon_hash(3, 0, 0) -- a constant; every client publishes the same value"

ATTESTATION_OPS: tuple[AttestationOp, ...] = (
    AttestationOp(0x00, "CreateAttestationV1", "CreateAttestationV2", _TX, "attestor", Bound.NONE,
                  ("attestation_id unique",), True,
                  "attestor_pub stored from params; `attestor_secret: zero // Not stored`"),
    AttestationOp(0x01, "RevokeAttestationV1", None, (), "attestor", Bound.STATE,
                  ("attestation exists", "params.attestor_pub == stored attestor_pub", "state Active"), False,
                  "no circuit; the compared field is a *public* key anyone can copy onto the wire"),
    AttestationOp(0x02, "ExpireAttestationV1", None, (), "anyone", Bound.NONE,
                  ("attestation exists", "expiry <= height"), False, "no circuit; legitimately permissionless"),
    AttestationOp(0x03, "CreateClaimV1", "CreateClaimV2", _TX, "claimant", Bound.NONE,
                  ("attestation Active & unexpired", "predicate matches or Custom", "claim_id unique",
                   "rate limit: 1 block per (attestation, claimant_pub)"), True,
                  "claimant_pub stored from params, unauthenticated"),
    AttestationOp(0x04, "VerifyClaimV1", "VerifyClaimV2", _TX, "verifier", Bound.NONE,
                  ("claim Pending", "attestation Active", "claim.attestation_id == params",
                   "evidence_commitment == params", "verified := revealed_result != 0"), True,
                  "comments say the circuit constrains revealed_result; VerifyClaimV2 constrains only the tx pair"),
    AttestationOp(0x05, "ConsumeClaimV1", "ConsumeClaimV2",
                  ("claim_id", "claimant_pub.x", "claimant_pub.y", "nullifier", *_TX), "consumer",
                  Bound.PROOF, ("claim Verified", "claim.claimant_pub == params.claimant_pub",
                                "nullifier unspent"), False,
                  "consumer_pub = ec_mul_base(consumer_secret, NULLIFIER_K); nullifier = H(1, claim_id, consumer_secret)"),
    AttestationOp(0x06, "ValidateClaimV1", None, (), "anyone", Bound.NONE,
                  ("claim exists",), False, "read-only, no circuit"),
    AttestationOp(0x07, "CheckNotRevokedV1", "CheckNotRevokedV2", _TX, "anyone", Bound.NONE,
                  ("attestation exists", "state != Revoked"), True, "read-only predicate"),
    AttestationOp(0x08, "DelegateAttestationV1", "DelegateAttestationV2", ("delegatee_leaf", *_TX),
                  "attestor", Bound.NONE, ("attestation Active", "delegation_id unique"), True,
                  "publishes H(4, delegatee_pub) -- the *delegatee*, not the delegating attestor"),
    AttestationOp(0x09, "VerifyChainV1", "VerifyChainV2", _TX, "anyone", Bound.NONE,
                  ("each link exists and is Active",), True, "read-only"),
    AttestationOp(0x0A, "UpdateDelegationV1", "UpdateDelegationV2", _TX, "attestor", Bound.NONE,
                  ("delegation exists",), True, "delegator not proven"),
    AttestationOp(0x0B, "AttestSlashV1", "AttestSlashV2", _TX, "attestor", Bound.NONE,
                  ("attestation exists",), True, ""),
    AttestationOp(0x0C, "CommitFeeScheduleV1", "CommitFeeScheduleV2", _TX, "attestor", Bound.NONE,
                  ("schedule_id unique",), True, ""),
    AttestationOp(0x0D, "CheckAttestationV1", None, (), "anyone", Bound.NONE,
                  ("attestation exists",), False, "read-only, no circuit"),
)

# How each contract's metadata() derives the tx_binding public input it hands the verifier
# (entrypoint*.rs / lib.rs at d775e37c, comments stripped).  "constant" = the literal
# poseidon_hash(3, 0, 0) -- every proof for the contract publishes the same value, so the
# proof is tied to no transaction even in principle; "echo" = params.tx_binding copied from
# the wire -- self-asserted, since stage 4 below never compares it to the real tx.
TX_BINDING_SOURCE: dict[str, str] = {
    "attestation": "constant", "auction": "constant", "baccarat": "constant", "bearer_bond": "constant",
    "betting_stake": "constant", "bridge": "constant", "dao_escrow": "constant",
    "darkbet_exchange": "constant", "darktoshi_dice": "constant", "escrow": "constant",
    "game_room": "constant", "identity": "constant", "insurance_market": "constant",
    "lottery": "constant", "otc_swap": "constant", "pool_stake": "constant",
    "relayer_endowment": "constant", "roulette": "constant", "slot": "constant",
    "box": "echo", "dex": "echo", "drain_protection": "echo", "labor_market": "echo",
    "multisig": "echo", "native_token": "echo", "oracle": "echo", "promissory_note": "echo",
    "purse": "echo", "subscription": "echo", "tender": "echo",
    "stablecoin": "mixed",
    "deployooor": "no circuits",
}
CONSTANT_TX_BINDING_CONTRACTS = tuple(c for c, k in TX_BINDING_SOURCE.items() if k == "constant")
ECHO_TX_BINDING_CONTRACTS = tuple(c for c, k in TX_BINDING_SOURCE.items() if k == "echo")


def tx_binding_source_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for k in TX_BINDING_SOURCE.values():
        out[k] = out.get(k, 0) + 1
    return out


def attestation_op(code: int) -> AttestationOp:
    for op in ATTESTATION_OPS:
        if op.code == code:
            return op
    raise KeyError(f"attestation 0x{code:02x}")


def authority_summary() -> dict[str, int]:
    """Counts the BUG-02 verdict rests on."""
    ops = ATTESTATION_OPS
    return {
        "selectors": len(ops),
        "with_circuit": sum(op.circuit is not None for op in ops),
        "publish_only_tx_pair": sum(op.public_inputs == _TX for op in ops),
        "actor_bound_by_proof": sum(op.actor_binding is Bound.PROOF for op in ops),
        "state_writers_unauthenticated": sum(
            op.unauthenticated and op.actor != "anyone" for op in ops),
        "replayable_proofs": sum(op.replayable_proof for op in ops),
    }


# --------------------------------------------------------------------------------------
# the forged-attestation path a wallet could take today (BUG-02, stronger form)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    selector: int
    actor: str
    what: str
    needs_secret_of: str | None  # whose secret the step requires, if any


FORGERY_PATH: tuple[Step, ...] = (
    Step(0x00, "anyone", "CreateAttestationV1 naming any attestor_pub (victim's key)", None),
    Step(0x03, "anyone", "CreateClaimV1 against it naming claimant_pub = own key", None),
    Step(0x04, "anyone", "VerifyClaimV1 with revealed_result = 1 -> state Verified", None),
    Step(0x05, "forger", "ConsumeClaimV1 -- the only step that needs a secret, and it is the forger's own",
         "forger"),
)


def secrets_required(path: tuple[Step, ...] = FORGERY_PATH) -> set[str]:
    return {s.needs_secret_of for s in path if s.needs_secret_of}


# --------------------------------------------------------------------------------------
# tx_binding verification chain
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage:
    n: int
    who: str
    claim: str                       # what the spec says happens
    implemented_in: str | None       # file:lines, or None when the stage does not exist
    effect: str

    @property
    def implemented(self) -> bool:
        return self.implemented_in is not None


TX_BINDING_CHAIN: tuple[Stage, ...] = (
    Stage(1, "circuit", "tx_binding = poseidon_hash(3, tx_commitment, tx_nonce) with tx_commitment a witness",
          "src/contract/*/proof/*.zk (e.g. box/proof/take.zk)",
          "binds the proof to *some* tx_commitment the prover chose"),
    Stage(2, "contract metadata()", "publish params.tx_binding and params.tx_nonce as public inputs",
          "src/contract/box/src/entrypoint/mod.rs:77-84 (take_metadata) and every sibling",
          "echoes the wire value; nothing compares it to the enclosing transaction"),
    Stage(3, "VM / zk_verifier", "verify each proof against metadata()'s public inputs",
          "src/linear/src/zk_verifier.rs (verify_core_tx_with_tables)",
          "proof and wire agree with each other"),
    Stage(4, "node", "expected = H(3, tx.tx_commitment, tx_nonce); require expected == tx_binding",
          None,
          "absent: no host import exposes tx_commitment to WASM and no node-side comparison exists"),
)

HOST_IMPORTS = (
    "drk_log", "set_return_data", "db_init", "db_lookup", "db_get", "db_contains_key", "db_set",
    "db_del", "db_mark_spent", "zkas_db_set", "get_object_bytes", "get_object_size", "merkle_add",
    "sparse_merkle_insert_batch", "merkle_anchor_add", "get_verifying_block_height",
    "get_block_target", "get_tx_hash", "get_call_index", "get_blockchain_time",
    "get_last_block_height", "get_tx", "get_tx_location", "get_block_hash", "emit_spend_hook",
)


def tx_binding_chain_status() -> dict[str, object]:
    missing = [s for s in TX_BINDING_CHAIN if not s.implemented]
    return {
        "stages": len(TX_BINDING_CHAIN),
        "implemented": len(TX_BINDING_CHAIN) - len(missing),
        "missing": [s.n for s in missing],
        "tx_commitment_host_import": any("commitment" in h for h in HOST_IMPORTS),
    }


def replay_defences(selector_nullifier: bool) -> tuple[str, ...]:
    """What stops a proof being re-used in a second transaction, given the chain above."""
    defences = []
    if selector_nullifier:
        defences.append("nullifier marked spent in exec/apply")
    # tx_binding is self-asserted at every stage the node implements
    return tuple(defences)


# --------------------------------------------------------------------------------------
# the project's own verification register (doc/src/arch/verification-hazop.md, 242 rows)
# --------------------------------------------------------------------------------------

HAZOP_STATUS: dict[str, int] = {
    "CLOSED": 72, "SATISFIED": 52, "OPEN": 43, "FIXED": 32, "PARTLY": 20,
    "ACCEPTED-WITH-REASON": 11, "RESTATED": 6, "FAILS": 3, "MECHANIZED": 2, "DEFINITIONAL": 1,
}
HAZOP_FAMILIES: dict[str, int] = {"OBL-C": 194, "OBL-T": 26, "OBL-Z": 22}
HAZOP_FAILS = (
    ("OBL-Z3", "every poseidon_hash in a circuit is domain-separated by the *right* constant"),
    ("OBL-Z18", "every constrain_equal_base has an operand the verifier can see"),
    ("OBL-C109", "the specification's maturity rule is the code's"),
)
# rows this note leans on, with the status the register itself records
HAZOP_CITED = {
    "OBL-Z18": "FAILS", "OBL-Z3": "FAILS", "OBL-C171": "OPEN", "OBL-C179": "OPEN",
    "OBL-C138": "OPEN", "OBL-C151": "CLOSED", "OBL-C168": "FIXED", "OBL-C152": "FIXED",
}


def hazop_resolved_share() -> float:
    done = sum(HAZOP_STATUS[k] for k in ("CLOSED", "SATISFIED", "FIXED", "MECHANIZED", "DEFINITIONAL"))
    return done / sum(HAZOP_STATUS.values())


def _main() -> None:  # pragma: no cover
    print("attestation authority:", authority_summary())
    for op in ATTESTATION_OPS:
        print(f"  0x{op.code:02x} {op.name:24s} actor={op.actor:9s} bound={op.actor_binding.value:5s} "
              f"pub={len(op.public_inputs)} replay={'y' if op.replayable_proof else 'n'}")
    print("forgery path needs secrets of:", secrets_required() or "{}")
    print("tx_binding chain:", tx_binding_chain_status())


if __name__ == "__main__":  # pragma: no cover
    _main()
