"""D2: per-agent Ed25519 keys and signed messages - every check K1-K6 passing and failing."""
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.helpers import Env

pytestmark = pytest.mark.unit


def signed(env, msg, key=None):
    return env.defence.sign_with(msg, key or env.defence.keys[msg.sender])


def failed_checks(env):
    return env.events("rejected")[-1]["failed_checks"]


def test_honest_message_is_verified(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    reply = env.bus.request(env.pay())
    assert reply.kind == "payment_result"
    msg, verdict = env.handled[-1]
    assert verdict.basis == "verified" and verdict.attributed_sender == "orchestrator"
    assert set(msg.auth) == {"alg", "nonce", "ts_ms", "sig"}


def test_k1_unknown_sender(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    env.bus.inject(signed(env, env.pay(sender="mallory"), Ed25519PrivateKey.generate()))
    assert failed_checks(env)[:2] == ["K1_known_sender", "K2_signature"]


def test_k2_wrong_key(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    env.bus.inject(signed(env, env.pay(), env.defence.keys["records"]))
    assert failed_checks(env) == ["K2_signature"]


def test_k2_tampered_body(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    m = signed(env, env.pay())
    m.body["account"] = "GB-KSTR-417"
    env.bus.inject(m)
    assert failed_checks(env) == ["K2_signature"]


def test_k3_wrong_recipient(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    m = signed(env, env.pay())          # addressed to finance...
    env.bus.inject(m, deliver_to="records")   # ...delivered to records
    assert "K3_recipient" in failed_checks(env)


def test_k4_reused_nonce(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    m = signed(env, env.pay())
    assert env.bus.inject(m.copy()).kind == "payment_result"
    env.bus.inject(m.copy())
    assert failed_checks(env) == ["K4_fresh_nonce"]


@pytest.mark.parametrize("shift_s", [61, -61])
def test_k5_stale_or_future_timestamp(shift_s, cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    m = env.pay()
    m.timestamp_ms += shift_s * 1000
    env.bus.inject(signed(env, m))
    assert failed_checks(env) == ["K5_timestamp"]


def test_k5_auth_timestamp_mismatch(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    m = signed(env, env.pay())
    m.auth["ts_ms"] += 1
    env.bus.inject(m)
    assert "K5_timestamp" in failed_checks(env)


def test_k6_unauthorised_kind(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    env.bus.inject(signed(env, env.pay(sender="records")))   # validly signed by records
    assert failed_checks(env) == ["K6_authorised"]


def test_all_failures_reported_together(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    m = env.pay(sender="records")
    m.timestamp_ms -= 120_000
    m = signed(env, m)
    m.body["amount_pence"] = 1
    env.bus.inject(m, deliver_to="records")
    assert failed_checks(env) == ["K2_signature", "K3_recipient", "K5_timestamp", "K6_authorised"]


def test_rejected_message_does_not_cache_its_nonce(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    m = signed(env, env.pay())
    bad = m.copy()
    bad.recipient = "records"   # breaks the signature too
    env.bus.inject(bad, deliver_to="finance")
    assert env.bus.inject(m.copy()).kind == "payment_result"   # same nonce still fresh


def test_no_private_keys_in_logs_or_registry(cfg, tmp_path):
    env = Env("D2", cfg, tmp_path)
    env.bus.request(env.pay())
    env.log.close()
    text = env.log.path.read_text(encoding="utf-8")
    from cryptography.hazmat.primitives import serialization
    for key in env.defence.keys.values():
        raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
        import base64
        assert base64.b64encode(raw).decode() not in text and raw.hex() not in text
    reg_text = json.dumps(env.defence.registry)
    assert "PRIVATE" not in reg_text
    assert set(env.defence.registry["agents"]["orchestrator"]) == {"public_key_b64", "may_send"}
