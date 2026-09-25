"""Claims in weeks/week-01/README.md §3 about Box, Purse and Promissory Note."""

import pytest

from darkwow_research import l1_circuits as l1


# --------------------------------------------------------------------------------------
# §3.1 -- the Halo2 L1 ceiling table reproduces from the .zk witness sections
# --------------------------------------------------------------------------------------


def test_ten_l1_circuits_all_at_k_11():
    assert len(l1.CIRCUITS) == 10
    assert {c.k for c in l1.CIRCUITS} == {11}


@pytest.mark.parametrize(("key", "expected"), sorted(l1.BOOK_CEILING_TABLE.items()))
def test_book_ceiling_table_matches_circuit_files(key, expected):
    contract, name = key
    (c,) = [c for c in l1.CIRCUITS if (c.contract, c.name) == key]
    assert (len(c.public_inputs), c.witness_only) == expected


def test_purse_deposit_and_withdraw_sit_exactly_on_the_ceiling():
    for c in (l1.PURSE_DEPOSIT, l1.PURSE_WITHDRAW):
        assert len(c.public_inputs) == l1.P_CEILING
        assert c.witness_only == l1.W_CEILING
    assert l1.operations("purse") == l1.O_CEILING


def test_box_and_purse_are_safe_tier():
    assert l1.contract_tier("box") is l1.Tier.SAFE
    assert l1.contract_tier("purse") is l1.Tier.SAFE


def test_promissory_note_is_l1_but_falls_outside_the_safe_tier():
    # The Book triages only Box and Purse. Revoke_V2 has ten constrain_instance
    # calls (P_CEILING is nine) and the contract exposes five circuits (O_CEILING
    # is three), so by the Book's own table PN is "scrutiny", not "safe".
    assert len(l1.PN_REVOKE.public_inputs) == 10 > l1.P_CEILING
    assert l1.PN_REVOKE.public_input_tier is l1.Tier.SCRUTINY
    assert l1.operations("promissory_note") == 5 > l1.O_CEILING
    assert l1.contract_tier("promissory_note") is l1.Tier.SCRUTINY
    assert ("promissory_note", "Revoke_V2") not in l1.BOOK_CEILING_TABLE


def test_every_l1_circuit_publishes_tx_binding_and_tx_nonce():
    for c in l1.CIRCUITS:
        assert "tx_binding" in c.public_inputs, c.name
        assert "tx_nonce" in c.public_inputs, c.name
        assert "tx_commitment" in c.witnesses and "tx_commitment" not in c.public_inputs, c.name


# --------------------------------------------------------------------------------------
# §3.2 / §3.3 -- Box and Purse anatomy
# --------------------------------------------------------------------------------------


def test_box_circuits_are_poseidon_only_and_have_no_owner_pub():
    for c in (l1.BOX_PUT, l1.BOX_TAKE):
        assert c.ec_ops == 0
        assert "owner_pub" not in c.witnesses  # the Book's `↓spend` barb has no counterpart


def test_box_take_is_terminal_and_put_is_consume_plus_create():
    assert l1.BOX_TAKE.consumes and not l1.BOX_TAKE.creates
    assert l1.BOX_PUT.consumes and l1.BOX_PUT.creates
    assert "new_state_nonce" in l1.BOX_PUT.witnesses  # free witness -- Purse derives nonce+1 instead


def test_purse_deposit_withdraw_have_no_asset_binding():
    for c in (l1.PURSE_DEPOSIT, l1.PURSE_WITHDRAW):
        assert "token_commit" not in c.public_inputs
        assert "asset_id" not in c.witnesses
    assert "token_commit" in l1.PURSE_BALANCE.public_inputs
    assert "derived_purse_id" in l1.PURSE_BALANCE.public_inputs


def test_purse_is_not_poseidon_only():
    # three Pedersen commitments = 3 x (ec_mul_short + ec_mul + ec_add) + one ec_add for the sum
    assert l1.PURSE_DEPOSIT.ec_ops == 10
    assert l1.PURSE_DEPOSIT.range_checks == 3


def test_promissory_note_circuits_all_compute_a_pedersen_commitment_in_circuit():
    for c in l1.circuits_for("promissory_note"):
        assert c.ec_ops == 3, c.name
        assert {"value_commit.x", "value_commit.y"} <= set(c.public_inputs), c.name


# --------------------------------------------------------------------------------------
# §3.5 -- who may consume a leaf?
# --------------------------------------------------------------------------------------


