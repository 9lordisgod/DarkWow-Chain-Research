"""Claims in weeks/week-02/README.md §4 (BUG-02) and §7 (tx_binding chain)."""

import pytest

from darkwow_research import binding as b
from darkwow_research import ocap_primitives as oc


# --------------------------------------------------------------------------------------
# §4.1 -- the attestation authority table
# --------------------------------------------------------------------------------------


def test_authority_summary_counts():
    assert b.authority_summary() == {
        "selectors": 14,
        "with_circuit": 10,
        "publish_only_tx_pair": 8,
        "actor_bound_by_proof": 1,
        "state_writers_unauthenticated": 8,
        "replayable_proofs": 9,
    }


def test_consume_claim_is_the_only_proof_bound_actor():
    bound = [op.name for op in b.ATTESTATION_OPS if op.actor_binding is b.Bound.PROOF]
    assert bound == ["ConsumeClaimV1"]
    op = b.attestation_op(0x05)
    assert "nullifier" in op.public_inputs and not op.replayable_proof


def test_revoke_compares_a_public_key_on_the_wire():
    op = b.attestation_op(0x01)
    assert op.circuit is None and op.actor_binding is b.Bound.STATE and op.unauthenticated
    assert "params.attestor_pub == stored attestor_pub" in op.state_checks


def test_verify_claim_sets_verified_from_a_wire_field():
    op = b.attestation_op(0x04)
    assert op.public_inputs == ("tx_binding", "tx_nonce")
    assert "verified := revealed_result != 0" in op.state_checks


def test_delegate_publishes_the_delegatee_not_the_delegator():
    op = b.attestation_op(0x08)
    assert op.public_inputs[0] == "delegatee_leaf" and op.actor_binding is b.Bound.NONE


def test_authority_table_agrees_with_the_circuit_registry():
    """Every op that claims a circuit has one in ocap_primitives, and the tx-pair-only
    ops are exactly the circuits with two constrain_instance calls."""
    circuits = {c.circuit for c in oc.circuits_for("attestation")}
    assert len(circuits) == 10
    tx_only_ops = {op.circuit for op in b.ATTESTATION_OPS if op.public_inputs == ("tx_binding", "tx_nonce")}
    tx_only_circuits = {c.circuit for c in oc.circuits_for("attestation") if c.only_tx_pair_is_public}
    # the op table uses the zkas namespace (CamelCaseV2); the registry uses the file stem
    def stem(ns):
        s = ns[:-2] if ns.endswith("V2") else ns
        return "".join("_" + ch.lower() if ch.isupper() else ch for ch in s).lstrip("_")
    assert {stem(n) for n in tx_only_ops} == tx_only_circuits


def test_nineteen_contracts_publish_a_constant_tx_binding():
    assert b.tx_binding_source_counts() == {"constant": 19, "echo": 11, "mixed": 1, "no circuits": 1}
    assert len(b.TX_BINDING_SOURCE) == 32
    for c in ("attestation", "identity", "dao_escrow", "escrow"):
        assert c in b.CONSTANT_TX_BINDING_CONTRACTS
    for c in ("box", "purse", "multisig", "oracle", "promissory_note"):
        assert c in b.ECHO_TX_BINDING_CONTRACTS


def test_five_of_the_six_governance_primitives_echo_the_wire_value():
    six = ("purse", "box", "identity", "multisig", "oracle", "attestation")
    assert [b.TX_BINDING_SOURCE[c] for c in six] == ["echo", "echo", "constant", "echo", "echo", "constant"]


# --------------------------------------------------------------------------------------
# §4.3 -- the forgery path needs only the forger's own secret
# --------------------------------------------------------------------------------------


def test_forgery_path_has_four_steps_and_needs_no_victim_secret():
    assert len(b.FORGERY_PATH) == 4
    assert b.secrets_required() == {"forger"}
    assert [s.selector for s in b.FORGERY_PATH] == [0x00, 0x03, 0x04, 0x05]


def test_only_the_last_forgery_step_needs_a_secret():
    assert [s.needs_secret_of for s in b.FORGERY_PATH[:3]] == [None, None, None]


# --------------------------------------------------------------------------------------
# §7 -- tx_binding chain: three of four stages exist
# --------------------------------------------------------------------------------------


def test_tx_binding_chain_stage_four_is_missing():
    assert b.tx_binding_chain_status() == {
        "stages": 4, "implemented": 3, "missing": [4], "tx_commitment_host_import": False,
    }


def test_no_host_import_exposes_the_tx_commitment():
    assert len(b.HOST_IMPORTS) == 25
    assert not any("commitment" in h or "binding" in h for h in b.HOST_IMPORTS)
    assert "get_tx_hash" in b.HOST_IMPORTS  # exists, but nobody hashes it into tx_binding


def test_without_stage_four_only_nullifiers_stop_replay():
    assert b.replay_defences(selector_nullifier=True) == ("nullifier marked spent in exec/apply",)
    assert b.replay_defences(selector_nullifier=False) == ()


@pytest.mark.parametrize("code", [0x00, 0x03, 0x04, 0x07, 0x09, 0x0A, 0x0B, 0x0C])
def test_tx_pair_only_ops_have_no_replay_defence(code):
    op = b.attestation_op(code)
    assert op.replayable_proof
    assert b.replay_defences(selector_nullifier="nullifier unspent" in op.state_checks) == ()


# --------------------------------------------------------------------------------------
# §7.3 -- the project's own verification register
# --------------------------------------------------------------------------------------


def test_hazop_register_has_242_rows_in_three_families():
    assert sum(b.HAZOP_STATUS.values()) == 242
    assert sum(b.HAZOP_FAMILIES.values()) == 242
    assert b.HAZOP_STATUS["OPEN"] == 43 and b.HAZOP_STATUS["FAILS"] == 3


def test_the_two_zk_fails_rows_are_the_ones_bug_02_turns_on():
    ids = [i for i, _ in b.HAZOP_FAILS]
    assert "OBL-Z3" in ids and "OBL-Z18" in ids
    assert b.HAZOP_CITED["OBL-Z18"] == "FAILS" and b.HAZOP_CITED["OBL-C171"] == "OPEN"


def test_roughly_two_thirds_of_the_register_is_resolved():
    assert 0.60 < b.hazop_resolved_share() < 0.70
