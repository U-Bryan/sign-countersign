r"""Quick per-cell summary of trial results (for monitoring; not used in the report).

Usage: .\.venv\Scripts\python.exe scripts\summarise.py [--phase pilot|main|oracle|mock] [--experiment core]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from run import phase_dirs  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="pilot")
    ap.add_argument("--experiment", default=None)
    args = ap.parse_args(argv)
    trials_dir = phase_dirs(args.phase)[0]
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in trials_dir.glob("*.json")]
    if args.experiment:
        recs = [r for r in recs if r["experiment"] == args.experiment]
    cells = defaultdict(list)
    for r in recs:
        cells[(r["experiment"], r["family"], r.get("variant_label", ""), r["defence"],
               r["attack"] + ("-" + r["attack_variant"] if r["attack_variant"] else ""))].append(r)

    def s(g, k):
        return sum(int(float(r.get(k) or 0)) for r in g if r["status"] == "ok")

    print(f"{'experiment':9s} {'def':7s} {'attack':13s} {'ok':>3s} {'err':>3s} {'succ':>4s} {'honest':>6s} "
          f"{'f1':>3s} {'f2':>3s} {'f3':>3s} {'f4x':>3s} {'f4b':>3s} {'refu':>4s} {'parse':>5s}  rejected checks / monitor")
    for key in sorted(cells):
        g = cells[key]
        ok = [r for r in g if r["status"] == "ok"]
        checks = sorted({c for r in ok for c in json.loads(r.get("rejected_checks") or "[]")})
        rules = sorted({r["monitor_rule_fired"] for r in ok if r.get("monitor_rule_fired")})
        print(f"{key[0]:9s} {key[3]:7s} {key[4]:13s} {len(ok):3d} {len(g) - len(ok):3d} {s(g, 'success'):4d} "
              f"{s(g, 'honest_task_completed'):6d} {s(g, 'f1_records_relayed'):3d} {s(g, 'f2_orch_instructed'):3d} "
              f"{s(g, 'f3_fin_attempted'):3d} {s(g, 'f4_executed'):3d} {s(g, 'f4_blocked'):3d} {s(g, 'refusals'):4d} "
              f"{s(g, 'parse_failures'):5d}  {','.join(checks)} {'/'.join(rules)}")
    cost = sum(float(r.get("cost_usd") or 0) for r in recs if r["status"] == "ok")
    print(f"\n{len(recs)} trials, cost ${cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
