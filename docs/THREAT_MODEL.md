# Threat model

Mallory's powers are enforced in code (`attacks.MalloryAPI`): each attack can call only the capabilities in its row, and `tests/test_attacks.py` checks that every other call raises `CapabilityError`.

| Attack | Inject messages | Read replies to her own messages | Observe bus traffic | Modify or drop in transit | Hijack an endpoint | Credentials held | Write to world data |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1-guess | ✓ | ✗ (blind by design) | ✗ | ✗ | ✗ | none | ✗ |
| A1-reflect | ✓ | ✓ | ✗ | ✗ | ✗ | none | ✗ |
| A2-fast / A2-slow | ✓ | ✓ | ✓ (records) | ✗ | ✗ | none | ✗ |
| A3 | ✓ | ✓ | ✓ | ✓ | ✗ | none | ✗ |
| A4-direct | ✓ | ✓ | ✗ | ✗ | ✗ | the records agent's credential (D1: the shared TOTP secret; D2/D3: records' private key) | ✗ |
| A4-lie | ✓ | ✓ | ✗ | ✗ | ✓ (only the `records` endpoint) | as A4-direct | ✗ |
| A5 (all variants) | ✗ | ✗ | ✗ | ✗ | ✗ | none | ✓ (one supplier record only) |

**Trusted:** the harness, the world's ground truth (invoice table, ledger, user-task registry), the key registry, the monitor, and the honest agents' code. The honest agents' **LLM judgement is not trusted**; that is the point of A5.

**Public knowledge:** the protocols and algorithms (TOTP, Ed25519, the message format), and the target invoice's ID, supplier and amount (a fraudster holding a copy of the invoice). Mallory does not know a task ID unless she observes it on the bus.

**Out of scope:** poisoning the monitor's source of truth, compromising the orchestrator's or finance agent's keys, side channels, denial of service as a goal (measured as a side effect, not a success), and real networks.
