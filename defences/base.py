"""Common interface for all defences.

Defences run in the transport layer, outside the LLM. They must never read
`Message.origin` (harness ground truth) - see tests/test_no_origin_leak.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bus import Accept, Reject
from message import HS_RESULT, Message, new_msg_id


@dataclass(frozen=True)
class PaymentRequest:
    invoice_id: str
    account: str
    amount_pence: int


@dataclass
class Allow:
    rules_checked: list[str] = field(default_factory=list)


@dataclass
class Block:
    first_rule: str
    rules_failed: list[str]
    detail: str = ""


class Defence:
    name = "base"
    uses_monitor = False

    def setup(self, world, clock, rng, agents, cfg, logger) -> None:
        self.world, self.clock, self.rng, self.agents, self.cfg, self.log = world, clock, rng, agents, cfg, logger

    def prepare_outgoing(self, msg: Message, bus, in_reply_to: Message | None = None) -> Message:
        return msg

    def verify_incoming(self, msg: Message, receiver: str) -> Accept | Reject:
        return Accept(msg.sender, "claimed")

    def handle_handshake(self, msg: Message, receiver: str, bus) -> Message:
        """Only D1 runs handshakes. Anyone else gets an 'unsupported' result."""
        return Message(
            msg_id=new_msg_id(self.rng), sender=receiver, recipient=msg.sender,
            timestamp_ms=self.clock.agent_now_ms(receiver), task_id=msg.task_id,
            body={"kind": HS_RESULT, "status": "unsupported"}, origin="honest",
        )

    def payment_gate(self, request: PaymentRequest, trigger: Message, verdict: Accept) -> Allow | Block:
        return Allow()

    def end_task(self) -> None:
        pass

    def credential_for(self, agent: str):
        """What Mallory steals in A4 (None when the defence has no credentials)."""
        return None

    def impostor(self, agent: str, credential):
        """A4-lie: an object Mallory uses to answer as `agent` with a stolen credential."""
        return NullImpostor(agent, self)


class NullImpostor:
    """D0: no credentials needed; replies go out as they are."""

    def __init__(self, agent: str, defence: Defence):
        self.agent = agent
        self.defence = defence

    def handle_handshake(self, msg: Message) -> Message:
        return self.defence.handle_handshake(msg, self.agent, None)

    def prepare_reply(self, reply: Message, in_reply_to: Message) -> Message:
        return reply
