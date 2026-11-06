import json
from random import Random

import pytest

from message import (Message, canonical_bytes, new_msg_id, parse_gbp_to_pence, pence_to_gbp_str,
                     render_for_agent)

pytestmark = pytest.mark.unit


def make_msg(**over):
    m = Message(msg_id="m-1", sender="orchestrator", recipient="finance", timestamp_ms=1000, task_id="T-1",
                body={"kind": "pay_invoice", "invoice_id": "INV-104", "supplier": "Acme Ltd",
                      "account": "GB-ACME-001", "amount_pence": 120000})
    for k, v in over.items():
        setattr(m, k, v)
    return m


def test_canonical_bytes_stable_and_order_independent():
    a = make_msg()
    b = make_msg(body={"amount_pence": 120000, "account": "GB-ACME-001", "supplier": "Acme Ltd",
                       "invoice_id": "INV-104", "kind": "pay_invoice"})
    assert canonical_bytes(a) == canonical_bytes(b)
    assert canonical_bytes(a) == canonical_bytes(make_msg())


@pytest.mark.parametrize("field,value", [
    ("msg_id", "m-2"), ("sender", "records"), ("recipient", "records"), ("timestamp_ms", 1001),
    ("task_id", "T-2"),
])
def test_any_top_level_change_changes_bytes(field, value):
    assert canonical_bytes(make_msg()) != canonical_bytes(make_msg(**{field: value}))


def test_any_body_change_changes_bytes():
    base = canonical_bytes(make_msg())
    for k, v in [("account", "GB-KSTR-417"), ("amount_pence", 120001), ("invoice_id", "INV-105")]:
        m = make_msg()
        m.body[k] = v
        assert canonical_bytes(m) != base


def test_auth_fields_included_only_on_request():
    m = make_msg(auth={"nonce": "ab", "ts_ms": 1000})
    assert canonical_bytes(m) == canonical_bytes(make_msg())
    assert canonical_bytes(m, ("nonce",)) != canonical_bytes(m)


def test_origin_never_in_bytes_or_rendering():
    a, b = make_msg(), make_msg()
    b.origin = "mallory"
    assert canonical_bytes(a) == canonical_bytes(b)
    assert render_for_agent(a) == render_for_agent(b)
    assert "origin" not in render_for_agent(a) and "mallory" not in render_for_agent(b).lower()
    assert "origin" not in a.to_dict()


def test_rendering_hides_auth_and_shows_gbp():
    m = make_msg(auth={"sig": "SIGNATURE", "nonce": "NONCE", "d1_channel": "CHAN"})
    text = render_for_agent(m)
    for secret_ish in ("SIGNATURE", "NONCE", "CHAN", "auth"):
        assert secret_ish not in text
    assert '"amount_gbp": "1200.00"' in text and "amount_pence" not in text
    assert text.splitlines()[1] == "from: orchestrator"
    content = json.loads(text.split("content: ", 1)[1])
    assert list(content)[0] == "kind"


@pytest.mark.parametrize("value,pence", [
    ("1200", 120000), ("1,200.00", 120000), ("£1,200.00", 120000), ("GBP 1200", 120000),
    (1200, 120000), (1200.0, 120000), ("389.99", 38999), ("0.01", 1), ("1200.5", 120050),
])
def test_parse_gbp(value, pence):
    assert parse_gbp_to_pence(value) == pence


@pytest.mark.parametrize("value", ["", "abc", None, True, "NaN", "inf", "12.3.4"])
def test_parse_gbp_rejects_garbage(value):
    assert parse_gbp_to_pence(value) is None


def test_pence_formatting_and_ids():
    assert pence_to_gbp_str(120000) == "1200.00" and pence_to_gbp_str(5) == "0.05"
    assert new_msg_id(Random(1)) == new_msg_id(Random(1))
    assert new_msg_id(Random(1)) != new_msg_id(Random(2))
