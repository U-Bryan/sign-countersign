import json

import pytest

from bus import REJECTED_NOTICE, Bus, Reject
from defences.d0_none import D0None
from message import Message, new_msg_id
from runlog import read_jsonl

pytestmark = pytest.mark.unit


class RejectAll(D0None):
    def verify_incoming(self, msg, receiver):
        return Reject(["TEST_reject"])


def make_bus(clock, logger, rng, world, cfg, defence=None):
    d = defence or D0None()
    d.setup(world, clock, rng, ["orchestrator", "records", "finance"], cfg, logger)
    bus = Bus(clock, d, logger, rng)

    def echo(msg, verdict):
        return Message(new_msg_id(rng), msg.recipient, msg.sender, clock.now_ms(), msg.task_id,
                       {"kind": "bank_details", "supplier": "Acme Ltd", "bank_account": "GB-ACME-001",
                        "notes": ""})
    bus.register_endpoint("records", echo)
    return bus


def req(rng, clock):
    return Message(new_msg_id(rng), "orchestrator", "records", clock.now_ms(), "T-1",
                   {"kind": "get_bank_details", "invoice_id": "INV-104", "supplier": "Acme Ltd"})


def test_request_round_trip_is_logged_in_order(clock, logger, rng, world, cfg):
    bus = make_bus(clock, logger, rng, world, cfg)
    reply = bus.request(req(rng, clock))
    assert reply.kind == "bank_details" and reply.sender == "records"
    events = [e["event"] for e in logger.events]
    assert events == ["sent", "delivered", "sent", "delivered"]
    seqs = [e["seq"] for e in logger.events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_every_log_line_is_json_with_required_fields(clock, logger, rng, world, cfg):
    bus = make_bus(clock, logger, rng, world, cfg)
    bus.request(req(rng, clock))
    logger.close()
    rows = read_jsonl(logger.path)
    assert rows
    for r in rows:
        for k in ("seq", "event", "sim_time_ms", "wall_time_iso", "perf_ns", "run_id"):
            assert k in r
        json.dumps(r)


def test_rejection_returns_generic_notice(clock, logger, rng, world, cfg):
    bus = make_bus(clock, logger, rng, world, cfg, RejectAll())
    reply = bus.request(req(rng, clock))
    assert reply.kind == "notice" and reply.body["text"] == REJECTED_NOTICE
    rej = logger.of("rejected")
    assert len(rej) == 1 and rej[0]["failed_checks"] == ["TEST_reject"]
    assert bus.stats["rejected"] == 1


def test_drop_hook(clock, logger, rng, world, cfg):
    bus = make_bus(clock, logger, rng, world, cfg)
    bus.add_transit_hook(lambda m, leg: None)
    reply = bus.request(req(rng, clock))
    assert reply.kind == "notice"
    assert len(logger.of("dropped")) == 1 and not logger.of("delivered")


def test_modify_hook_is_logged_with_diff_and_marks_origin(clock, logger, rng, world, cfg):
    bus = make_bus(clock, logger, rng, world, cfg)

    def tamper(m, leg):
        if leg == "reply":
            m = m.copy()
            m.body["bank_account"] = "GB-KSTR-417"
        return m
    bus.add_transit_hook(tamper)
    reply = bus.request(req(rng, clock))
    assert reply.body["bank_account"] == "GB-KSTR-417"
    mods = logger.of("modified")
    assert len(mods) == 1 and mods[0]["changes"] == {"body.bank_account": ["GB-ACME-001", "GB-KSTR-417"]}
    assert mods[0]["msg"]["origin"] == "mallory_modified"


def test_observe_hook_sees_both_legs(clock, logger, rng, world, cfg):
    bus = make_bus(clock, logger, rng, world, cfg)
    seen = []
    bus.add_transit_hook(lambda m, leg: (seen.append((leg, m.kind)), m)[1])
    bus.request(req(rng, clock))
    assert seen == [("request", "get_bank_details"), ("reply", "bank_details")]
    assert not logger.of("modified")


def test_inject_marks_origin_and_returns_unverified_reply(clock, logger, rng, world, cfg):
    bus = make_bus(clock, logger, rng, world, cfg, RejectAll())
    # Receiver rejects, so Mallory gets the notice.
    out = bus.inject(req(rng, clock))
    assert out.kind == "notice"
    assert logger.of("injected")[0]["msg"]["origin"] == "mallory"


def test_unknown_recipient(clock, logger, rng, world, cfg):
    bus = make_bus(clock, logger, rng, world, cfg)
    m = req(rng, clock)
    m.recipient = "nobody"
    assert bus.request(m).kind == "notice"
    assert logger.of("undeliverable")
