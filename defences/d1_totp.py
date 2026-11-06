"""D1: shared TOTP handshake, implemented exactly as first proposed (RUNBOOK 6.7).

1. caller -> receiver  hs_hello        {nonce_c}            (nonce_c becomes the channel_id)
2. receiver -> caller  hs_code         {code_r, nonce_r}    (the receiver reveals its code FIRST)
3. caller checks code_r
4. caller -> receiver  hs_countercode  {channel_id, code_c}
5. receiver -> caller  hs_result       ok | REJECTED

Faithful to the proposal: nonces are exchanged but not bound to the codes, nothing is
cached, and after the handshake there is no per-message integrity. With one shared
secret, code_r == code_c, which is what makes the reflection attack (A1-reflect) work.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pyotp

from bus import Accept, HandshakeFailed, Reject
from defences.base import Defence
from message import HANDSHAKE_KINDS, HS_CODE, HS_COUNTERCODE, HS_HELLO, HS_RESULT, Message, new_hex, new_msg_id


def _dt(t_ms: int) -> datetime:
    return datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc)


class D1Totp(Defence):
    name = "D1"

    # ----- codes (D1fix overrides _make_totps) -------------------------------
    def _make_totps(self, secret: str):
        t = pyotp.TOTP(secret, digits=self.digits, interval=self.period)
        return t, t  # D1: the same code in both directions

    def code_r(self, t_ms: int) -> str:
        return self._sign.at(_dt(t_ms))

    def code_c(self, t_ms: int) -> str:
        return self._counter.at(_dt(t_ms))

    def check_r(self, code, t_ms: int) -> bool:
        return bool(code) and self._sign.verify(str(code), for_time=_dt(t_ms), valid_window=self.window)

    def check_c(self, code, t_ms: int) -> bool:
        return bool(code) and self._counter.verify(str(code), for_time=_dt(t_ms), valid_window=self.window)

    def codes_from_secret(self, secret: str, t_ms: int) -> tuple[str, str]:
        """What anyone holding the secret can compute (the algorithm is public). Used by A4."""
        sign, counter = self._make_totps(secret)
        return sign.at(_dt(t_ms)), counter.at(_dt(t_ms))

    # ----- lifecycle --------------------------------------------------------
    def setup(self, world, clock, rng, agents, cfg, logger) -> None:
        super().setup(world, clock, rng, agents, cfg, logger)
        self.digits = int(cfg.d1.totp_digits)
        self.period = int(cfg.d1.totp_period_s)
        self.window = int(cfg.d1.valid_window)
        self.ttl_ms = int(cfg.d1.channel_ttl_s) * 1000
        self.secret = pyotp.random_base32()          # one per trial, shared by the honest agents
        self._sign, self._counter = self._make_totps(self.secret)
        self._channels: dict[tuple[str, str, str], int] = {}   # (local, peer, channel_id) -> expiry
        self._pending: dict[tuple[str, str, str], int] = {}    # receiver side, after hs_hello

    def end_task(self) -> None:
        self._channels.clear()
        self._pending.clear()
        self.log.log("hs_channels_closed")

    def credential_for(self, agent: str):
        return self.secret  # one shared secret: stealing "records'" credential means stealing everyone's

    # ----- caller side ------------------------------------------------------
    def _live_channel(self, local: str, peer: str) -> str | None:
        now = self.clock.now_ms()
        for (l, p, cid), exp in self._channels.items():
            if l == local and p == peer and exp >= now:
                return cid
        return None

    def prepare_outgoing(self, msg: Message, bus, in_reply_to: Message | None = None) -> Message:
        if msg.kind in HANDSHAKE_KINDS:
            return msg
        if in_reply_to is not None:
            cid = in_reply_to.auth.get("d1_channel")
            msg.auth = {"d1_channel": cid} if cid else {}
            return msg
        cid = self._live_channel(msg.sender, msg.recipient)
        if cid is None:
            cid = self._handshake(msg.sender, msg.recipient, msg.task_id, bus)
        msg.auth = {"d1_channel": cid}
        return msg

    def _handshake(self, caller: str, receiver: str, task_id: str, bus) -> str:
        nonce_c = new_hex(self.rng, 16)
        hello = Message(new_msg_id(self.rng), caller, receiver, self.clock.agent_now_ms(caller), task_id,
                        {"kind": HS_HELLO, "nonce_c": nonce_c})
        r1 = bus.request(hello)
        if r1.kind != HS_CODE:
            raise HandshakeFailed(["D1_no_code_from_receiver"])
        if not self.check_r(r1.body.get("code_r", ""), self.clock.agent_now_ms(caller)):
            self.log.log("hs_fail_caller", caller=caller, receiver=receiver, channel_id=nonce_c)
            raise HandshakeFailed(["D1_bad_code_from_receiver"])
        counter = Message(new_msg_id(self.rng), caller, receiver, self.clock.agent_now_ms(caller), task_id,
                          {"kind": HS_COUNTERCODE, "channel_id": nonce_c,
                           "code_c": self.code_c(self.clock.agent_now_ms(caller))})
        r2 = bus.request(counter)
        if r2.kind != HS_RESULT or r2.body.get("status") != "ok":
            raise HandshakeFailed(["D1_countercode_rejected"])
        self._channels[(caller, receiver, nonce_c)] = self.clock.now_ms() + self.ttl_ms
        self.log.log("hs_ok", side="caller", caller=caller, receiver=receiver, channel_id=nonce_c)
        return nonce_c

    # ----- receiver side ----------------------------------------------------
    def handle_handshake(self, msg: Message, receiver: str, bus) -> Message:
        now = self.clock.agent_now_ms(receiver)
        if msg.kind == HS_HELLO:
            cid = str(msg.body.get("nonce_c", ""))
            self._pending[(receiver, msg.sender, cid)] = self.clock.now_ms() + self.ttl_ms
            body = {"kind": HS_CODE, "code_r": self.code_r(now), "nonce_r": new_hex(self.rng, 16)}
        elif msg.kind == HS_COUNTERCODE:
            cid = str(msg.body.get("channel_id", ""))
            key = (receiver, msg.sender, cid)
            pending_ok = self._pending.pop(key, None) is not None
            code_ok = self.check_c(msg.body.get("code_c", ""), now)
            if pending_ok and code_ok:
                self._channels[key] = self.clock.now_ms() + self.ttl_ms
                self.log.log("hs_ok", side="receiver", caller=msg.sender, receiver=receiver, channel_id=cid)
                body = {"kind": HS_RESULT, "status": "ok"}
            else:
                failed = ([] if pending_ok else ["D1_no_pending_hello"]) + ([] if code_ok else ["D1_bad_countercode"])
                if bus is not None:
                    bus.stats["rejected"] += 1
                self.log.log("rejected", side="receiver", receiver=receiver, msg=msg.to_log(),
                             failed_checks=failed, detail="REJECTED", defence_ns=0)
                body = {"kind": HS_RESULT, "status": "REJECTED"}
        else:
            body = {"kind": HS_RESULT, "status": "unexpected"}
        return Message(new_msg_id(self.rng), receiver, msg.sender, now, msg.task_id, body)

    def verify_incoming(self, msg: Message, receiver: str):
        if msg.kind in HANDSHAKE_KINDS:
            return Accept(msg.sender, "handshake")
        cid = msg.auth.get("d1_channel")
        if not cid:
            return Reject(["D1_no_channel"])
        exp = self._channels.get((receiver, msg.sender, cid))
        if exp is None:
            return Reject(["D1_no_channel"])
        if exp < self.clock.now_ms():
            return Reject(["D1_channel_expired"])
        return Accept(msg.sender, "channel")

    # ----- A4-lie: Mallory answers as `agent` with the stolen secret ---------------
    def impostor(self, agent: str, credential):
        return D1Impostor(agent, credential, self)


class D1Impostor:
    """Answers handshakes as the hijacked agent using the stolen secret, then replies on the channel."""

    def __init__(self, agent: str, secret: str, defence: D1Totp):
        self.agent = agent
        self.secret = secret
        self.d = defence

    def handle_handshake(self, msg: Message) -> Message:
        now = self.d.clock.agent_now_ms(self.agent)
        code_r, _ = self.d.codes_from_secret(self.secret, now)
        if msg.kind == HS_HELLO:
            body = {"kind": HS_CODE, "code_r": code_r, "nonce_r": new_hex(self.d.rng, 16)}
        else:  # Mallory accepts any countercode
            body = {"kind": HS_RESULT, "status": "ok"}
        return Message(new_msg_id(self.d.rng), self.agent, msg.sender, now, msg.task_id, body, origin="mallory")

    def prepare_reply(self, reply: Message, in_reply_to: Message) -> Message:
        cid = in_reply_to.auth.get("d1_channel")
        reply.auth = {"d1_channel": cid} if cid else {}
        return reply
