"""S2_FIX_B.md is frozen (version B1, 2026-10-12): the fix, the expectations, the sets,
the conditions, the metrics and the decision rule must not change silently once runs can start.

Changing the file is allowed only as a new version: write S2_FIX_B2 (or bump the version in the file), record
why in JOURNAL.md, and update FROZEN_SHA256 in the same commit. Set hashes live in S2_FIX_B_SETS.json, not here.
"""
import hashlib
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "S2_FIX_B.md"
FROZEN_SHA256 = "c7da5f472b92629dd5fc9abeec004d4040f014e1654f0b6fb9269e29954ffe71"   # version B1, wording of 2026-10-13


def test_frozen_spec_is_unchanged():
    assert hashlib.sha256(SPEC.read_bytes()).hexdigest() == FROZEN_SHA256, \
        "S2_FIX_B.md changed after freezing: make it a new version (see this file's docstring)"
