"""Small builders shared by the defence tests."""
from __future__ import annotations

from random import Random

from bus import Bus
from clock import SimClock
from defences import make_defence
from message import AGENTS, Message, new_msg_id
from runlog import RunLogger
from world import World

# A start time exactly on a 30-second TOTP step boundary.
STEP_START_MS = 1_794_000_000_000 - (1_794_000_000_000 % 30_000)


class Env:
    def __init__(self, defence_name: str, cfg, tmp_path, start_ms: int = STEP_START_MS, seed: int = 99):
        self.rng = Random(seed)
        self.clock = SimClock(start_ms, real_time=False)
        self.log = RunLogger(tmp_path / f"{defence_name.replace('+', 'p')}.jsonl", "t", self.clock)
        self.world = World(self.clock, self.log)
        self.defence = make_defence(defence_name)
        self.defence.setup(self.world, self.clock, self.rng, list(AGENTS), cfg, self.log)
        self.bus = Bus(self.clock, self.defence, self.log, self.rng)
        self.bus.register_endpoint("records", self._records)
        self.bus.register_endpoint("finance", self._finance)
        self.bus.register_endpoint("orchestrator", lambda m, v: None)
        self.handled: list[tuple[Message, object]] = []

    def _records(self, msg, verdict):
        self.handled.append((msg, verdict))
        return self.msg("records", msg.sender, {"kind": "bank_details", "supplier": "Acme Ltd",
                                                "bank_account": "GB-ACME-001", "notes": ""})

    def _finance(self, msg, verdict):
        self.handled.append((msg, verdict))
        return self.msg("finance", msg.sender, {"kind": "payment_result", "invoice_id": "INV-104",
                                                "status": "paid", "detail": ""})

    def msg(self, sender, recipient, body, task_id="T-1") -> Message:
        return Message(new_msg_id(self.rng), sender, recipient, self.clock.agent_now_ms(sender), task_id, body)

    def get_bank(self, sender="orchestrator") -> Message:
        return self.msg(sender, "records", {"kind": "get_bank_details", "invoice_id": "INV-104",
                                            "supplier": "Acme Ltd"})

    def pay(self, sender="orchestrator", account="GB-ACME-001", amount=120000) -> Message:
        return self.msg(sender, "finance", {"kind": "pay_invoice", "invoice_id": "INV-104",
                                            "supplier": "Acme Ltd", "account": account, "amount_pence": amount})

    def events(self, name):
        return self.log.of(name)
