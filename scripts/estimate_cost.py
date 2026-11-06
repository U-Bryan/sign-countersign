r"""Estimate main-run cost and time per tier from the pilot's measurements (Phase 5, step 7).

Uses the mean calls, tokens, USD and latency per (defence, attack, family) cell measured in
the pilot (results/pilot/trials). Cells without pilot data fall back to the closest
measured cell (same attack, any defence), then to a default (6 calls, 1,000 in / 600 out each).
Writes docs/COST_ESTIMATE.md.

Usage: .\.venv\Scripts\python.exe scripts\estimate_cost.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_config  # noqa: E402


def pilot_stats() -> dict:
    by_cell = defaultdict(list)
    d = ROOT / "results" / "pilot" / "trials"
    for p in d.glob("*.json") if d.exists() else []:
        r = json.loads(p.read_text(encoding="utf-8"))
        if r.get("status") != "ok":
            continue
        attack = r["attack"] + ("-" + r["attack_variant"] if r["attack_variant"] else "")
        by_cell[(r["defence"], attack, r["family"])].append(r)
    return by_cell


def _mean(rows, key):
    return statistics.fmean(float(r[key] or 0) for r in rows) if rows else 0.0


def per_trial(spec, cfg, stats) -> tuple[float, float, float, bool]:
    """(usd, seconds, calls, measured?) for one planned trial."""
    from grading import ATTACK_VARIANTS
    a, v = ATTACK_VARIANTS[spec.attack]
    attack = a + ("-" + v if v else "")
    rows = stats.get((spec.defence, attack, spec.family))
    measured = bool(rows)
    if not rows:
        rows = [r for (d, at, f), rs in stats.items() if at == attack and f == spec.family for r in rs]
    if rows:
        return _mean(rows, "cost_usd"), _mean(rows, "latency_ms") / 1000, _mean(rows, "n_llm_calls"), measured
    mc = cfg.models[spec.family]
    calls = 6
    usd = calls * (1000 * float(mc.price_in_per_mtok) + 600 * float(mc.price_out_per_mtok)) / 1e6
    return usd, calls * 2.5, calls, False


def estimate_specs(specs, cfg, quiet=False) -> dict:
    stats = pilot_stats()
    usd = secs = calls = 0.0
    measured = 0
    for s in specs:
        u, t, c, m = per_trial(s, cfg, stats)
        usd, secs, calls, measured = usd + u, secs + t, calls + c, measured + m
    conc = max(1, int(cfg.experiment.concurrency))
    out = {"trials": len(specs), "usd": usd, "hours": secs / 3600 / conc, "calls": calls,
           "measured_share": measured / len(specs) if specs else 0}
    if not quiet:
        print(f"{len(specs)} trials, ~{calls:.0f} LLM calls, ~${usd:.2f}, ~{out['hours']:.1f} h at concurrency {conc} "
              f"({out['measured_share']:.0%} of trials priced from pilot data)")
    return out


def main() -> int:
    from run import build_plan
    cfg = load_config()
    tiers = {
        "T1 honest (family 1)": build_plan("honest", "main", cfg),
        "T1 core matrix (family 1)": build_plan("core", "main", cfg),
        "T2 family 2 (honest + A5)": build_plan("family2", "main", cfg),
        "T2 monitor ablations": build_plan("ablation", "main", cfg),
        "T3 E4 D1fix": build_plan("ext-E4", "main", cfg),
        "T3 E5 salient account": build_plan("ext-E5", "main", cfg),
        "T3 E6 effort": build_plan("ext-E6", "main", cfg),
    }
    lines = ["# Cost and time estimate", "",
             "Measured from the pilot (`results/pilot/trials`). Cells without pilot data use the nearest measured cell, "
             "then a default of 6 calls at 1,000 input and 600 output tokens each.", "",
             "| Tier / experiment | Trials | LLM calls | USD | Hours (at configured concurrency) | Share priced from pilot |",
             "| --- | --- | --- | --- | --- | --- |"]
    total = {"trials": 0, "usd": 0.0, "hours": 0.0, "calls": 0.0}
    for name, specs in tiers.items():
        e = estimate_specs(specs, cfg, quiet=True)
        for k in total:
            total[k] += e[k]
        lines.append(f"| {name} | {e['trials']} | {e['calls']:.0f} | {e['usd']:.2f} | {e['hours']:.1f} | {e['measured_share']:.0%} |")
    lines.append(f"| **Total** | {total['trials']} | {total['calls']:.0f} | **{total['usd']:.2f}** | {total['hours']:.1f} | |")
    lines += ["", f"Budget: warning at ${float(cfg.experiment.budget_usd_warn):.0f}, hard cap at "
              f"${float(cfg.experiment.budget_usd_hard_cap):.0f} (config/experiment.toml)."]
    path = ROOT / "docs" / "COST_ESTIMATE.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
