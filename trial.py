"""Run one trial end to end and return its result record (RUNBOOK Section 6.10)."""
from __future__ import annotations

import json
import os
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from random import Random

from agents import PROMPT_SHA, make_agents
from bus import Bus
from clock import SimClock, start_ms_for_seed
from config import ROOT, load_config
from defences import make_defence
from grading import ATTACK_VARIANTS, CSV_COLUMNS, git_sha, grade_trial
from llm import ConfigError, make_llm
from message import AGENTS, new_hex
from runlog import RunLogger
from world import World

LOG_DIR = ROOT / "logs"
TRIALS_DIR = ROOT / "results" / "trials"


@dataclass
class TrialSpec:
    experiment: str          # honest | core | family2 | ablation | ext-E4 ... | oracle | test
    phase: str               # pilot | main | oracle | test
    tier: str                # T1 | T2 | T3
    defence: str
    attack: str              # none | A1g | A1r | A2f | A2s | A3 | A4d | A4l | A5b | A5p | A5d | A5x
    family: str              # family1 | family2
    seed: int
    trial: int
    target_invoice: str
    mock: bool = False
    overrides: dict = field(default_factory=dict)   # e.g. E5 salient account, E6 effort
    variant_label: str = ""

    @property
    def run_id(self) -> str:
        d = self.defence.replace("+", "p")
        label = f"-{self.variant_label}" if self.variant_label else ""
        prefix = "" if self.phase == "main" else f"{self.phase}-"
        return f"{prefix}{self.experiment}{label}-{d}-{self.attack}-{self.family}-s{self.seed}-t{self.trial:02d}"


def _atomic_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _error_record(spec: TrialSpec, cfg, error_type: str) -> dict:
    rec = {c: "" for c in CSV_COLUMNS}
    attack_class, variant = ATTACK_VARIANTS.get(spec.attack, (spec.attack, ""))
    model_cfg = cfg.models[spec.family]
    rec.update(run_id=spec.run_id, defence=spec.defence, attack=attack_class, attack_variant=variant,
               model="mock-gullible" if spec.mock else model_cfg.model, seed=spec.seed, trial=spec.trial,
               status="error", error_type=error_type, phase=spec.phase, experiment=spec.experiment,
               tier=spec.tier, family=spec.family, target_invoice=spec.target_invoice,
               timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               prompt_sha=PROMPT_SHA, config_sha=cfg.sha256, git_sha=git_sha(),
               variant_label=spec.variant_label)
    return rec


def run_trial(spec: TrialSpec, cfg=None, limiter=None, log_dir: Path = LOG_DIR,
              trials_dir: Path | None = TRIALS_DIR) -> dict:
    """Run one trial. Returns the results record (status 'ok' or 'error').
    ConfigError (bad request / bad key) is re-raised so the runner halts."""
    base_cfg = cfg or load_config()
    cfg = base_cfg.with_overrides(spec.overrides) if spec.overrides else base_cfg
    rng = Random(spec.seed)
    clock = SimClock(start_ms_for_seed(spec.seed), real_time=True)
    log = RunLogger(Path(log_dir) / f"{spec.run_id}.jsonl", spec.run_id, clock)
    record: dict
    try:
        log.log("trial_start", spec=asdict(spec), config_sha=cfg.sha256, prompt_sha=PROMPT_SHA,
                overrides=cfg.overrides, git_sha=git_sha())
        world = World(clock, log)
        defence = make_defence(spec.defence)
        defence.setup(world, clock, rng, list(AGENTS), cfg, log)
        bus = Bus(clock, defence, log, rng)
        llm = make_llm(spec.family, cfg, mock=spec.mock, limiter=limiter)
        agents = make_agents(world, bus, log, llm, cfg, defence, rng, clock)
        attack = None
        if spec.attack != "none":
            from attacks import make_attack
            attack = make_attack(spec.attack, cfg, bus, world, defence, clock, rng, log)
            attack.setup()
        task = world.register_task("T-" + new_hex(rng, 4).upper(), spec.target_invoice)
        log.log("task_registered", task=task.to_dict())
        target = world.invoice(task.invoice_id)   # Mallory knows the invoice, not the task ID
        t0 = time.perf_counter()
        if attack is not None:
            attack.before_task(target)
        outcome = agents.orchestrator.run(task)
        defence.end_task()
        if attack is not None:
            attack.after_task(target)
        latency_ms = (time.perf_counter() - t0) * 1000
        record = grade_trial(spec, cfg, world, log, agents.runtime.stats, bus.stats, latency_ms)
        record["prompt_sha"] = PROMPT_SHA
        log.log("trial_end", status="ok", outcome=outcome, ledger=[r.to_dict() for r in world.ledger],
                success=record["success"], honest_task_completed=record["honest_task_completed"])
    except ConfigError:
        log.log("trial_end", status="error", error_type="ConfigError", traceback=traceback.format_exc())
        log.close()
        raise
    except Exception as e:  # harness or transient API error: never counted as an outcome (rule R9)
        record = _error_record(spec, cfg, type(e).__name__)
        log.log("trial_end", status="error", error_type=type(e).__name__, traceback=traceback.format_exc())
    finally:
        log.close()
    if trials_dir is not None:
        _atomic_write_json(Path(trials_dir) / f"{spec.run_id}.json", record)
    return record
