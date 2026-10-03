"""Claims in weeks/week-02/README.md §3 (BUG-01): call ordering, atomic execution and
what a parent can learn from a child's wire."""

import pytest

from darkwow_research import call_tree as ct


def _escrow_tx(children):
    return ct.escrow_claim("E1", children)


# --------------------------------------------------------------------------------------
# §3.1 -- DarkTree is post-order; the parent is always last
# --------------------------------------------------------------------------------------


def test_flatten_is_dfs_post_order_children_first():
    tx = _escrow_tx([ct.pn_transfer("V"), ct.box_take("C_claim")])
    leaves = ct.flatten(tx)
    assert [l.call.contract for l in leaves] == ["promissory_note", "box", "escrow"]
    assert leaves[-1].parent_index is None and leaves[-1].children_indexes == (0, 1)
    assert leaves[0].parent_index == 2 and leaves[1].parent_index == 2
    assert ct.is_post_order(leaves)


def test_nested_tree_still_post_order():
    inner = ct.Call("a", 0).child(ct.Call("b", 0).child(ct.Call("c", 0)))
    leaves = ct.flatten(inner)
    assert [l.call.contract for l in leaves] == ["c", "b", "a"]
    assert ct.is_post_order(leaves)
    ct.reconcile(leaves)  # no exception


def test_reconcile_rejects_a_child_that_does_not_point_back():
    tx = _escrow_tx([ct.pn_transfer("V")])
    leaves = ct.flatten(tx)
    broken = [ct.Leaf(0, leaves[0].call, None, ()), leaves[1]]
    with pytest.raises(ValueError):
        ct.reconcile(broken)


def test_reconcile_rejects_parent_before_child():
    tx = _escrow_tx([ct.pn_transfer("V")])
    a, b = ct.flatten(tx)
    reordered = [ct.Leaf(0, b.call, None, (1,)), ct.Leaf(1, a.call, 0, ())]
    with pytest.raises(ValueError, match="post-order"):
        ct.reconcile(reordered)


def test_limits_quoted_in_the_note():
    assert ct.MAX_TX_CALLS == 20
    assert ct.MAX_CALLS_BY_INDEX_ENCODING == 255


# --------------------------------------------------------------------------------------
# §3.2 -- the execution loop: sequential, shared overlay, atomic
# --------------------------------------------------------------------------------------


def test_in_order_escrow_claim_is_accepted():
    tx = _escrow_tx([ct.pn_transfer("V"), ct.box_take("C_claim")])
    st, tr = ct.execute(tx, ct.ESCROW_HANDLERS, ct.funded_escrow_state())
    assert tr.accepted and tr.executed == [0, 1, 2] and tr.applied == [0, 1, 2]
    assert st[("escrow", "E1")]["state"] == "Claimed"


def test_swapped_siblings_are_rejected_by_slot_check_not_by_the_compiler():
    tx = _escrow_tx([ct.box_take("C_claim"), ct.pn_transfer("V")])
    st, tr = ct.execute(tx, ct.ESCROW_HANDLERS, ct.funded_escrow_state())
    assert not tr.accepted and tr.failed_at == 2
    assert tr.reason == "slot 0: wrong contract box"


def test_rejection_reverts_children_that_already_ran():
    """Children execute *before* the parent, so the parent's rejection must undo them."""
    tx = _escrow_tx([ct.box_take("C_claim"), ct.pn_transfer("V")])
    initial = ct.funded_escrow_state()
    st, tr = ct.execute(tx, ct.ESCROW_HANDLERS, initial)
    assert tr.executed == [0, 1, 2] and tr.applied == [0, 1]
    assert st == initial  # nullifiers spent by the two children are gone


def test_missing_child_fails_closed():
    tx = _escrow_tx([ct.pn_transfer("V")])
    _, tr = ct.execute(tx, ct.ESCROW_HANDLERS, ct.funded_escrow_state())
    assert tr.reason == "missing child slot 1"


