"""D2: per-agent Ed25519 keys and signed messages (RUNBOOK 6.7).

Every message carries auth = {alg, nonce, ts_ms, sig}; the signature covers the whole
message (id, sender, recipient, timestamp, task, body, alg, nonce, ts_ms). The receiver
runs all six checks K1-K6 and records every failure.
"""
from __future__ import annotations

import base64
import binascii

from cryptography.exceptions import InvalidSignature

import registry as reg
from bus import Accept, Reject
from defences.base import Defence
from message import Message, canonical_bytes, new_hex

SIGNED_AUTH_FIELDS = ("alg", "nonce", "ts_ms")
D2_CHECKS = ("K1_known_sender", "K2_signature", "K3_recipient", "K4_fresh_nonce", "K5_timestamp", "K6_authorised")


class D2Signed(Defence):
    name = "D2"

    def setup(self, world, clock, rng, agents, cfg, logger) -> None:
        super().setup(world, clock, rng, agents, cfg, logger)
        self.keys, self.registry = reg.generate(agents)     # private keys stay in memory only
        self._pub = {a: reg.public_key(self.registry, a) for a in agents}
        self.window_ms = int(cfg.d2.timestamp_window_s) * 1000
        self.nonce_ttl_ms = int(cfg.d2.nonce_cache_ttl_s) * 1000
        self.nonce_bytes = int(cfg.d2.nonce_bytes)
        self._seen: dict[tuple[str, str, str], int] = {}     # (receiver, sender, nonce) -> expiry
        self._purge_at = 1024

    # ----- signing ----------------------------------------------------------
    def sign_with(self, msg: Message, key) -> Message:
        msg.auth = {"alg": "Ed25519", "nonce": new_hex(self.rng, self.nonce_bytes), "ts_ms": msg.timestamp_ms}
        sig = key.sign(canonical_bytes(msg, SIGNED_AUTH_FIELDS))
        msg.auth["sig"] = base64.b64encode(sig).decode("ascii")
        return msg

    def prepare_outgoing(self, msg: Message, bus, in_reply_to: Message | None = None) -> Message:
        key = self.keys.get(msg.sender)
        if key is None:
            return msg
        return self.sign_with(msg, key)

    # ----- verification -----------------------------------------------------
    def _signature_ok(self, msg: Message) -> bool:
        pub = self._pub.get(msg.sender)
        if pub is None or msg.auth.get("alg") != "Ed25519":
            return False
        try:
            pub.verify(base64.b64decode(msg.auth["sig"], validate=True), canonical_bytes(msg, SIGNED_AUTH_FIELDS))
            return True
        except (InvalidSignature, KeyError, ValueError, TypeError, binascii.Error):
            return False

    def verify_incoming(self, msg: Message, receiver: str):
        failed: list[str] = []
        entry = self.registry["agents"].get(msg.sender)
        if entry is None:
            failed.append("K1_known_sender")
        if entry is None or not self._signature_ok(msg):
            failed.append("K2_signature")
        if msg.recipient != receiver:
            failed.append("K3_recipient")
        now = self.clock.agent_now_ms(receiver)
        if len(self._seen) > self._purge_at:   # amortised purge of expired entries (keeps verify O(1))
            self._seen = {k: v for k, v in self._seen.items() if v >= now}
            self._purge_at = max(1024, 2 * len(self._seen))
        nonce = msg.auth.get("nonce")
        expiry = self._seen.get((receiver, msg.sender, nonce)) if nonce else None
        if not nonce or (expiry is not None and expiry >= now):
            failed.append("K4_fresh_nonce")
        ts = msg.auth.get("ts_ms")
        if not isinstance(ts, int) or isinstance(ts, bool) or ts != msg.timestamp_ms or abs(now - ts) > self.window_ms:
            failed.append("K5_timestamp")
        allowed = (entry or {}).get("may_send", {}).get(receiver, [])
        if msg.kind not in allowed:
            failed.append("K6_authorised")
        if failed:
            return Reject(failed)
        self._seen[(receiver, msg.sender, nonce)] = now + self.nonce_ttl_ms   # cache only accepted nonces
        return Accept(msg.sender, "verified", list(D2_CHECKS))

    # ----- A4 ---------------------------------------------------------------
    def credential_for(self, agent: str):
        return self.keys[agent]

    def impostor(self, agent: str, credential):
        return D2Impostor(agent, credential, self)


class D2Impostor:
    """A4-lie under D2: Mallory signs replies as `agent` with the stolen private key."""

    def __init__(self, agent: str, key, defence: D2Signed):
        self.agent, self.key, self.d = agent, key, defence

    def handle_handshake(self, msg: Message) -> Message:
        return self.d.handle_handshake(msg, self.agent, None)

    def prepare_reply(self, reply: Message, in_reply_to: Message) -> Message:
        return self.d.sign_with(reply, self.key)
