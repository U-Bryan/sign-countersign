"""JSON schemas for each agent's structured output, plus validation.

Every field is required and additionalProperties is false, so the same schema works
in strict mode on both providers. Amounts are decimal strings.
"""
from __future__ import annotations

from message import parse_gbp_to_pence


def _schema(fields: dict[str, dict]) -> dict:
    return {
        "type": "object",
        "properties": fields,
        "required": list(fields),
        "additionalProperties": False,
    }


STR = {"type": "string"}

ORCHESTRATOR_SCHEMA = _schema({
    "action": {"type": "string", "enum": ["ask_records", "instruct_finance", "done"]},
    "invoice_id": STR, "supplier": STR, "account": STR, "amount_gbp": STR, "summary": STR,
})
RECORDS_SCHEMA = _schema({
    "action": {"type": "string", "enum": ["lookup_supplier", "reply"]},
    "supplier": STR, "bank_account": STR, "notes": STR,
})
FINANCE_SCHEMA = _schema({
    "action": {"type": "string", "enum": ["send_payment", "refuse"]},
    "invoice_id": STR, "account": STR, "amount_gbp": STR, "reason": STR,
})
MONITOR_SCHEMA = _schema({  # E8 (LLM monitor) only
    "decision": {"type": "string", "enum": ["allow", "block"]},
    "reason": STR,
})

SCHEMAS = {
    "orchestrator": ORCHESTRATOR_SCHEMA,
    "records": RECORDS_SCHEMA,
    "finance": FINANCE_SCHEMA,
    "monitor": MONITOR_SCHEMA,
}


def validate(agent: str, obj) -> str | None:
    """Return None if valid, else a short error message for the repair prompt."""
    schema = SCHEMAS[agent]
    if not isinstance(obj, dict):
        return "the reply must be a single JSON object"
    expected = set(schema["properties"])
    missing = expected - set(obj)
    extra = set(obj) - expected
    if missing:
        return f"missing fields: {sorted(missing)}"
    if extra:
        return f"unexpected fields: {sorted(extra)}"
    for k, spec in schema["properties"].items():
        if not isinstance(obj[k], str):
            return f'field "{k}" must be a string'
        if "enum" in spec and obj[k] not in spec["enum"]:
            return f'field "{k}" must be one of {spec["enum"]}'
    action = obj.get("action")
    if agent == "orchestrator" and action == "instruct_finance":
        if not obj["account"].strip():
            return 'instruct_finance needs a non-empty "account"'
        if parse_gbp_to_pence(obj["amount_gbp"]) is None:
            return '"amount_gbp" must be a decimal amount such as "1200.00"'
    if agent == "finance" and action == "send_payment":
        if not obj["account"].strip():
            return 'send_payment needs a non-empty "account"'
        if parse_gbp_to_pence(obj["amount_gbp"]) is None:
            return '"amount_gbp" must be a decimal amount such as "1200.00"'
    if agent == "records" and action == "lookup_supplier" and not obj["supplier"].strip():
        return 'lookup_supplier needs a non-empty "supplier"'
    return None
