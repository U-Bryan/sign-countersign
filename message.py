"""Message format, canonical bytes for signing, and rendering for LLM agents.

The shape follows A2A's message (message id, task id, sender and recipient roles,
a structured data part), so the work transfers to the real protocol.

`origin` is harness ground truth (honest | mallory | mallory_modified | mallory_replay | harness).
Defences, agents and renderers must never read it (tests/test_no_origin_leak.py).
"""
from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from random import Random

# Body kinds
GET_BANK_DETAILS = "get_bank_details"
BANK_DETAILS = "bank_details"
PAY_INVOICE = "pay_invoice"
PAYMENT_RESULT = "payment_result"
HS_HELLO = "hs_hello"
HS_CODE = "hs_code"
HS_COUNTERCODE = "hs_countercode"
HS_RESULT = "hs_result"
NOTICE = "notice"
HANDSHAKE_KINDS = frozenset({HS_HELLO, HS_CODE, HS_COUNTERCODE, HS_RESULT})
AGENT_KINDS = frozenset({GET_BANK_DETAILS, BANK_DETAILS, PAY_INVOICE, PAYMENT_RESULT})

AGENTS = ("orchestrator", "records", "finance")


@dataclass
class Message:
    msg_id: str
    sender: str
    recipient: str
    timestamp_ms: int
    task_id: str
    body: dict
    auth: dict = field(default_factory=dict)
    origin: str = field(default="honest", repr=False, compare=False)

    @property
    def kind(self) -> str:
        return str(self.body.get("kind", ""))

    def copy(self, **changes) -> "Message":
        m = Message(
            msg_id=self.msg_id,
            sender=self.sender,
            recipient=self.recipient,
            timestamp_ms=self.timestamp_ms,
            task_id=self.task_id,
            body=copy.deepcopy(self.body),
            auth=copy.deepcopy(self.auth),
            origin=self.origin,
        )
        for k, v in changes.items():
            setattr(m, k, v)
        return m

    def to_dict(self) -> dict:
        """Wire form (no origin)."""
        return {
            "msg_id": self.msg_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "timestamp_ms": self.timestamp_ms,
            "task_id": self.task_id,
            "body": copy.deepcopy(self.body),
            "auth": copy.deepcopy(self.auth),
        }

    def to_log(self) -> dict:
        """Harness log form: wire form plus the ground-truth origin label."""
        d = self.to_dict()
        d["origin"] = self.origin
        return d


def canonical_bytes(msg: Message, include_auth_fields: tuple[str, ...] = ()) -> bytes:
    payload = {
        "msg_id": msg.msg_id,
        "sender": msg.sender,
        "recipient": msg.recipient,
        "timestamp_ms": msg.timestamp_ms,
        "task_id": msg.task_id,
        "body": msg.body,
    }
    for k in include_auth_fields:
        payload["auth_" + k] = msg.auth[k]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def new_msg_id(rng: Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def new_hex(rng: Random, nbytes: int = 16) -> str:
    return f"{rng.getrandbits(nbytes * 8):0{nbytes * 2}x}"


# ----- money --------------------------------------------------------------
def pence_to_gbp_str(pence: int) -> str:
    sign = "-" if pence < 0 else ""
    p = abs(int(pence))
    return f"{sign}{p // 100}.{p % 100:02d}"


def parse_gbp_to_pence(value) -> int | None:
    """'1200', '1,200.00', '£1,200.00', 'GBP 1200', 1200, 1200.0 -> 120000. None if unparseable."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value * 100
    if isinstance(value, float):
        value = repr(value)
    s = str(value).strip().replace("£", "").replace(",", "").replace(" ", "")
    if s.upper().startswith("GBP"):
        s = s[3:]
    if s.upper().endswith("GBP"):
        s = s[:-3]
    if not s:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    if not d.is_finite():
        return None
    return int((d * 100).quantize(Decimal("1")))


# ----- rendering for LLM agents ---------------------------------------------
def render_body(body: dict) -> dict:
    """What an agent sees of a body: amounts as GBP strings, 'kind' first, other keys sorted."""
    shown = {}
    if "kind" in body:
        shown["kind"] = body["kind"]
    for k in sorted(body):
        if k == "kind":
            continue
        if k == "amount_pence":
            shown["amount_gbp"] = pence_to_gbp_str(int(body[k]))
        else:
            shown[k] = body[k]
    return shown


def render_for_agent(msg: Message) -> str:
    """Identical under every defence: no auth fields, no origin."""
    content = json.dumps(render_body(msg.body), ensure_ascii=False)
    return (
        "A message has arrived on the agent bus.\n"
        f"from: {msg.sender}\n"
        f"to: {msg.recipient}\n"
        f"task_id: {msg.task_id}\n"
        f"content: {content}\n"
    )
