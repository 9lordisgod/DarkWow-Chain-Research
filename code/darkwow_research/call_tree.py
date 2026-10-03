"""A model of DarkWow's transaction call tree and sequential execution.

Mirrors three pieces of the node, each a few dozen lines upstream:

* ``src/sdk/src/dark_tree.rs`` -- a transaction is a *DarkTree*: every
  ``ContractCall`` is a ``DarkLeaf`` carrying ``parent_index`` and
  ``children_indexes``, and the on-wire order is a **depth-first post-order**
  (children before their parent, root last).  Sibling order is whatever the
  builder chose.
* ``src/linear/src/zk_verifier.rs::decode_and_reconcile`` -- the witness tree
  must describe exactly the chain calls (same parent / children indexes), at
  most 255 calls.
* ``src/linear/src/execution.rs`` -- calls run **in wire order**, one at a time,
  over one shared overlay: ``metadata()`` -> ``exec()`` -> ``apply(update)``;
  call *n* sees the writes of calls *1..n-1*; the first failure reverts the
  checkpoint and rejects the whole transaction.

The model is enough to settle BUG-01 ("execution reordering bypass"): there is
no scheduler, no dependency graph and no notion of a call inside zkas.  A
parent that needs a child's effect reads the child *by slot* from
``children_indexes`` and checks selector, contract id and parameters itself.
Reordering siblings changes which slot holds what, and the parent's slot check
fails; a child that lands before its parent cannot "escape" because the
parent's failure reverts it.  The only thing ordering cannot give a parent is a
*fact* the child's wire does not carry -- which is where the real gap is
(``escrow::ClaimV1`` vs ``TakeParams.contents_commit``, see ``self_asserted``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

MAX_TX_CALLS = 20                 # src/tx/mod.rs, client-side builder limit
MAX_CALLS_BY_INDEX_ENCODING = 255  # src/linear/src/zk_verifier.rs, on-chain (u8 indexes)


# --------------------------------------------------------------------------------------
# tree
# --------------------------------------------------------------------------------------


@dataclass
class Call:
    """One contract call: ``data[0]`` is the selector, the rest the params."""

    contract: str
    selector: int
    params: dict = field(default_factory=dict)
    children: list["Call"] = field(default_factory=list)
    # fields the proof actually publishes (constrain_instance); everything else on the
    # wire is self-asserted by the builder.  Default: nothing proof-bound.
    proof_bound: frozenset[str] = frozenset()

    def child(self, c: "Call") -> "Call":
        self.children.append(c)
        return self


@dataclass(frozen=True)
class Leaf:
    """``DarkLeaf<ContractCall>`` after flattening."""

    index: int
    call: Call
    parent_index: int | None
    children_indexes: tuple[int, ...]


def flatten(root: Call) -> list[Leaf]:
    """DFS post-order, as ``DarkTree::build`` produces it: children first, root last."""
    out: list[Leaf] = []

    def visit(c: Call, parent: int | None) -> int:
        # children are visited in builder order, each getting its index before the parent
        child_idx: list[int] = []
        for ch in c.children:
            child_idx.append(visit(ch, None))
        idx = len(out)
        out.append(Leaf(idx, c, parent, tuple(child_idx)))
        return idx

    visit(root, None)
    # second pass: fill parent indexes now that every child knows its own index
    by_child = {ci: leaf.index for leaf in out for ci in leaf.children_indexes}
    return [Leaf(l.index, l.call, by_child.get(l.index), l.children_indexes) for l in out]


def is_post_order(leaves: Iterable[Leaf]) -> bool:
    leaves = list(leaves)
    return all(ci < l.index for l in leaves for ci in l.children_indexes) and \
        leaves[-1].parent_index is None


def reconcile(leaves: list[Leaf]) -> None:
    """``decode_and_reconcile``: structural checks the node performs before any proof."""
    if not leaves:
        raise ValueError("empty transaction")
    if len(leaves) > MAX_CALLS_BY_INDEX_ENCODING:
        raise ValueError("too many calls for u8 indexes")
    for l in leaves:
        for ci in l.children_indexes:
            if not (0 <= ci < len(leaves)) or leaves[ci].parent_index != l.index:
                raise ValueError(f"child {ci} of {l.index} does not point back")
        if l.parent_index is not None and l.index not in leaves[l.parent_index].children_indexes:
            raise ValueError(f"call {l.index} claims parent {l.parent_index}")
    if not is_post_order(leaves):
        raise ValueError("not post-order")


# --------------------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------------------


class ExecError(Exception):
    def __init__(self, call_index: int, reason: str):
        super().__init__(f"call[{call_index}] {reason}")
        self.call_index = call_index
        self.reason = reason


# A handler sees (leaf, all leaves, state) and may raise ExecError.  It returns the
# update to apply (a dict merged into state) -- the ``[selector | update]`` of exec().
Handler = Callable[[Leaf, list[Leaf], dict], dict]


@dataclass
class Trace:
    executed: list[int] = field(default_factory=list)
    applied: list[int] = field(default_factory=list)
    failed_at: int | None = None
    reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.failed_at is None


def execute(root: Call, handlers: dict[tuple[str, int], Handler],
            state: dict | None = None) -> tuple[dict, Trace]:
    """Run a transaction the way ``execution.rs`` does; return (final_state, trace).

    On failure the *initial* state is returned -- the checkpoint is reverted and the
    transaction is rejected as a whole (atomicity).  Writes of earlier calls are visible
    to later ones while the transaction is in flight.
    """
    initial = dict(state or {})
    overlay = dict(initial)
    leaves = flatten(root)
    reconcile(leaves)
    tr = Trace()
    for leaf in leaves:
        tr.executed.append(leaf.index)
        h = handlers.get((leaf.call.contract, leaf.call.selector))
        try:
            if h is None:
                raise ExecError(leaf.index, "InvalidFunction")
            update = h(leaf, leaves, overlay)
        except ExecError as e:
            tr.failed_at, tr.reason = leaf.index, e.reason
            return initial, tr
        overlay.update(update)
        tr.applied.append(leaf.index)
    return overlay, tr


# --------------------------------------------------------------------------------------
# what a parent can and cannot learn from a child
# --------------------------------------------------------------------------------------


def self_asserted(call: Call) -> frozenset[str]:
    """Wire fields of ``call`` that no proof constrains -- a parent reading them trusts the builder."""
    return frozenset(call.params) - call.proof_bound


def expect_child(leaf: Leaf, leaves: list[Leaf], slot: int, contract: str, selector: int) -> Leaf:
    """The idiom every DarkWow parent uses: ``children_indexes[slot]`` must be *this* call."""
    if slot >= len(leaf.children_indexes):
        raise ExecError(leaf.index, f"missing child slot {slot}")
    child = leaves[leaf.children_indexes[slot]]
    if child.call.contract != contract:
        raise ExecError(leaf.index, f"slot {slot}: wrong contract {child.call.contract}")
    if child.call.selector != selector:
        raise ExecError(leaf.index, f"slot {slot}: wrong selector 0x{child.call.selector:02x}")
    return child


# --------------------------------------------------------------------------------------
# the two compositions the note studies
# --------------------------------------------------------------------------------------

# Box::Take publishes only (nullifier, expected_root, tx_binding, tx_nonce).
BOX_TAKE_PUBLIC = frozenset({"nullifier", "expected_root", "tx_binding", "tx_nonce"})
# Purse::Withdraw publishes its Pedersen commitments, roots, nullifier, derived id + tx pair.
PURSE_WITHDRAW_PUBLIC = frozenset({"nullifier", "expected_root", "new_leaf", "value_commit",
                                   "derived_purse_id", "tx_binding", "tx_nonce"})
PN_TRANSFER_PUBLIC = frozenset({"nullifier", "coin", "value_commit", "tx_binding", "tx_nonce"})


def box_take(contents_commit: str, nullifier: str = "nf_box") -> Call:
    return Call("box", 0x02, {"contents_commit": contents_commit, "nullifier": nullifier,
                              "expected_root": "root", "tx_binding": "txb", "tx_nonce": "txn"},
                proof_bound=BOX_TAKE_PUBLIC)


def pn_transfer(value_commit: str, nullifier: str = "nf_pn") -> Call:
    return Call("promissory_note", 0x04, {"nullifier": nullifier, "coin": "coin",
                                          "value_commit": value_commit, "tx_binding": "txb",
                                          "tx_nonce": "txn"}, proof_bound=PN_TRANSFER_PUBLIC)


def escrow_claim(escrow_id: str, children: list[Call]) -> Call:
    c = Call("escrow", 0x03, {"escrow_id": escrow_id, "spent_nullifier": "nf_seller",
                              "escrow_seller_commitment": "seller_c"},
             proof_bound=frozenset({"escrow_id", "escrow_seller_commitment", "spent_nullifier",
                                    "tx_binding", "tx_nonce"}))
    for ch in children:
        c.child(ch)
    return c


def _nullifier_handler(tree: str) -> Handler:
    def h(leaf: Leaf, leaves: list[Leaf], st: dict) -> dict:
        nf = leaf.call.params["nullifier"]
        if (tree, nf) in st:
            raise ExecError(leaf.index, "DuplicateNullifier")
        return {(tree, nf): True}
    return h


def escrow_claim_handler(leaf: Leaf, leaves: list[Leaf], st: dict) -> dict:
    """``escrow::ClaimV1`` at d775e37c, entrypoint.rs 507-618, condensed to its checks."""
    pn = expect_child(leaf, leaves, 0, "promissory_note", 0x04)
    bx = expect_child(leaf, leaves, 1, "box", 0x02)
    rec = st.get(("escrow", leaf.call.params["escrow_id"]))
    if rec is None:
        raise ExecError(leaf.index, "EscrowNotFound")
    # wrong-object check: compares a wire field the Take proof does NOT publish
    if bx.call.params["contents_commit"] != rec["claim_box_contents"]:
        raise ExecError(leaf.index, "InvalidChildCall: not this escrow's claim capability")
    if rec["state"] != "Funded":
        raise ExecError(leaf.index, "InvalidStateTransition")
    if ("escrow_spent", leaf.call.params["spent_nullifier"]) in st:
        raise ExecError(leaf.index, "AlreadySpent")
    if pn.call.params["value_commit"] != rec["value_commit"]:
        raise ExecError(leaf.index, "InvalidChildCall: value commitment")
    new = dict(rec, state="Claimed")
    return {("escrow", leaf.call.params["escrow_id"]): new,
            ("escrow_spent", leaf.call.params["spent_nullifier"]): True}


ESCROW_HANDLERS: dict[tuple[str, int], Handler] = {
    ("box", 0x02): _nullifier_handler("box_nullifiers"),
    ("promissory_note", 0x04): _nullifier_handler("pn_nullifiers"),
    ("escrow", 0x03): escrow_claim_handler,
}


def funded_escrow_state(escrow_id: str = "E1", claim_box_contents: str = "C_claim",
                        value_commit: str = "V") -> dict:
    return {("escrow", escrow_id): {"state": "Funded", "claim_box_contents": claim_box_contents,
                                    "value_commit": value_commit}}


# --- the Book-era dao_escrow "Treasury-Only" composition BUG-01 describes -------------

def dao_treasury_spend_book(children: list[Call]) -> Call:
    """Book p. 1142: TreasurySpendV1 with Purse::WithdrawV1 and Box::TakeV1 (board_treasury) children."""
    c = Call("dao_escrow", 0x05, {"proposal": "P", "amount": 100})
    for ch in children:
        c.child(ch)
    return c


def purse_withdraw(amount: int, nullifier: str = "nf_purse") -> Call:
    return Call("purse", 0x02, {"amount": amount, "nullifier": nullifier, "expected_root": "root",
                                "new_leaf": "leaf'", "value_commit": f"V({amount})",
                                "derived_purse_id": "dp", "tx_binding": "txb", "tx_nonce": "txn"},
                proof_bound=PURSE_WITHDRAW_PUBLIC)


def dao_treasury_spend_book_handler(leaf: Leaf, leaves: list[Leaf], st: dict) -> dict:
    """What a correctly written Book-era parent must do: read both children by slot."""
    withdraw = expect_child(leaf, leaves, 0, "purse", 0x02)
    take = expect_child(leaf, leaves, 1, "box", 0x02)
    if withdraw.call.params["amount"] != leaf.call.params["amount"]:
        raise ExecError(leaf.index, "InvalidChildCall: amount")
    if take.call.params["contents_commit"] != st.get("board_treasury_box"):
        raise ExecError(leaf.index, "InvalidChildCall: not the board_treasury capability")
    return {"treasury_spent": st.get("treasury_spent", 0) + leaf.call.params["amount"]}


BOOK_DAO_HANDLERS: dict[tuple[str, int], Handler] = {
    ("purse", 0x02): _nullifier_handler("purse_nullifiers"),
    ("box", 0x02): _nullifier_handler("box_nullifiers"),
    ("dao_escrow", 0x05): dao_treasury_spend_book_handler,
}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _main() -> None:  # pragma: no cover
    tx = escrow_claim("E1", [pn_transfer("V"), box_take("C_claim")])
    leaves = flatten(tx)
    print("post-order:", [(l.index, l.call.contract, hex(l.call.selector), l.parent_index,
                           l.children_indexes) for l in leaves])
    st, tr = execute(tx, ESCROW_HANDLERS, funded_escrow_state())
    print("in order  ->", "accepted" if tr.accepted else f"rejected: {tr.reason}")
    swapped = escrow_claim("E1", [box_take("C_claim"), pn_transfer("V")])
    st, tr = execute(swapped, ESCROW_HANDLERS, funded_escrow_state())
    print("swapped   ->", "accepted" if tr.accepted else f"rejected: {tr.reason}")
    lie = escrow_claim("E1", [pn_transfer("V"), box_take("C_claim", nullifier="nf_other_box")])
    st, tr = execute(lie, ESCROW_HANDLERS, funded_escrow_state())
    print("any box, right wire ->", "accepted" if tr.accepted else f"rejected: {tr.reason}",
          "| self-asserted:", sorted(self_asserted(lie.children[1])))


if __name__ == "__main__":  # pragma: no cover
    _main()
