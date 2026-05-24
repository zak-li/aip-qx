"""Sorted Merkle tree for non-membership proofs (sanctions exclusion).

A sorted Merkle tree allows proving that a value is NOT present by showing
the two adjacent leaves that straddle it, plus the Merkle path for both.

This implementation builds the tree from a sorted list of names, hashed
at the leaf level, and provides:
  - build(names)  → MerkleTree
  - non_membership_proof(name) → NonMembershipProof | None
  - verify_non_membership(proof, root) → bool
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# ── hashing helpers ───────────────────────────────────────────────────────────

def _leaf_hash(value: str) -> bytes:
    return hashlib.sha256(b"LEAF:" + value.lower().encode()).digest()


def _node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"NODE:" + left + right).digest()


# ── tree ──────────────────────────────────────────────────────────────────────

@dataclass
class MerkleTree:
    sorted_names: list[str]
    leaves: list[bytes]           # hashed, sorted order
    root: bytes
    _levels: list[list[bytes]] = field(default_factory=list, repr=False)

    @classmethod
    def build(cls, names: list[str]) -> MerkleTree:
        sorted_names = sorted(set(n.lower() for n in names))
        leaves = [_leaf_hash(n) for n in sorted_names]

        if not leaves:
            leaves = [b"\x00" * 32]  # empty tree sentinel
            sorted_names = [""]

        levels = [leaves[:]]
        current = leaves[:]
        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), 2):
                left = current[i]
                r = current[i + 1] if i + 1 < len(current) else current[i]
                next_level.append(_node_hash(left, r))
            levels.append(next_level)
            current = next_level

        root = current[0]
        return cls(sorted_names=sorted_names, leaves=leaves, root=root, _levels=levels)

    def _merkle_path(self, leaf_index: int) -> list[dict]:
        path = []
        idx = leaf_index
        for level in self._levels[:-1]:
            if idx % 2 == 0:
                sibling_idx = idx + 1 if idx + 1 < len(level) else idx
                path.append({"hash": level[sibling_idx].hex(), "side": "right"})
            else:
                path.append({"hash": level[idx - 1].hex(), "side": "left"})
            idx //= 2
        return path

    def non_membership_proof(self, name: str) -> NonMembershipProof | None:
        """Return proof that name is not in the tree, or None if it IS in it."""
        key = name.lower()

        # Binary-search for insertion point
        lo, hi = 0, len(self.sorted_names) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.sorted_names[mid] == key:
                return None  # value IS present → cannot prove non-membership
            elif self.sorted_names[mid] < key:
                lo = mid + 1
            else:
                hi = mid - 1

        # lo is the insertion index; the straddling leaves are lo-1 and lo
        left_idx  = max(lo - 1, 0)
        right_idx = min(lo, len(self.sorted_names) - 1)

        return NonMembershipProof(
            queried_name=name,
            left_leaf_name=self.sorted_names[left_idx],
            right_leaf_name=self.sorted_names[right_idx],
            left_leaf_hash=self.leaves[left_idx].hex(),
            right_leaf_hash=self.leaves[right_idx].hex(),
            left_path=self._merkle_path(left_idx),
            right_path=self._merkle_path(right_idx),
            root=self.root.hex(),
        )


@dataclass(slots=True)
class NonMembershipProof:
    queried_name: str
    left_leaf_name: str
    right_leaf_name: str
    left_leaf_hash: str
    right_leaf_hash: str
    left_path: list[dict]
    right_path: list[dict]
    root: str

    def to_dict(self) -> dict:
        return {
            "queried_name":     self.queried_name,
            "left_leaf_name":   self.left_leaf_name,
            "right_leaf_name":  self.right_leaf_name,
            "left_leaf_hash":   self.left_leaf_hash,
            "right_leaf_hash":  self.right_leaf_hash,
            "left_path":        self.left_path,
            "right_path":       self.right_path,
            "root":             self.root,
        }


def _verify_path(leaf_hash: bytes, path: list[dict], expected_root: str) -> bool:
    current = leaf_hash
    for step in path:
        sibling = bytes.fromhex(step["hash"])
        if step["side"] == "right":
            current = _node_hash(current, sibling)
        else:
            current = _node_hash(sibling, current)
    return current.hex() == expected_root


def verify_non_membership(proof: NonMembershipProof, expected_root: str) -> bool:
    """Stateless verification of a non-membership proof."""
    # 1. Leaf hashes must match declared names
    if _leaf_hash(proof.left_leaf_name).hex() != proof.left_leaf_hash:
        return False
    if _leaf_hash(proof.right_leaf_name).hex() != proof.right_leaf_hash:
        return False

    # 2. Queried name must sort strictly between the two straddling leaves
    key = proof.queried_name.lower()
    if not (proof.left_leaf_name.lower() <= key <= proof.right_leaf_name.lower()):
        return False
    if proof.left_leaf_name.lower() == key or proof.right_leaf_name.lower() == key:
        return False  # name is actually a leaf — membership, not absence

    # 3. Both Merkle paths must resolve to the same root
    left_ok  = _verify_path(bytes.fromhex(proof.left_leaf_hash),  proof.left_path,  expected_root)
    right_ok = _verify_path(bytes.fromhex(proof.right_leaf_hash), proof.right_path, expected_root)

    return left_ok and right_ok and proof.root == expected_root


# ── sanctions tree loader ─────────────────────────────────────────────────────

_cached_tree: MerkleTree | None = None

def get_sanctions_tree() -> MerkleTree:
    global _cached_tree
    if _cached_tree is not None:
        return _cached_tree

    from core.features.compliance.fixtures_loader import get_sanctions_lists

    all_names: list[str] = []
    for lst in get_sanctions_lists().values():
        all_names.extend(str(e) for e in lst)

    _cached_tree = MerkleTree.build(all_names)
    return _cached_tree


def invalidate_sanctions_cache() -> None:
    global _cached_tree
    _cached_tree = None