def test_box_and_purse_leaves_do_not_commit_to_their_owner():
    for c in (l1.BOX_PUT, l1.BOX_TAKE, l1.PURSE_DEPOSIT, l1.PURSE_WITHDRAW):
        assert c.owner_secret in c.nullifier
        assert c.owner_secret not in c.leaf
        assert not c.leaf_binds_owner
        assert c.max_nullifiers_per_leaf is None  # one nullifier per distinct owner_secret


def test_promissory_note_coin_commits_to_its_owner():
    # coin = H(4, pub, ...), pub = H(7, spend_secret), nullifier = H(1, spend_secret, coin)
    assert l1.PN_REVOKE.leaf_binds_owner
    assert l1.PN_REVOKE.nullifier == ("spend_secret", "coin")
    assert l1.PN_REVOKE.max_nullifiers_per_leaf == 1


def test_leaf_preimages_of_box_and_purse_travel_in_plaintext_params():
    assert l1.leaf_preimage_on_wire(l1.PUT_PARAMS, l1.BOX_PUT)
    assert l1.leaf_preimage_on_wire(l1.TAKE_PARAMS, l1.BOX_TAKE)
    assert l1.leaf_preimage_on_wire(l1.DEPOSIT_PARAMS, l1.PURSE_DEPOSIT)
    assert l1.leaf_preimage_on_wire(l1.WITHDRAW_PARAMS, l1.PURSE_WITHDRAW)


# --------------------------------------------------------------------------------------
# §3.4 -- wire formats
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", l1.WIRE_FORMATS, ids=lambda f: f.struct)
def test_header_constant_matches_encode(fmt):
    assert l1.header_bytes(fmt) == fmt.header_bytes


def test_encoded_sizes():
    assert l1.PUT_PARAMS.encoded_size() == 1349
    assert l1.TAKE_PARAMS.encoded_size() == 1253
    assert l1.DEPOSIT_PARAMS.encoded_size() == 1437
    assert l1.WITHDRAW_PARAMS.encoded_size() == 1437
    assert l1.BALANCE_PARAMS.encoded_size() == 1357
    assert l1.PUT_PARAMS.encoded_size(proof_len=3) == 1352  # tests upstream use vec![1, 2, 3]
    with pytest.raises(ValueError):
        l1.PUT_PARAMS.encoded_size(proof_len=256)


def test_merkle_path_dominates_the_payload():
    for fmt in l1.WIRE_FORMATS:
        assert l1.MERKLE_PATH_BYTES / fmt.encoded_size() > 0.7


def test_plaintext_balances_on_the_purse_wire():
    names = [f.name for f in l1.DEPOSIT_PARAMS.plaintext_witness_fields]
    assert {"old_balance", "deposit_amount", "new_balance", "purse_id", "state_nonce", "asset_id"} <= set(names)
    assert sum(f.size for f in l1.DEPOSIT_PARAMS.fields if f.name.endswith("balance") or f.name == "deposit_amount") == 24


# --------------------------------------------------------------------------------------
# §3.6 -- Promissory Note selectors
# --------------------------------------------------------------------------------------


def test_promissory_note_function_codes():
    assert [f.name for f in l1.PromissoryNoteFunction] == [
        "RegisterTypeV1", "RedeemV1", "IssueV1", "RevokeV1", "TransferV1", "OtcSwapV1",
    ]
    assert l1.PromissoryNoteFunction.RedeemV1 == 0x01
    assert l1.PromissoryNoteFunction.OtcSwapV1 == 0x05


def test_legacy_names_disagree_with_the_code():
    # TransferV1 exists in both vocabularies but at different selectors.
    assert l1.LEGACY_PN_FUNCTION_NAMES["TransferV1"] == 0x03
    assert l1.PromissoryNoteFunction.TransferV1 == 0x04
    assert l1.LEGACY_PN_FUNCTION_NAMES["OtcSwapV1"] != l1.PromissoryNoteFunction.OtcSwapV1
    assert "RedeemV1" not in l1.LEGACY_PN_FUNCTION_NAMES


def test_pn_redeem_receipt_pins_value_to_zero_and_has_no_nullifier():
    assert "value" in l1.PN_REDEEM.public_inputs
    assert l1.PN_REDEEM.range_checks == 0
    assert not l1.PN_REDEEM.consumes
    assert l1.PN_REVOKE.consumes and l1.PN_REVOKE.merkle_roots == 1
    assert l1.PN_TRANSFER.merkle_roots == 0  # output side only


def test_pn_issue_is_type_transparent_but_transfer_is_not():
    assert "asset_id" in l1.PN_ISSUE.public_inputs
    assert "asset_id" not in l1.PN_TRANSFER.public_inputs
    assert "token_commit" in l1.PN_TRANSFER.public_inputs
