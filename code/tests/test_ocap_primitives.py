"""Claims in weeks/week-02/README.md §1-§2 about the six primitives, their circuits,
the Book-era vs shipped dao_escrow, and the composition matrix."""

import pytest

from darkwow_research import ocap_primitives as oc


# --------------------------------------------------------------------------------------
# §1 -- selector tables match manifest.toml (functions / requires_proof / circuits)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("contract", "selectors", "proofs", "circuits"), [
    ("purse", 4, 3, 3), ("box", 3, 2, 2), ("identity", 8, 2, 2), ("multisig", 4, 3, 3),
    ("oracle", 6, 6, 6), ("attestation", 14, 10, 10), ("promissory_note", 6, 5, 5),
    ("dao_escrow", 10, 6, 5), ("escrow", 6, 5, 5),
])
def test_selector_counts_match_manifests(contract, selectors, proofs, circuits):
    c = oc.CONTRACTS[contract]
    assert len(c.selectors) == selectors
    assert len(c.proof_selectors) == proofs
    assert len(c.circuits) == circuits


def test_six_governance_primitives_are_genesis_contracts():
    assert [p.name for p in oc.PRIMITIVES] == ["purse", "box", "identity", "multisig", "oracle", "attestation"]
    assert all(p.genesis_counter is not None for p in oc.PRIMITIVES)
    assert oc.DAO_ESCROW.genesis_counter is None and oc.ESCROW.genesis_counter is None


def test_identity_selector_0x03_is_a_hole_and_0x06_is_the_capability_check():
    with pytest.raises(KeyError):
        oc.IDENTITY.selector(0x03)
    assert oc.IDENTITY.selector(0x06).name == "VerifyCapabilityV1"
    assert oc.IDENTITY.selector(0x06).circuit == "VerifyCapabilityV2"


# --------------------------------------------------------------------------------------
# §1.2 -- forty-one circuits; only the oracle leaves k = 11
# --------------------------------------------------------------------------------------


def test_forty_one_circuits_across_nine_contracts():
    assert len(oc.CIRCUITS) == 41
    assert len({c.contract for c in oc.CIRCUITS}) == 9


def test_only_oracle_circuits_leave_k_11():
    non11 = {(c.contract, c.circuit, c.k) for c in oc.CIRCUITS if c.k != 11}
    assert {c for c, _, _ in non11} == {"oracle"}
    assert len(non11) == 6
    assert oc.circuit("oracle", "push_value_commitment").k == 14


def test_eight_of_ten_attestation_circuits_publish_only_the_tx_pair():
    att = oc.circuits_for("attestation")
    tx_only = [c for c in att if c.only_tx_pair_is_public]
    assert len(att) == 10 and len(tx_only) == 8
    assert {c.circuit for c in att} - {c.circuit for c in tx_only} == {"consume_claim", "delegate_attestation"}
    # three statements: two witnesses copied to instances and one hash nobody constrains
    assert {c.statements for c in tx_only if c.circuit in ("create_attestation", "create_claim")} == {3}


def test_only_consume_claim_binds_a_secret_among_attestation_circuits():
    binders = [c.circuit for c in oc.circuits_for("attestation") if c.binds_a_secret]
    assert binders == ["consume_claim"]


def test_box_take_publishes_four_instances_without_contents_or_owner():
    take = oc.circuit("box", "take")
    assert take.public_inputs == ("nullifier", "expected_root", "tx_binding", "tx_nonce")
    assert "contents_commit" not in take.public_inputs
    assert take.merkle_root == 1  # possession is proven, but of *which* box is private


def test_escrow_claim_publishes_the_seller_commitment_itself():
    claim = oc.circuit("escrow", "claim")
    assert "escrow_seller_commitment" in claim.public_inputs
    assert claim.binds_a_secret


# --------------------------------------------------------------------------------------
# §2 -- the Book's 17 dao_escrow selectors vs the 10 that shipped
# --------------------------------------------------------------------------------------


def test_book_table_has_seventeen_contiguous_selectors():
    codes = [s.code for s in oc.BOOK_DAO_ESCROW]
    assert codes == list(range(0x11))


def test_fate_counts_kept_rewired_retired():
    r = oc.selector_retirement()
    assert {f: len(v) for f, v in r.items()} == {oc.Fate.KEPT: 5, oc.Fate.REWIRED: 5, oc.Fate.RETIRED: 7}


