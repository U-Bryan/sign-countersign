"""Per-agent Ed25519 keys and the public registry (D2/D3).

Keys are generated fresh per trial and kept in memory only. The registry holds public
keys and the authorisation table (who may send which message kinds to whom).
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

MAY_SEND = {
    "orchestrator": {"records": ["get_bank_details"], "finance": ["pay_invoice"]},
    "records": {"orchestrator": ["bank_details"]},
    "finance": {"orchestrator": ["payment_result"]},
}


def public_b64(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def generate(agents) -> tuple[dict[str, Ed25519PrivateKey], dict]:
    keys = {a: Ed25519PrivateKey.generate() for a in agents}
    registry = {"agents": {a: {"public_key_b64": public_b64(keys[a]), "may_send": MAY_SEND.get(a, {})}
                           for a in agents}}
    return keys, registry


def public_key(registry: dict, agent: str) -> Ed25519PublicKey | None:
    entry = registry.get("agents", {}).get(agent)
    if entry is None:
        return None
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(entry["public_key_b64"]))


def export_registry(registry: dict, path: Path | str) -> None:
    """Write the public registry (no private material exists in it by construction)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
