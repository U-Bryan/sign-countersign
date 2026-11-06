r"""Phase gate checks (RUNBOOK rule R1). Usage: .\.venv\Scripts\python.exe gates.py <phase 0-8>

Prints one line per check and then "GATE <n> PASS" or "GATE <n> FAIL". Exit code 0 only on PASS.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
sys.path.insert(0, str(ROOT))


def run(args, timeout=1200) -> tuple[int, str]:
    env = dict(os.environ, PYTHONUTF8="1")
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env=env)
    return p.returncode, (p.stdout + p.stderr).strip()


def git_exe() -> str | None:
    from gitutil import git_exe as _g
    return _g()


def git(*args) -> tuple[bool, str]:
    g = git_exe()
    if not g:
        return False, "git not installed"
    code, out = run([g, *args])
    return code == 0, out


def pytest(*targets) -> tuple[bool, str]:
    code, out = run([PY, "-m", "pytest", "-q", *targets])
    return code == 0, out.splitlines()[-1] if out else ""


def trials(phase: str) -> list[dict]:
    d = {"main": ROOT / "results" / "trials", "pilot": ROOT / "results" / "pilot" / "trials",
         "oracle": ROOT / "results" / "oracle" / "trials"}[phase]
    return [json.loads(p.read_text(encoding="utf-8")) for p in d.glob("*.json")] if d.exists() else []


def progress_text() -> str:
    p = ROOT / "PROGRESS.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def honest_rate(recs, defence, family="family1") -> tuple[int, int]:
    rs = [r for r in recs if r["experiment"] == "honest" and r["defence"] == defence and r["family"] == family
          and r["status"] == "ok"]
    return sum(int(r["honest_task_completed"]) for r in rs), len(rs)


# ----- gates -------------------------------------------------------------------------
def gate0():
    code, out = run([PY, "-c", "import pyotp, cryptography, anthropic, openai, pandas, matplotlib, scipy, statsmodels"])
    yield "imports", code == 0 and out == "", out[:200]
    mc = ROOT / "docs" / "MODEL_CHECK.md"
    text = mc.read_text(encoding="utf-8") if mc.exists() else ""
    f1 = bool(re.search(r"\| family1 \|[^\n]*\| yes \|", text))
    f2 = bool(re.search(r"\| family2 \|[^\n]*\| yes \|", text)) or "family 2 deferred" in progress_text().lower()
    yield "model check family1", f1, "docs/MODEL_CHECK.md" if mc.exists() else "run scripts/check_models.py"
    yield "model check family2 (or deferred)", f2, ""
    code, out = run([PY, "scripts/secret_scan.py"])
    yield "secret scan", code == 0, out.splitlines()[-1] if out else ""
    ok, out = git("check-ignore", ".env")
    yield ".env is git-ignored", ok and ".env" in out, out[:100]


def gate1():
    ok, out = pytest("-m", "unit")
    yield "unit tests", ok, out
    from clock import SimClock
    from runlog import RunLogger, read_jsonl
    from world import World
    from random import Random
    from bus import Bus
    from defences.d0_none import D0None
    from config import load_config
    from message import Message, new_msg_id
    path = ROOT / "logs" / "gate1-demo.jsonl"
    clock = SimClock(1_794_000_000_000, real_time=False)
    log = RunLogger(path, "gate1-demo", clock)
    w = World(clock, log)
    row = w.send_payment("INV-104", "GB-ACME-001", 120000, "orchestrator", "claimed", "demo")
    yield "send_payment by hand shows a ledger row", w.ledger == (row,), str(row)
    rng = Random(1)
    d = D0None()
    d.setup(w, clock, rng, ["orchestrator", "records", "finance"], load_config(), log)
    bus = Bus(clock, d, log, rng)
    bus.register_endpoint("records", lambda m, v: Message(new_msg_id(rng), "records", m.sender, 0, m.task_id,
                                                          {"kind": "bank_details", "supplier": "", "bank_account": "", "notes": ""}))
    bus.request(Message(new_msg_id(rng), "orchestrator", "records", 0, "T-1", {"kind": "get_bank_details"}))
    log.close()
    rows = read_jsonl(path)
    need = {"seq", "event", "sim_time_ms", "wall_time_iso", "perf_ns", "run_id"}
    yield "bus message logged with required fields", any(r["event"] == "sent" for r in rows) and all(need <= set(r) for r in rows), str(path)
    path.unlink(missing_ok=True)


def gate2():
    ok, out = pytest("tests/test_agents_mock.py")
    yield "mock agent tests", ok, out
    recs = trials("pilot")
    k, n = honest_rate(recs, "D0")
    yield "honest D0 family1 >= 9/10", n >= 10 and k >= 9, f"{k}/{n}"
    k2, n2 = honest_rate(recs, "D0", "family2")
    yield "honest D0 family2 >= 9/10 (or deferred)", (n2 >= 10 and k2 >= 9) or "family 2 deferred" in progress_text().lower(), f"{k2}/{n2}"
    rs = [r for r in recs if r["experiment"] == "honest" and r["status"] == "ok"]
    calls = sum(int(r["n_llm_calls"]) for r in rs)
    pf = sum(int(r["parse_failures"]) for r in rs)
    yield "parse failures <= 2% of calls", calls > 0 and pf / calls <= 0.02, f"{pf}/{calls}"
    ok, out = git("rev-parse", "-q", "--verify", "refs/tags/prompts-v1")
    yield "tag prompts-v1 exists", ok, out[:60]


def gate3():
    ok, out = pytest("tests/test_d1.py", "tests/test_d2.py", "tests/test_monitor.py", "tests/test_properties.py",
                     "tests/test_honest_all_defences.py")
    yield "defence unit, property and mock honest tests", ok, out
    recs = trials("pilot")
    for d in ("D1", "D2", "D3"):
        k, n = honest_rate(recs, d)
        yield f"live honest {d} >= 9/10", n >= 10 and k >= 9, f"{k}/{n}"
    yield "tables/bench.csv exists", (ROOT / "tables" / "bench.csv").exists(), ""


def gate4():
    ok, out = git("log", "-1", "--format=%ct", "prereg-v1")
    yield "tag prereg-v1 exists", ok, out[:60]
    attack_logs = [p for p in (ROOT / "logs" / "pilot").glob("pilot-core-*.jsonl")] if (ROOT / "logs" / "pilot").exists() else []
    if ok and attack_logs:
        first = min(p.stat().st_mtime for p in attack_logs)
        yield "prereg-v1 precedes every attack-trial log", int(out.strip()) <= first, ""
    ok2, out2 = pytest("tests/test_attacks.py", "tests/test_oracle_matrix.py")
    yield "attack tests and oracle matrix", ok2, out2
    recs = [r for r in trials("pilot") if r["experiment"] == "core" and r["defence"] == "D0" and r["status"] == "ok"]
    from attacks import CORE_ATTACKS
    from grading import ATTACK_VARIANTS
    for a in CORE_ATTACKS:
        cls, var = ATTACK_VARIANTS[a]
        rs = [r for r in recs if r["attack"] == cls and r["attack_variant"] == var]
        s = sum(int(r["success"]) for r in rs)
        documented = f"C-3 {a}" in progress_text()
        yield f"{a} succeeds at least once under D0 (live)", (rs and s >= 1) or documented, f"{s}/{len(rs)}"


def gate5():
    from attacks import CORE_ATTACKS
    from grading import ATTACK_VARIANTS
    from oracle_table import ORACLE_TABLE
    recs = [r for r in trials("pilot") if r["experiment"] == "core" and r["status"] == "ok"]
    have = {(r["defence"], r["attack"], r["attack_variant"]) for r in recs}
    missing = [(d, a) for d in ("D0", "D1", "D2", "D3") for a in CORE_ATTACKS if (d, *ATTACK_VARIANTS[a]) not in have]
    yield "every T1 cell has pilot rows", not missing, f"missing {missing[:4]}"
    orc = trials("oracle")
    bad = [r["run_id"] for r in orc if r["status"] == "ok" and r["attack"] != "none"
           and int(r["success"]) != ORACLE_TABLE[r["defence"]][next(k for k, v in ATTACK_VARIANTS.items() if v == (r["attack"], r["attack_variant"]))]]
    yield "mock matrix matches the oracle", bool(orc) and not bad, f"{len(orc)} oracle trials, {len(bad)} mismatches"
    code, out = run([PY, "audit.py", "--phase", "pilot"])
    yield "audit pilot 100%", code == 0, out.splitlines()[0] if out else ""
    for f in ("docs/PILOT_AUDIT.md", "docs/PILOT_BUGS.md", "docs/COST_ESTIMATE.md"):
        yield f"{f} exists", (ROOT / f).exists(), ""
    m = re.search(r"C3 tiers approved:\s*([^\n·]+)", progress_text())
    yield "tier approval recorded (C3)", bool(m and "T1" in m.group(1)), m.group(1).strip() if m else ""


def gate6():
    from run import build_plan
    from config import load_config
    cfg = load_config()
    m = re.search(r"C3 tiers approved:\s*([^\n·]+)", progress_text())
    approved = m.group(1) if m else "T1"
    exps = ["honest", "core"] + (["family2", "ablation"] if "T2" in approved else [])
    exps += [e for e in ("ext-E4", "ext-E5", "ext-E6") if e[4:] in approved]
    done = {r["run_id"] for r in trials("main") if r["status"] == "ok"}
    for e in exps:
        plan = build_plan(e, "main", cfg)
        short = [s.run_id for s in plan if s.run_id not in done]
        yield f"{e}: all {len(plan)} planned trials ok", not short, f"{len(short)} missing"
    code, out = run([PY, "audit.py", "--phase", "main"])
    yield "audit main 100%", code == 0, out.splitlines()[0] if out else ""
    yield "results/run_manifest.json exists", (ROOT / "results" / "run_manifest.json").exists(), ""
    ok, _ = git("rev-parse", "-q", "--verify", "refs/tags/main-run-complete")
    yield "tag main-run-complete", ok, ""


EXPECTED_OUTPUTS = ["figures/fig2_asr_heatmap.png", "figures/fig4_asr_forest.png", "figures/fig5_cost_tradeoff.png",
                    "figures/fig7_attribution.png", "figures/fig8_a5_funnel.png", "figures/fig9_oracle_vs_llm.png",
                    "tables/table2_asr_matrix.csv", "tables/table3_significance.csv", "tables/table4_costs.csv",
                    "tables/table10_hypotheses.csv", "tables/values.json"]


def gate7():
    res = ROOT / "results" / "results.csv"
    t0 = res.stat().st_mtime if res.exists() else 0
    for f in EXPECTED_OUTPUTS:
        p = ROOT / f
        yield f"{f} exists and is newer than results.csv", p.exists() and p.stat().st_mtime >= t0, ""
    det = ROOT / "tables" / "determinism.json"
    yield "analysis is deterministic (two runs identical)", det.exists() and json.loads(det.read_text(encoding="utf-8")).get("identical") is True, ""
    ok, out = pytest("tests/test_stats.py")
    yield "statistics tests", ok, out


def gate8():
    hc = ROOT / "handoff" / "HANDOFF_CHECKLIST.md"
    text = hc.read_text(encoding="utf-8") if hc.exists() else ""
    yield "handoff checklist complete", bool(text) and "- [ ]" not in text, str(hc)
    code, out = run([PY, "reproduce.py"], timeout=3600)
    yield "reproduce.py passes", code == 0, out.splitlines()[-1] if out else ""
    code, out = run([PY, "scripts/secret_scan.py"])
    yield "secret scan", code == 0, ""
    ok, out = git("diff", "--quiet", "prereg-v1", "--", "PREREGISTRATION.md")
    yield "PREREGISTRATION.md unchanged since prereg-v1", ok, ""
    ok, out = git("diff", "--quiet", "prompts-v1", "--", "prompts/")
    yield "prompts unchanged since prompts-v1 (or deviation logged)", ok or "prompt change" in (ROOT / "docs" / "DEVIATIONS.md").read_text(encoding="utf-8").lower(), ""


GATES = {0: gate0, 1: gate1, 2: gate2, 3: gate3, 4: gate4, 5: gate5, 6: gate6, 7: gate7, 8: gate8}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or not argv[0].isdigit() or int(argv[0]) not in GATES:
        print(__doc__)
        return 2
    n = int(argv[0])
    failures = 0
    for name, ok, detail in GATES[n]():
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"GATE {n} {'PASS' if not failures else 'FAIL'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
