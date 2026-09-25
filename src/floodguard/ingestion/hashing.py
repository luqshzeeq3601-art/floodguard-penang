"""Deterministic content hashes and canonical JSON encoding for raw artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_hex(data: bytes) -> str:
    """SHA-256 of payload bytes exactly as received (no decoding or newline translation)."""
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    """Stable JSON text: sorted keys, no insignificant whitespace, UTF-8 kept verbatim."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def jsonl_bytes(objs: list[dict[str, Any]]) -> bytes:
    """Canonical JSON Lines (``\\n`` terminated); identical input -> identical bytes."""
    return "".join(canonical_json(o) + "\n" for o in objs).encode("utf-8")
