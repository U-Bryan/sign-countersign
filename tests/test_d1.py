"""D1 (shared TOTP handshake as proposed) and D1fix (direction-separated codes)."""
import pytest

from message import HS_COUNTERCODE, HS_HELLO, new_hex
from tests.helpers import Env

pytestmark = pytest.mark.unit


def hello(env, sender="orchestrator", recipient="finance", nonce=None):
    nonce = nonce or new_hex(env.rng, 16)
    return env.msg(sender, recipient, {"kind": HS_HELLO, "nonce_c": nonce}), nonce


def countercode(env, nonce, code, sender="orchestrator", recipient="finance"):
    return env.msg(sender, recipient, {"kind": HS_COUNTERCODE, "channel_id": nonce, "code_c": code})


def test_honest_handshake_opens_channels_both_sides(cfg, tmp_path):
    env = Env("D1", cfg, tmp_path)
    reply = env.bus.request(env.get_bank())
    assert reply.kind == "bank_details"
    keys = set(env.defence._channels)
    cid = reply.auth["d1_channel"]
    assert ("orchestrator", "records", cid) in keys and ("records", "orchestrator", cid) in keys
    assert len(env.events("hs_ok")) == 2
    # A second message reuses the channel: no new handshake.
    env.bus.request(env.get_bank())
    assert len(env.events("hs_ok")) == 2


def test_wrong_countercode_is_rejected(cfg, tmp_path):
    env = Env("D1", cfg, tmp_path)
    h, nonce = hello(env)
    assert env.bus.inject(h).kind == "hs_code"
    r = env.bus.inject(countercode(env, nonce, "000000" if env.defence.code_c(env.clock.now_ms()) != "000000" else "111111"))
    assert r.body["status"] == "REJECTED"
    rej = env.events("rejected")
    assert rej and "D1_bad_countercode" in rej[-1]["failed_checks"]


def test_countercode_without_hello_is_rejected(cfg, tmp_path):
    env = Env("D1", cfg, tmp_path)
    r = env.bus.inject(countercode(env, "deadbeef", env.defence.code_c(env.clock.now_ms())))
    assert r.body["status"] == "REJECTED"
    assert "D1_no_pending_hello" in env.events("rejected")[-1]["failed_checks"]


def test_caller_aborts_on_wrong_receiver_code(cfg, tmp_path, monkeypatch):
    env = Env("D1", cfg, tmp_path)
    real = env.defence.code_c(env.clock.now_ms())
    monkeypatch.setattr(env.defence, "code_r", lambda t: "000000" if real != "000000" else "111111")
    reply = env.bus.request(env.get_bank())
    assert reply.kind == "notice"
    assert env.events("hs_fail_caller")
    assert env.events("send_failed")[-1]["failed_checks"] == ["D1_bad_code_from_receiver"]


def test_valid_window_one_step_each_way(cfg, tmp_path):
    env = Env("D1", cfg, tmp_path)
    t = env.clock.now_ms()                      # exactly on a step boundary
    code = env.defence.code_c(t)
    assert env.defence.check_c(code, t)
    assert env.defence.check_c(code, t + 30_000)        # next step: accepted
    assert env.defence.check_c(code, t - 1)             # previous step: accepted
    assert not env.defence.check_c(code, t + 60_000)    # two steps later: rejected
    assert not env.defence.check_c(code, t - 30_001)    # two steps earlier: rejected
    assert not env.defence.check_c("", t) and not env.defence.check_c(None, t)


def test_closed_and_expired_channels_reject(cfg, tmp_path):
    env = Env("D1", cfg, tmp_path)
    reply = env.bus.request(env.pay())
    cid = reply.auth["d1_channel"]
    env.defence.end_task()
    stale = env.pay()
    stale.auth = {"d1_channel": cid}
    assert env.bus.inject(stale).kind == "notice"
    assert env.events("rejected")[-1]["failed_checks"] == ["D1_no_channel"]
    env2 = Env("D1", cfg, tmp_path, seed=5)
    reply2 = env2.bus.request(env2.pay())
    env2.clock.advance(cfg.d1.channel_ttl_s + 1)
    m = env2.pay()
    m.auth = {"d1_channel": reply2.auth["d1_channel"]}
    env2.bus.inject(m)
    assert env2.events("rejected")[-1]["failed_checks"] == ["D1_channel_expired"]


def test_channel_is_bound_to_claimed_peer(cfg, tmp_path):
    env = Env("D1", cfg, tmp_path)
    reply = env.bus.request(env.pay())
    m = env.pay(sender="records")
    m.auth = {"d1_channel": reply.auth["d1_channel"]}
    env.bus.inject(m)
    assert env.events("rejected")[-1]["failed_checks"] == ["D1_no_channel"]


def test_reflection_attack_works_against_d1(cfg, tmp_path):
    """Pins down the documented flaw (deviation V6): the receiver's own code, sent back, opens a channel."""
    env = Env("D1", cfg, tmp_path)
    h, nonce = hello(env)
    code_r = env.bus.inject(h).body["code_r"]
    assert env.bus.inject(countercode(env, nonce, code_r)).body["status"] == "ok"
    forged = env.pay(account="GB-KSTR-417")
    forged.auth = {"d1_channel": nonce}
    assert env.bus.inject(forged).kind == "payment_result"
    msg, verdict = env.handled[-1]
    assert verdict.attributed_sender == "orchestrator" and verdict.basis == "channel"


def test_reflection_fails_against_d1fix_but_honest_works(cfg, tmp_path):
    env = Env("D1fix", cfg, tmp_path)
    h, nonce = hello(env)
    code_r = env.bus.inject(h).body["code_r"]
    assert env.bus.inject(countercode(env, nonce, code_r)).body["status"] == "REJECTED"
    assert env.bus.request(env.pay()).kind == "payment_result"


@pytest.mark.parametrize("defence", ["D1", "D1fix"])
@pytest.mark.parametrize("delay,accepted", [(10, True), (300, False)])
def test_replayed_handshake_depends_on_delay(defence, delay, accepted, cfg, tmp_path):
    env = Env(defence, cfg, tmp_path)
    seen = []
    env.bus.add_transit_hook(lambda m, leg: (seen.append(m.copy()), m)[1])
    env.bus.request(env.pay())
    env.defence.end_task()
    recorded = [m for m in seen if m.sender == "orchestrator" and m.recipient == "finance"]
    kinds = [m.kind for m in recorded]
    assert kinds == ["hs_hello", "hs_countercode", "pay_invoice"]
    env.clock.advance(delay)
    for m in recorded:
        m.origin = "mallory_replay"
        out = env.bus.inject(m)
    assert (out.kind == "payment_result") is accepted


def test_totp_secret_never_logged(cfg, tmp_path):
    env = Env("D1", cfg, tmp_path)
    env.bus.request(env.get_bank())
    env.bus.request(env.pay())
    env.log.close()
    text = env.log.path.read_text(encoding="utf-8")
    assert env.defence.secret not in text
