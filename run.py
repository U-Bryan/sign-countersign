r"""Experiment runner (RUNBOOK 6.12): plan, schedule, run (resumably), and report status.

Examples (PowerShell, from the project root):
  .\.venv\Scripts\python.exe run.py --experiment honest --phase pilot --trials 1
  .\.venv\Scripts\python.exe run.py --experiment core --phase main
  .\.venv\Scripts\python.exe run.py --experiment oracle --mock
  .\.venv\Scripts\python.exe run.py --status
  .\.venv\Scripts\python.exe run.py --rebuild-csv
Exit codes: 0 ok, 2 configuration error (halted), 3 budget cap reached.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from random import Random

from attacks import CORE_ATTACKS
from config import ROOT, load_config
from defences import CORE_DEFENCES
from grading import CSV_COLUMNS
from llm import ConfigError, RateLimiter
from trial import TrialSpec, run_trial
from world import INVOICES

A5_VARIANTS = ("A5b", "A5p", "A5d")
EXPERIMENT_OFFSET = {"honest": 0, "core": 100, "family2": 200, "ablation": 300, "ext-E4": 400,
                     "ext-E5": 500, "ext-E6": 600, "ext-E7": 700, "ext-E8": 800, "oracle": 900}
TIER = {"honest": "T1", "core": "T1", "family2": "T2", "ablation": "T2", "oracle": "T1"}


def phase_dirs(phase: str) -> tuple[Path, Path, Path]:
    """(trials_dir, logs_dir, csv_path) for a phase. Pilot and oracle data never mix with main data."""
    if phase == "main":
        return ROOT / "results" / "trials", ROOT / "logs", ROOT / "results" / "results.csv"
    if phase == "pilot":
        return ROOT / "results" / "pilot" / "trials", ROOT / "logs" / "pilot", ROOT / "results" / "pilot" / "results_pilot.csv"
    if phase == "oracle":
        return ROOT / "results" / "oracle" / "trials", ROOT / "logs" / "oracle", ROOT / "results" / "oracle.csv"
    if phase == "mock":  # rehearsal data from the mock LLM; never analysed as results
        return ROOT / "results" / "mock" / "trials", ROOT / "logs" / "mock", ROOT / "results" / "mock" / "results_mock.csv"
    raise ValueError(phase)


# ----- planning ---------------------------------------------------------------------
def experiment_cells(experiment: str, defences=None, attacks=None) -> list[tuple]:
    """Cells as (defence, attack, family_key, overrides_json, variant_label)."""
    f1 = "family1"
    if experiment == "honest":
        cells = [(d, "none", f1, "{}", "") for d in (defences or CORE_DEFENCES)]
    elif experiment == "core":
        cells = [(d, a, f1, "{}", "") for d in (defences or CORE_DEFENCES) for a in (attacks or CORE_ATTACKS)]
    elif experiment == "family2":
        cells = [(d, "none", "family2", "{}", "") for d in CORE_DEFENCES]
        cells += [(d, a, "family2", "{}", "") for d in CORE_DEFENCES for a in A5_VARIANTS]
    elif experiment == "ablation":
        cells = [("D0+M", a, f1, "{}", "") for a in ("none",) + CORE_ATTACKS]
        cells += [(d, a, f1, "{}", "") for d in ("D3-R1", "D0+M-R1") for a in ("A1r", "A3", "A4l", "A5b")]
    elif experiment == "ext-E4":
        cells = [("D1fix", a, f1, "{}", "") for a in ("A1r", "A2f", "A2s")]
    elif experiment == "ext-E5":
        ov = json.dumps({"world": {"mallory_account": "GB-MALLORY-666"}})
        cells = [("D2", a, f1, ov, "salient") for a in A5_VARIANTS]
    elif experiment == "ext-E6":
        cells = [("D2", a, f1, json.dumps({"models": {f1: {"effort": lvl}}}), f"effort-{lvl}")
                 for lvl in ("low", "high") for a in A5_VARIANTS]
    elif experiment == "oracle":
        from oracle_table import ORACLE_TABLE
        cells = [(d, a, f1, "{}", "") for d, row in ORACLE_TABLE.items() for a in row]
    else:
        raise SystemExit(f"experiment {experiment!r} is not implemented in run.py")
    if defences and experiment not in ("honest", "core"):
        cells = [c for c in cells if c[0] in defences]
    if attacks and experiment not in ("core",):
        cells = [c for c in cells if c[1] in attacks or c[1] == "none"]
    return sorted(set(cells))


def build_plan(experiment: str, phase: str, cfg, trials: int | None = None, defences=None, attacks=None,
               mock: bool = False) -> list[TrialSpec]:
    cells = experiment_cells(experiment, defences, attacks)
    base = int(cfg.experiment.seed_base)
    offset = EXPERIMENT_OFFSET[experiment]
    specs = []
    for ci, (d, a, fam, ov, label) in enumerate(cells):
        if trials is not None:
            n = trials if a != "none" else trials * int(cfg.experiment.honest_tasks)
        elif phase == "pilot":
            n = int(cfg.experiment.pilot_trials_per_cell) if a != "none" else int(cfg.experiment.honest_tasks)
        elif experiment == "oracle":
            n = 3
        else:
            n = int(cfg.experiment.trials_per_cell)
        if a == "none" and trials is None and phase == "main":
            n = int(cfg.experiment.honest_tasks) * int(cfg.experiment.honest_reps_per_task)
        for t in range(n):
            specs.append(TrialSpec(
                experiment=experiment, phase=phase, tier=TIER.get(experiment, "T3"), defence=d, attack=a,
                family=fam, seed=base + 1000 * (offset + ci) + t, trial=t,
                target_invoice=INVOICES[t % len(INVOICES)].invoice_id, mock=mock or experiment == "oracle",
                overrides=json.loads(ov), variant_label=label))
    return specs


def write_seeds(specs: list[TrialSpec]) -> None:
    path = ROOT / "results" / "seeds.csv"
    rows = {}
    if path.exists():
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                rows[r["run_id"]] = r
    for s in specs:
        rows[s.run_id] = {"run_id": s.run_id, "experiment": s.experiment, "phase": s.phase, "defence": s.defence,
                          "attack": s.attack, "family": s.family, "variant_label": s.variant_label,
                          "trial": s.trial, "seed": s.seed, "target_invoice": s.target_invoice}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(next(iter(rows.values())).keys()))
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["run_id"]))


# ----- results files ------------------------------------------------------------------
_csv_lock = threading.Lock()


def load_trials(trials_dir: Path) -> dict[str, dict]:
    out = {}
    if trials_dir.exists():
        for p in trials_dir.glob("*.json"):
            try:
                out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
    return out


def append_csv(csv_path: Path, rec: dict) -> None:
    with _csv_lock:
        new = not csv_path.exists()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(rec)


def rebuild_csv(phase: str) -> int:
    trials_dir, _, csv_path = phase_dirs(phase)
    recs = sorted(load_trials(trials_dir).values(), key=lambda r: r["run_id"])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = csv_path.with_suffix(".csv.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)
    os.replace(tmp, csv_path)
    return len(recs)


def progress(line: str) -> None:
    p = ROOT / "results" / "progress.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


def total_spend() -> float:
    spent = 0.0
    for phase in ("main", "pilot"):
        for r in load_trials(phase_dirs(phase)[0]).values():
            try:
                spent += float(r.get("cost_usd") or 0)
            except ValueError:
                pass
    return spent


# ----- execution ------------------------------------------------------------------------
def execute(specs: list[TrialSpec], cfg, concurrency: int, max_trials: int | None = None) -> int:
    trials_dir, logs_dir, csv_path = phase_dirs(specs[0].phase)
    existing = load_trials(trials_dir)
    todo = [s for s in specs if existing.get(s.run_id, {}).get("status") != "ok"]
    Random(int(cfg.experiment.seed_base)).shuffle(todo)
    if max_trials is not None:
        todo = todo[:max_trials]
    write_seeds(specs)
    limiter = RateLimiter(float(cfg.experiment.max_requests_per_minute))
    warn = float(cfg.experiment.budget_usd_warn)
    cap = float(os.environ.get("SCC_BUDGET_CAP", cfg.experiment.budget_usd_hard_cap))
    spent = total_spend()
    progress(f"START {specs[0].experiment}/{specs[0].phase}: {len(todo)} to run ({len(specs)} planned), spent so far ${spent:.4f}")
    print(f"{len(todo)} trials to run ({len(specs) - len(todo)} already done). Spend so far: ${spent:.4f}")
    attempts: dict[str, int] = {}
    queue = list(todo)
    done = errors = 0
    warned = spent >= warn
    exit_code = 0
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        running = {}
        while queue or running:
            while queue and len(running) < concurrency and exit_code == 0:
                s = queue.pop(0)
                attempts[s.run_id] = attempts.get(s.run_id, 0) + 1
                running[ex.submit(run_trial, s, cfg, limiter, logs_dir, trials_dir)] = s
            if not running:
                break
            finished, _ = wait(list(running), return_when=FIRST_COMPLETED)
            for fut in finished:
                s = running.pop(fut)
                try:
                    rec = fut.result()
                except ConfigError as e:
                    progress(f"HALT ConfigError on {s.run_id}: {e}")
                    print(f"\nHALTED: configuration error on {s.run_id}:\n  {e}", file=sys.stderr)
                    exit_code = 2
                    queue.clear()
                    continue
                append_csv(csv_path, rec)
                done += 1
                spent += float(rec.get("cost_usd") or 0)
                if rec["status"] != "ok":
                    errors += 1
                    if attempts[s.run_id] < 4:
                        queue.append(s)
                progress(f"{rec['status']:5s} {s.run_id} success={rec.get('success')} cost=${float(rec.get('cost_usd') or 0):.5f}")
                if done % 25 == 0:
                    rate = done / max(time.time() - t_start, 1e-9)
                    progress(f"SUMMARY done={done} errors={errors} spent=${spent:.4f} rate={rate * 60:.1f}/min")
                    print(f"  {done} done, {errors} errors, ${spent:.4f} spent")
                if not warned and spent >= warn:
                    warned = True
                    progress(f"BUDGET WARNING: ${spent:.2f} >= ${warn:.2f}")
                    print(f"BUDGET WARNING: ${spent:.2f} spent (warn level ${warn:.2f})")
                if spent >= cap and exit_code == 0:
                    progress(f"BUDGET CAP: ${spent:.2f} >= ${cap:.2f}; stopping")
                    print(f"BUDGET CAP REACHED (${spent:.2f}); stopping after running trials finish.")
                    exit_code = 3
                    queue.clear()
    n = rebuild_csv(specs[0].phase)
    write_manifest(specs[0].phase, cfg)
    progress(f"END {specs[0].experiment}/{specs[0].phase}: done={done} errors={errors} spent=${spent:.4f} csv_rows={n}")
    print(f"Finished: {done} trials run, {errors} error results, total spend ${spent:.4f}. CSV rows: {n}.")
    return exit_code


def write_manifest(phase: str, cfg) -> None:
    """results/run_manifest.json (main) or results/<phase>/run_manifest.json: environment and run summary."""
    import importlib.metadata as md
    import platform
    from agents import PROMPT_SHA
    from grading import git_sha
    recs = list(load_trials(phase_dirs(phase)[0]).values())
    ok = [r for r in recs if r.get("status") == "ok"]
    stamps = sorted(r["timestamp"] for r in recs if r.get("timestamp"))
    pkgs = {}
    for name in ("pyotp", "cryptography", "anthropic", "openai", "pandas", "matplotlib", "scipy", "statsmodels", "numpy"):
        try:
            pkgs[name] = md.version(name)
        except md.PackageNotFoundError:
            pkgs[name] = None
    manifest = {
        "phase": phase, "first_trial_end": stamps[0] if stamps else None, "last_trial_end": stamps[-1] if stamps else None,
        "python": platform.python_version(), "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu": platform.processor() or platform.machine(), "cpu_count": os.cpu_count(), "packages": pkgs,
        "git_sha": git_sha(), "config_sha": cfg.sha256, "prompt_sha": PROMPT_SHA,
        "models_requested": {k: cfg.models[k].model for k in cfg.models.keys()},
        "model_settings": {k: cfg.models[k].to_dict() for k in cfg.models.keys()},
        "models_returned": sorted({m for r in ok for m in str(r.get("model_returned", "")).split(";") if m}),
        "trials": len(recs), "trials_ok": len(ok), "trials_error": len(recs) - len(ok),
        "spend_usd": round(sum(float(r.get("cost_usd") or 0) for r in ok), 6),
        "experiments": sorted({r["experiment"] for r in recs}),
    }
    path = (ROOT / "results" / "run_manifest.json") if phase == "main" else (phase_dirs(phase)[0].parent / "run_manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")


def status() -> None:
    for phase in ("main", "pilot", "oracle"):
        recs = load_trials(phase_dirs(phase)[0])
        if not recs:
            continue
        cells: dict[tuple, dict] = {}
        for r in recs.values():
            key = (r["experiment"], r["defence"], r["attack"] + ("-" + r["attack_variant"] if r["attack_variant"] else ""),
                   r["family"], r.get("variant_label", ""))
            c = cells.setdefault(key, {"ok": 0, "error": 0, "success": 0})
            c[r["status"] if r["status"] in ("ok", "error") else "error"] += 1
            if r["status"] == "ok":
                c["success"] += int(r["success"] or 0)
        print(f"\n== phase {phase}: {len(recs)} trial files")
        print(f"{'experiment':10s} {'defence':8s} {'attack':14s} {'family':8s} {'label':12s} ok  err  succ")
        for key in sorted(cells):
            c = cells[key]
            print(f"{key[0]:10s} {key[1]:8s} {key[2]:14s} {key[3]:8s} {key[4]:12s} {c['ok']:3d} {c['error']:4d} {c['success']:5d}")
    print(f"\nTotal API spend recorded (main + pilot): ${total_spend():.4f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment")
    ap.add_argument("--phase", default="main", choices=["pilot", "main", "oracle", "mock"])
    ap.add_argument("--family", default=None, help="override the family for every cell")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--defences", default=None)
    ap.add_argument("--attacks", default=None)
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--max-trials", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--rebuild-csv", action="store_true")
    args = ap.parse_args(argv)
    os.environ.setdefault("PYTHONUTF8", "1")
    cfg = load_config()
    if args.status:
        status()
        return 0
    if args.rebuild_csv:
        for phase in ("main", "pilot", "oracle"):
            print(f"{phase}: {rebuild_csv(phase)} rows")
        return 0
    if not args.experiment:
        ap.error("--experiment is required")
    phase = "oracle" if args.experiment == "oracle" else args.phase
    defences = args.defences.split(",") if args.defences else None
    attacks = None if not args.attacks or args.attacks == "all" else args.attacks.split(",")
    specs = build_plan(args.experiment, phase, cfg, args.trials, defences, attacks, args.mock)
    if args.family:
        for s in specs:
            s.family = args.family
    if args.estimate:
        from scripts.estimate_cost import estimate_specs
        estimate_specs(specs, cfg)
        return 0
    if args.dry_run:
        cells = sorted({(s.defence, s.attack, s.family, s.variant_label) for s in specs})
        print(f"{len(specs)} trials in {len(cells)} cells, phase {phase}:")
        for c in cells:
            print("  ", c, sum(1 for s in specs if (s.defence, s.attack, s.family, s.variant_label) == c))
        return 0
    if not specs:
        print("nothing planned")
        return 0
    return execute(specs, cfg, args.concurrency or int(cfg.experiment.concurrency), args.max_trials)


if __name__ == "__main__":
    sys.exit(main())
