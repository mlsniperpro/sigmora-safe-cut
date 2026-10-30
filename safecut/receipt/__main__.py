"""``python -m safecut.receipt verify <receipt.json> [<receipt.json> …]``: check a receipt chain (oldest first).

Exit 0 and ``chain ok`` when every hash holds and each receipt links to the one before it; exit 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

from safecut.contracts import ContractError, Receipt, load
from safecut.receipt.build import verify_chain


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "verify":
        print("usage: python -m safecut.receipt verify <receipt.json> [<receipt.json> ...]", file=sys.stderr)
        return 2
    try:
        receipts = [load(Path(p), Receipt) for p in argv[1:]]
    except ContractError as exc:
        print(f"invalid: {exc}")
        return 1
    ok = verify_chain(receipts)
    print("chain ok" if ok else "chain broken")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
