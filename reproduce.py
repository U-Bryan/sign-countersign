r"""One-command reproduction (RUNBOOK Phase 8).

  .\.venv\Scripts\python.exe reproduce.py              # free: offline tests -> audit -> analysis -> report,
                                                        #       regenerating every number and figure from committed data
  .\.venv\Scripts\python.exe reproduce.py --mock-full  # free: the whole pipeline with the deterministic mock LLM
  .\.venv\Scripts\python.exe reproduce.py --full --budget 60 [--tiers T1,T2]   # real API rerun (needs keys in .env)
Exit code 0 only if every step succeeds.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def step(name: str, args: list[str], timeout: int = 7200) -> None:
    print(f"\n=== {name}: {' '.join(args)}", flush=True)
    env = dict(os.environ, PYTHONUTF8="1")
    code = subprocess.run([PY, *args], cwd=ROOT, env=env, timeout=timeout).returncode
    if code != 0:
        print(f"\nFAILED at step '{name}' (exit code {code})")
        sys.exit(code)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--mock-full", action="store_true")
    g.add_argument("--full", action="store_true")
    ap.add_argument("--budget", type=float, default=None, help="hard cap in USD for --full")
    ap.add_argument("--tiers", default="T1")
    args = ap.parse_args(argv)

    step("offline tests", ["-m", "pytest", "-q", "-m", "not live"])
    if args.mock_full:
        step("oracle matrix (mock)", ["run.py", "--experiment", "oracle"])
        step("audit oracle", ["audit.py", "--phase", "oracle"])
        for exp in ("honest", "core", "ablation", "ext-E4"):
            step(f"mock {exp}", ["run.py", "--experiment", exp, "--phase", "mock", "--mock", "--trials", "3"])
        step("audit mock", ["audit.py", "--phase", "mock"])
        step("analysis (mock)", ["analyse.py", "--csv", "results/mock/results_mock.csv", "--phase", "mock",
                                 "--out-root", "results/mock/analysis", "--extensions", "E1,E2,E3"])
        step("report (mock)", ["make_report.py", "--root", "results/mock/analysis", "--csv", "results/mock/results_mock.csv",
                               "--logs", "logs/mock", "--out", "results/mock/report"])
        print("\nMock pipeline complete: results/mock/report/RESULTS.md")
        return 0
    if args.full:
        if args.budget is not None:
            os.environ["SCC_BUDGET_CAP"] = str(args.budget)
        step("model check", ["scripts/check_models.py", "--family", "family1"])
        exps = ["honest", "core"] + (["family2", "ablation"] if "T2" in args.tiers else [])
        for exp in exps:
            step(f"run {exp}", ["run.py", "--experiment", exp, "--phase", "main"], timeout=6 * 3600)
    if not (ROOT / "results" / "results.csv").exists():
        print("\nNo results/results.csv yet. Run the experiments first, or use --mock-full for a free rehearsal.")
        return 1
    step("audit", ["audit.py", "--phase", "main"])
    step("analysis", ["analyse.py", "--extensions", "E1,E2,E3"])
    step("report", ["make_report.py"])
    print("\nReproduction complete: report/RESULTS.md, figures/, tables/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
