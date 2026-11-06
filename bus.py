"""Transport layer: routing, defence checks, Mallory's hooks and logging.

Order of operations for every message (requests and replies alike):
 1. defence.prepare_outgoing on the sender's side (D1 may run a handshake; D2 signs)
 2. log "sent"
 3. Mallory's transit hooks (observe / modify / drop), if her capabilities include them
 4. route to the endpoint (honest agent, or Mallory's handler if hijacked)
 5. defence.verify_incoming on the receiver's side -> Accept or Reject (all checks run)
 6. handler builds the reply, which goes back through steps 1-5 in the other direction
A message that fails verification never reaches the recipient's LLM. The sender gets a
generic notice: "delivery failed: rejected by recipient".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from message import HANDSHAKE_KINDS, NOTICE, Message, new_msg_id

REJECTED_NOTICE = "delivery failed: rejected by recipient"


@dataclass
class Accept:
    attributed_sender: str
    basis: str  # "claimed" | "channel" | "verified" | "mallory"
    passed_checks: list[str] = field(default_factory=list)


@dataclass
class Reject:
    failed_checks: list[str]
    detail: str = ""


class HandshakeFailed(Exception):
    def __init__(self, failed_checks: list[str]):
        super().__init__(", ".join(failed_checks))
        self.failed_checks = failed_checks


Handler = Callable[[Message, Accept], "Message | None"]
TransitHook = Callable[[Message, str], "Message | None"]


def _diff(a: Message, b: Message) -> dict:
    """Field-level diff between two versions of a message (for the 'modified' log event)."""
    out = {}
    da, db = a.to_dict(), b.to_dict()
    for k in da:
        if k == "body":
            for bk in sorted(set(da["body"]) | set(db["body"])):
                if da["body"].get(bk) != db["body"].get(bk):
                    out[f"body.{bk}"] = [da["body"].get(bk), db["body"].get(bk)]
        elif da[k] != db[k]:
            out[k] = [da[k], db[k]]
    return out


class Bus:
    def __init__(self, clock, defence, logger, rng):
        self.clock = clock
        self.defence = defence
        self.log = logger
        self.rng = rng
        self._endpoints: dict[str, Handler] = {}
        self._hijacked: dict[str, Handler] = {}
        self._transit_hooks: list[TransitHook] = []
        self.stats = {"messages": 0, "handshake_messages": 0, "rejected": 0}

    # ----- wiring ---------------------------------------------------------
    def register_endpoint(self, name: str, handler: Handler) -> None:
        self._endpoints[name] = handler

    def hijack_endpoint(self, name: str, handler: Handler) -> None:
        """A4-lie only, reached through MalloryAPI."""
        self._hijacked[name] = handler
        self.log.log("attack_step", step="hijack_endpoint", endpoint=name)

    def add_transit_hook(self, fn: TransitHook) -> None:
        """A2 (observe) and A3 (modify), reached through MalloryAPI."""
        self._transit_hooks.append(fn)

    def notice(self, about: Message, text: str) -> Message:
        return Message(
            msg_id=new_msg_id(self.rng), sender="bus", recipient=about.sender,
            timestamp_ms=self.clock.now_ms(), task_id=about.task_id,
            body={"kind": NOTICE, "text": text}, origin="harness",
        )

    # ----- entry points ---------------------------------------------------
    def request(self, msg: Message) -> Message:
        """An honest agent sends msg; returns the verified reply, or a notice."""
        t0 = time.perf_counter_ns()
        try:
            msg = self.defence.prepare_outgoing(msg, self)
        except HandshakeFailed as e:
            self.log.log("send_failed", msg=msg.to_log(), failed_checks=e.failed_checks,
                         defence_ns=time.perf_counter_ns() - t0)
            return self.notice(msg, REJECTED_NOTICE)
        prep_ns = time.perf_counter_ns() - t0
        return self._transmit(msg, prep_ns, caller_is_mallory=False)

    def inject(self, msg: Message, deliver_to: str | None = None) -> Message:
        """Mallory's entry point. No defence preparation: she builds any auth herself.
        The reply to her own message is returned to her unverified."""
        if msg.origin == "honest":
            msg.origin = "mallory"
        self.log.log("injected", msg=msg.to_log(), deliver_to=deliver_to or msg.recipient)
        return self._transmit(msg, 0, caller_is_mallory=True, deliver_to=deliver_to)

    # ----- internals --------------------------------------------------------
    def _count(self, msg: Message) -> None:
        self.stats["messages"] += 1
        if msg.kind in HANDSHAKE_KINDS:
            self.stats["handshake_messages"] += 1

    def _run_hooks(self, msg: Message, leg: str) -> Message | None:
        for hook in self._transit_hooks:
            before = msg.copy()
            out = hook(msg, leg)
            if out is None:
                self.log.log("dropped", leg=leg, msg=before.to_log())
                return None
            changes = _diff(before, out)
            if changes:
                if out.origin == "honest":
                    out.origin = "mallory_modified"
                self.log.log("modified", leg=leg, msg_id=out.msg_id, changes=changes, msg=out.to_log())
            msg = out
        return msg

    def _transmit(self, msg: Message, prep_ns: int, caller_is_mallory: bool,
                  deliver_to: str | None = None) -> Message:
        self._count(msg)
        self.log.log("sent", leg="request", msg=msg.to_log(), defence_ns=prep_ns)
        routed = self._run_hooks(msg, "request")
        if routed is None:
            return self.notice(msg, REJECTED_NOTICE)
        msg = routed
        dest = deliver_to or msg.recipient
        handler = self._hijacked.get(dest)
        hijacked = handler is not None
        if handler is None:
            handler = self._endpoints.get(dest)
        if handler is None:
            self.log.log("undeliverable", msg=msg.to_log(), dest=dest)
            return self.notice(msg, "delivery failed: unknown recipient")

        # Step 5: receiver-side verification (Mallory, when she holds an endpoint, accepts anything).
        if hijacked:
            verdict, ver_ns = Accept(msg.sender, "mallory"), 0
        else:
            t = time.perf_counter_ns()
            verdict = self.defence.verify_incoming(msg, dest)
            ver_ns = time.perf_counter_ns() - t
        if isinstance(verdict, Reject):
            self.stats["rejected"] += 1
            self.log.log("rejected", side="receiver", receiver=dest, msg=msg.to_log(),
                         failed_checks=verdict.failed_checks, detail=verdict.detail, defence_ns=ver_ns)
            return self.notice(msg, REJECTED_NOTICE)
        self.log.log("delivered", leg="request", receiver=dest, msg_id=msg.msg_id, kind=msg.kind,
                     origin=msg.origin, attributed_sender=verdict.attributed_sender,
                     basis=verdict.basis, defence_ns=ver_ns)

        # Step 6: build the reply.
        if msg.kind in HANDSHAKE_KINDS and not hijacked:
            t = time.perf_counter_ns()
            reply = self.defence.handle_handshake(msg, dest, self)
            rep_prep_ns = time.perf_counter_ns() - t
        else:
            reply = handler(msg, verdict)
            if reply is None:
                return self.notice(msg, "no reply")
            if hijacked:
                rep_prep_ns = 0
            else:
                t = time.perf_counter_ns()
                reply = self.defence.prepare_outgoing(reply, self, in_reply_to=msg)
                rep_prep_ns = time.perf_counter_ns() - t

        # Reply leg.
        self._count(reply)
        self.log.log("sent", leg="reply", msg=reply.to_log(), defence_ns=rep_prep_ns)
        routed_reply = self._run_hooks(reply, "reply")
        if routed_reply is None:
            return self.notice(msg, REJECTED_NOTICE)
        reply = routed_reply
        if caller_is_mallory:
            self.log.log("delivered", leg="reply", receiver="mallory", msg_id=reply.msg_id,
                         kind=reply.kind, origin=reply.origin, attributed_sender=reply.sender,
                         basis="unverified", defence_ns=0)
            return reply
        t = time.perf_counter_ns()
        verdict2 = self.defence.verify_incoming(reply, reply.recipient)
        ver2_ns = time.perf_counter_ns() - t
        if isinstance(verdict2, Reject):
            self.stats["rejected"] += 1
            self.log.log("rejected", side="caller", receiver=reply.recipient, msg=reply.to_log(),
                         failed_checks=verdict2.failed_checks, detail=verdict2.detail, defence_ns=ver2_ns)
            return self.notice(msg, REJECTED_NOTICE)
        self.log.log("delivered", leg="reply", receiver=reply.recipient, msg_id=reply.msg_id,
                     kind=reply.kind, origin=reply.origin, attributed_sender=verdict2.attributed_sender,
                     basis=verdict2.basis, defence_ns=ver2_ns)
        return reply