def test_unknown_selector_is_invalid_function():
    tx = ct.Call("escrow", 0x7F)
    _, tr = ct.execute(tx, ct.ESCROW_HANDLERS, {})
    assert tr.reason == "InvalidFunction"


def test_duplicate_nullifier_inside_one_transaction_is_caught():
    tx = _escrow_tx([ct.pn_transfer("V", nullifier="same"), ct.box_take("C_claim", nullifier="same")])
    _, tr = ct.execute(tx, {**ct.ESCROW_HANDLERS, ("box", 0x02): ct.ESCROW_HANDLERS[("promissory_note", 0x04)]},
                       ct.funded_escrow_state())
    assert tr.reason == "DuplicateNullifier" and tr.failed_at == 1


# --------------------------------------------------------------------------------------
# §3.3 -- proof-bound vs self-asserted wire fields (the real residual gap)
# --------------------------------------------------------------------------------------


def test_box_take_contents_commit_is_self_asserted():
    take = ct.box_take("C_claim")
    assert ct.self_asserted(take) == frozenset({"contents_commit"})
    assert ct.BOX_TAKE_PUBLIC == {"nullifier", "expected_root", "tx_binding", "tx_nonce"}


def test_any_box_with_the_right_wire_passes_escrow_wrong_object_check():
    lie = _escrow_tx([ct.pn_transfer("V"), ct.box_take("C_claim", nullifier="nf_some_other_box")])
    st, tr = ct.execute(lie, ct.ESCROW_HANDLERS, ct.funded_escrow_state())
    assert tr.accepted
    assert st[("escrow", "E1")]["state"] == "Claimed"


def test_but_the_wire_must_still_say_the_right_commitment():
    honest_wire = _escrow_tx([ct.pn_transfer("V"), ct.box_take("C_other")])
    _, tr = ct.execute(honest_wire, ct.ESCROW_HANDLERS, ct.funded_escrow_state())
    assert tr.reason.startswith("InvalidChildCall: not this escrow")


def test_purse_withdraw_amount_is_also_self_asserted():
    w = ct.purse_withdraw(100)
    assert "amount" in ct.self_asserted(w)
    assert "value_commit" not in ct.self_asserted(w)  # the Pedersen commitment *is* proof-bound


def test_pn_transfer_publishes_everything_the_parent_reads():
    pn = ct.pn_transfer("V")
    assert ct.self_asserted(pn) == frozenset()


# --------------------------------------------------------------------------------------
# §3.4 -- the Book-era Treasury-Only composition BUG-01 describes
# --------------------------------------------------------------------------------------


def test_book_treasury_spend_in_order_is_accepted():
    tx = ct.dao_treasury_spend_book([ct.purse_withdraw(100), ct.box_take("C_board")])
    st, tr = ct.execute(tx, ct.BOOK_DAO_HANDLERS, {"board_treasury_box": "C_board"})
    assert tr.accepted and st["treasury_spent"] == 100


def test_book_treasury_spend_reordered_is_rejected_atomically():
    """The brief's attack: Purse transfer 'before' the Box check.  Order is structural
    (post-order + slot), so the only way to reorder is to swap siblings -- caught."""
    tx = ct.dao_treasury_spend_book([ct.box_take("C_board"), ct.purse_withdraw(100)])
    st, tr = ct.execute(tx, ct.BOOK_DAO_HANDLERS, {"board_treasury_box": "C_board"})
    assert not tr.accepted and tr.failed_at == 2
    assert "treasury_spent" not in st
    assert ("purse_nullifiers", "nf_purse") not in st  # the withdraw was rolled back


def test_book_treasury_spend_with_a_lying_box_wire_is_accepted():
    """...and the same self-asserted field defeats the Book-era design too."""
    tx = ct.dao_treasury_spend_book([ct.purse_withdraw(100), ct.box_take("C_board", nullifier="nf_random_box")])
    st, tr = ct.execute(tx, ct.BOOK_DAO_HANDLERS, {"board_treasury_box": "C_board"})
    assert tr.accepted
