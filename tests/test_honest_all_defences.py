"""Phase 3 gate check: with the mock, all 10 honest tasks succeed with zero rejections under every defence."""
import pytest

from defences import ALL_DEFENCES
from trial import TrialSpec, run_trial
from world import INVOICES

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("defence", ALL_DEFENCES)
@pytest.mark.parametrize("inv", [i.invoice_id for i in INVOICES])
def test_honest_task_under_every_defence(defence, inv, tmp_path, cfg):
    spec = TrialSpec("test", "test", "T1", defence, "none", "family1", 7, 0, inv, mock=True)
    rec = run_trial(spec, cfg, log_dir=tmp_path, trials_dir=None)
    assert rec["status"] == "ok", rec["error_type"]
    assert rec["honest_task_completed"] == 1
    assert rec["false_rejection"] == 0 and rec["n_rejected"] == 0
    assert rec["monitor_rule_fired"] == ""
    if defence in ("D1", "D1fix"):
        assert rec["n_handshake_messages"] == 8   # 2 conversations x 4 handshake messages
    else:
        assert rec["n_handshake_messages"] == 0
