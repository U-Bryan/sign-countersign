"""Phase 2 offline tests: the honest flow with the deterministic mock LLM."""
import pytest

from llm import LLMResult, MockClient, parse_json_object
from trial import TrialSpec, run_trial
from world import INVOICES

pytestmark = pytest.mark.integration


def spec(defence="D0", attack="none", inv="INV-104", seed=1, trial=0):
    return TrialSpec("test", "test", "T1", defence, attack, "family1", seed, trial, inv, mock=True)


@pytest.mark.parametrize("inv", [i.invoice_id for i in INVOICES])
def test_all_ten_honest_tasks_succeed_under_d0(inv, tmp_path, cfg):
    rec = run_trial(spec(inv=inv), cfg, log_dir=tmp_path, trials_dir=None)
    assert rec["status"] == "ok", rec
    assert rec["honest_task_completed"] == 1
    assert rec["payment_rows"] == 1 and rec["success"] == 0 and rec["false_rejection"] == 0
    assert rec["n_llm_calls"] == 6  # orchestrator 3, records 2, finance 1


class ScriptedClient:
    """Returns pre-set outputs per agent; falls back to the gullible mock."""

    def __init__(self, scripts: dict[str, list]):
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.mock = MockClient()

    def complete(self, agent, system, user, schema, state=None):
        queue = self.scripts.get(agent)
        if queue:
            item = queue.pop(0)
            if isinstance(item, LLMResult):
                return item
            return LLMResult(parse_json_object(item), item, 0, 0, "scripted", "scripted", "scripted", "end_turn")
        return self.mock.complete(agent, system, user, schema, state)


def run_with(client, tmp_path, cfg, inv="INV-104"):
    import llm as llm_mod
    original = llm_mod.make_llm
    llm_mod.make_llm = lambda *a, **k: client
    import trial as trial_mod
    trial_mod.make_llm = llm_mod.make_llm
    try:
        return run_trial(spec(inv=inv), cfg, log_dir=tmp_path, trials_dir=None)
    finally:
        llm_mod.make_llm = original
        trial_mod.make_llm = original


def test_parse_repair_path_recovers(tmp_path, cfg):
    client = ScriptedClient({"finance": ["this is not json"]})
    rec = run_with(client, tmp_path, cfg)
    assert rec["parse_failures"] == 1
    assert rec["honest_task_completed"] == 1   # repair call (mock) succeeded
    assert rec["n_llm_calls"] == 7


def test_two_parse_failures_mean_no_payment(tmp_path, cfg):
    client = ScriptedClient({"finance": ["nope", '{"action": "pay"}']})
    rec = run_with(client, tmp_path, cfg)
    assert rec["parse_failures"] == 2 and rec["payment_rows"] == 0


def test_refusal_is_an_outcome_not_an_error(tmp_path, cfg):
    refusal = LLMResult(None, "", 5, 0, "scripted", "scripted", "scripted", "refusal")
    client = ScriptedClient({"finance": [refusal]})
    rec = run_with(client, tmp_path, cfg)
    assert rec["status"] == "ok" and rec["refusals"] == 1 and rec["payment_rows"] == 0


def test_orchestrator_step_limit(tmp_path, cfg):
    ask = '{"action": "ask_records", "invoice_id": "INV-104", "supplier": "Acme Ltd", ' \
          '"account": "", "amount_gbp": "", "summary": ""}'
    client = ScriptedClient({"orchestrator": [ask] * 10})
    rec = run_with(client, tmp_path, cfg)
    assert rec["payment_rows"] == 0
    assert rec["n_llm_calls"] == 6 + 6 * 2   # 6 orchestrator steps, each causing a 2-call records lookup


def test_records_with_unknown_supplier_replies_empty(tmp_path, cfg):
    bad = '{"action": "lookup_supplier", "supplier": "Nobody Ltd", "bank_account": "", "notes": ""}'
    client = ScriptedClient({"records": [bad, bad, bad]})
    rec = run_with(client, tmp_path, cfg)
    # Two lookups max, then the records agent replies with empty details; finance is told to pay "" -> invalid.
    assert rec["status"] == "ok"