def test_kept_plus_rewired_is_exactly_what_shipped():
    r = oc.selector_retirement()
    surviving = {s.code for s in r[oc.Fate.KEPT] + r[oc.Fate.REWIRED]}
    assert surviving == oc.shipped_codes()
    assert len(surviving) == 10


def test_retired_selectors_are_invalid_function_in_code():
    for s in oc.selector_retirement()[oc.Fate.RETIRED]:
        with pytest.raises(KeyError):
            oc.DAO_ESCROW.selector(s.code)


def test_every_capability_gated_book_selector_was_rewired_or_retired():
    gated = [s for s in oc.BOOK_DAO_ESCROW if "board_" in s.book_capability or s.book_capability == "member_vote"
             or s.book_capability == "dispute_arbitrator"]
    assert gated and all(s.fate in (oc.Fate.REWIRED, oc.Fate.RETIRED) for s in gated)


def test_book_dao_escrow_named_six_primitives_the_code_uses_two_children():
    assert len(oc.BOOK_DAO_ESCROW_PRIMITIVES) == 6
    assert len(oc.CODE_DAO_ESCROW_CHILDREN) == 2
    assert oc.reference("box", "dao_escrow") is oc.RefKind.NONE
    assert oc.reference("purse", "dao_escrow") is oc.RefKind.NONE
    assert oc.reference("identity", "dao_escrow") is oc.RefKind.NONE
    assert oc.reference("oracle", "dao_escrow") is oc.RefKind.NONE
    assert oc.reference("attestation", "dao_escrow") is oc.RefKind.NONE
    assert oc.reference("multisig", "dao_escrow") is oc.RefKind.ENTRYPOINT
    assert oc.reference("promissory_note", "dao_escrow") is oc.RefKind.ENTRYPOINT


# --------------------------------------------------------------------------------------
# §1.3 -- composition matrix
# --------------------------------------------------------------------------------------


def test_matrix_shape_is_seven_by_thirty_two():
    m = oc.composition_matrix()
    assert len(m) == 7 and all(len(r) == 32 for r in m)
    assert len(oc.ALL_CONTRACTS) == 32


def test_oracle_has_no_entrypoint_consumer_anywhere():
    assert oc.consumers("oracle") == ()
    assert oc.consumers("oracle", oc.RefKind.LIB_ONLY) == ("darkbet_exchange",)


def test_escrow_and_drain_protection_are_the_only_box_plus_purse_composers():
    both = [c for c in oc.ALL_CONTRACTS
            if oc.reference("box", c) is oc.RefKind.ENTRYPOINT and oc.reference("purse", c) is oc.RefKind.ENTRYPOINT]
    assert both == ["drain_protection", "escrow"]


def test_nine_contracts_compose_a_governance_primitive():
    assert oc.composers() == ("dao_escrow", "drain_protection", "escrow", "identity", "insurance_market",
                              "labor_market", "pool_stake", "stablecoin", "tender")


def test_identity_box_reference_is_comment_only():
    assert ("box", "identity") in oc.COMMENT_ONLY_REFS
    assert oc.reference("box", "identity") is oc.RefKind.ENTRYPOINT


def test_lib_only_is_a_superset_of_entrypoint_references():
    for p in oc.PRIMITIVE_ROWS:
        assert set(oc._ENTRY[p]) <= set(oc._LIB[p]), p


# --------------------------------------------------------------------------- Week 1 erratum


def test_week1_finding_8_is_closed_at_d775e37c():
    """Week 1 Finding 8: Box/Purse leaves did not pin their owner (ec914970).  At d775e37c
    every L1 leaf folds ``owner_pub``; Week 1's model is kept as the historical record."""
    from darkwow_research import l1_circuits as w1

    for c in (w1.BOX_PUT, w1.BOX_TAKE, w1.PURSE_DEPOSIT, w1.PURSE_WITHDRAW):
        assert "owner_pub" not in c.leaf and not c.leaf_binds_owner
    for key, leaf in oc.LEAF_FORMULAS.items():
        assert leaf[-1] == "owner_pub" and leaf[0] == "DOMAIN_MERKLE_LEAF", key
    assert set(oc.LEAF_FORMULAS) == {("box", "put"), ("box", "take"), ("purse", "deposit"), ("purse", "withdraw")}
