"""Property-based tests (hypothesis): any single-field change breaks a D2 signature."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from message import Message, canonical_bytes
from monitor import independent_signature_check
from tests.helpers import Env

pytestmark = pytest.mark.property

FIELDS = ["msg_id", "sender", "recipient", "timestamp_ms", "task_id",
          "body.kind", "body.invoice_id", "body.supplier", "body.account", "body.amount_pence",
          "auth.nonce", "auth.ts_ms", "auth.alg", "body.+extra", "body.-account"]


@pytest.fixture(scope="module")
def d2env(tmp_path_factory):
    from config import load_config
    return Env("D2", load_config(), tmp_path_factory.mktemp("prop"))


def mutate(m: Message, field: str, delta: int, text: str) -> Message:
    m = m.copy()
    if field == "body.+extra":
        m.body["extra"] = text
    elif field == "body.-account":
        m.body.pop("account")
    elif field.startswith("body."):
        k = field[5:]
        v = m.body[k]
        m.body[k] = v + (delta or 1) if isinstance(v, int) else (v + text if text else v + "x")
    elif field.startswith("auth."):
        k = field[5:]
        v = m.auth[k]
        m.auth[k] = v + (delta or 1) if isinstance(v, int) else (v + text if text else v + "x")
    else:
        v = getattr(m, field)
        setattr(m, field, v + (delta or 1) if isinstance(v, int) else (v + text if text else v + "x"))
    return m


@settings(max_examples=600, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@given(field=st.sampled_from(FIELDS), delta=st.integers(min_value=-3, max_value=3),
       text=st.text(min_size=0, max_size=3))
def test_any_single_change_breaks_the_signature(d2env, field, delta, text):
    env = d2env
    m = env.defence.sign_with(env.pay(), env.defence.keys["orchestrator"])
    assert env.defence._signature_ok(m) and independent_signature_check(m, env.defence.registry)
    bad = mutate(m, field, delta, text)
    if bad.to_dict() == m.to_dict():
        return  # no-op mutation (e.g. empty text on a field we append to) - nothing to test
    assert not env.defence._signature_ok(bad)
    assert not independent_signature_check(bad, env.defence.registry)


@settings(max_examples=200, deadline=None)
@given(st.permutations(["kind", "invoice_id", "supplier", "account", "amount_pence"]))
def test_canonical_bytes_ignore_key_order(order):
    body = {"kind": "pay_invoice", "invoice_id": "INV-104", "supplier": "Acme Ltd", "account": "GB-ACME-001",
            "amount_pence": 120000}
    shuffled = {k: body[k] for k in order}
    a = Message("m", "orchestrator", "finance", 1, "T", body)
    b = Message("m", "orchestrator", "finance", 1, "T", shuffled)
    assert canonical_bytes(a) == canonical_bytes(b)


def test_transport_and_monitor_agree_on_honest_signatures(d2env):
    env = d2env
    for _ in range(50):
        m = env.defence.sign_with(env.pay(), env.defence.keys["orchestrator"])
        assert env.defence._signature_ok(m) == independent_signature_check(m, env.defence.registry) is True
