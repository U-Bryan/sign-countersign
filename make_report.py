r"""Generate the reports, excerpts, docs and handoff bundle (RUNBOOK Section 11).

Every number comes from tables/values.json or a generated table and is wrapped in a
<!--v:key-->value<!--/v--> marker (rule R5). Generated tables are wrapped in
<!--table:name--> ... <!--/table--> markers.

Usage:
  .\.venv\Scripts\python.exe make_report.py               # report/ and docs/ from the main analysis
  .\.venv\Scripts\python.exe make_report.py --handoff     # also build handoff/ and its zip
  .\.venv\Scripts\python.exe make_report.py --root results\mock\analysis --csv results\mock\results_mock.csv --logs logs\mock --out results\mock\report
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import textwrap
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config import ROOT, load_config

VERIFY = "[VERIFY]"


class Ctx:
    def __init__(self, root: Path, csv_path: Path, logs: Path, out: Path):
        self.root, self.csv_path, self.logs, self.out = root, csv_path, logs, out
        vp = root / "tables" / "values.json"
        self.values = json.loads(vp.read_text(encoding="utf-8")) if vp.exists() else {}
        self.rows = list(csv.DictReader(open(csv_path, encoding="utf-8", newline=""))) if csv_path.exists() else []

    def v(self, key: str, fmt=None) -> str:
        if key not in self.values:
            return f"[MISSING: {key}]"
        val = self.values[key]
        shown = fmt(val) if fmt else val
        return f"<!--v:{key}-->{shown}<!--/v-->"

    def has(self, key: str) -> bool:
        return key in self.values

    def table(self, name: str) -> str:
        p = self.root / "tables" / f"{name}.md"
        if p.exists():
            body = p.read_text(encoding="utf-8").strip()
        else:
            # Some tables (bench.csv, written by bench.py) have no .md twin: render the CSV.
            pc = self.root / "tables" / f"{name}.csv"
            if not pc.exists():
                return f"_(table {name} not produced: no data yet)_"
            body = csv_to_md(pc)
        return f"<!--table:{name}-->\n{body}\n<!--/table-->"

    def fig(self, stem: str, caption: str) -> str:
        p = self.root / "figures" / f"{stem}.png"
        if not p.exists():
            return f"_(figure {stem} not produced: no data yet)_"
        rel = Path("..") / p.relative_to(self.root) if self.out.parent == self.root else p
        return f"![{caption}]({rel.as_posix()})\n\n*{caption}*"


def csv_to_md(p: Path) -> str:
    """Render a small CSV as a Markdown pipe table."""
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return ""

    def esc(s: str) -> str:
        return s.replace("|", "\\|")

    head, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(esc(h) for h in head) + " |", "|" + "|".join(" --- " for _ in head) + "|"]
    lines += ["| " + " | ".join(esc(x) for x in r) + " |" for r in body]
    return "\n".join(lines)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "n/a"


def pct(x) -> str:
    return f"{100 * float(x):.0f}%"


# ----- excerpts -----------------------------------------------------------------------------
EXCERPTS = [
    ("box1_a5_success_d2", "Box 1: a prompt-injected insider succeeds under per-agent signatures (A5, D2)",
     lambda r: r["defence"] == "D2" and r["attack"] == "A5" and r["success"] == "1"),
    ("ex2_a3_success_d1", "A relay tampers with the payment instruction after the TOTP handshake (A3, D1)",
     lambda r: r["defence"] == "D1" and r["attack"] == "A3" and r["success"] == "1"),
    ("ex3_monitor_block_d3", "The reference monitor blocks an injected payment (A5, D3)",
     lambda r: r["defence"] == "D3" and r["attack"] == "A5" and r["f4_blocked"] == "1"),
    ("ex4_a1_reflect_d1", "Reflection: the receiver's own code opens a channel (A1-reflect, D1)",
     lambda r: r["defence"] == "D1" and r["attack"] == "A1" and r["attack_variant"] == "reflect" and r["success"] == "1"),
    ("ex5_a4_lie_d2", "A stolen records key lies about bank details (A4-lie, D2)",
     lambda r: r["defence"] == "D2" and r["attack"] == "A4" and r["attack_variant"] == "lie" and r["success"] == "1"),
]


def render_chain(events: list[dict]) -> list[str]:
    out = []
    n = 0
    for e in events:
        ev = e["event"]
        line = None
        if ev == "task_registered":
            line = f"**User task** `{e['task']['task_id']}`: {e['task']['text']}"
        elif ev == "attack_step":
            extra = {k: v for k, v in e.items() if k not in ("seq", "event", "sim_time_ms", "wall_time_iso", "perf_ns",
                                                              "run_id", "attack", "step")}
            line = f"**Mallory** ({e.get('attack')}): `{e.get('step')}` {json.dumps(extra, ensure_ascii=False)[:400]}"
        elif ev == "tool_call":
            res = json.dumps(e.get("result", e.get("args")), ensure_ascii=False)
            line = f"**{e['agent']} tool** `{e['tool']}` {json.dumps(e.get('args'), ensure_ascii=False)} → {res[:600]}"
        elif ev == "llm_call" and e.get("parsed"):
            line = f"**{e['agent']} (LLM) decides**: `{json.dumps(e['parsed'], ensure_ascii=False)[:500]}`"
        elif ev == "sent" and not str(e["msg"]["body"].get("kind", "")).startswith("hs_"):
            m = e["msg"]
            auth = "signed" if "sig" in m["auth"] else ("channel " + m["auth"]["d1_channel"][:8] if "d1_channel" in m["auth"] else "no auth")
            line = (f"**Bus**: `{m['sender']} → {m['recipient']}` ({auth}, origin: {m['origin']}) "
                    f"`{json.dumps(m['body'], ensure_ascii=False)[:500]}`")
        elif ev == "sent" and str(e["msg"]["body"].get("kind", "")).startswith("hs_"):
            m = e["msg"]
            line = f"Handshake `{m['body']['kind']}` `{m['sender']} → {m['recipient']}` {json.dumps({k: v for k, v in m['body'].items() if k != 'kind'})}"
        elif ev == "modified":
            line = f"**Mallory modifies in transit**: {json.dumps(e['changes'], ensure_ascii=False)}"
        elif ev == "rejected":
            line = f"**Rejected** at {e.get('receiver')}: {e.get('failed_checks')}"
        elif ev == "delivered" and e.get("leg") == "request":
            line = f"Delivered to {e['receiver']} (attributed to `{e['attributed_sender']}`, basis: {e['basis']})"
        elif ev == "monitor_decision":
            line = (f"**Monitor**: {e['outcome']}; first rule `{e['first_rule'] or '-'}`; failed {e['rules_failed']}; "
                    f"request {json.dumps(e['request'])}")
        elif ev == "payment":
            r = e["row"]
            line = f"**Ledger row**: {r['invoice_id']} → `{r['account']}` £{r['amount_pence'] / 100:,.2f}, requested_by `{r['requested_by']}` ({r['attribution_basis']})"
        if line:
            n += 1
            out.append(f"{n}. {line}")
    return out


def write_excerpts(c: Ctx) -> dict:
    exdir = c.out / "excerpts"
    exdir.mkdir(parents=True, exist_ok=True)
    chosen = {}
    for stem, title, pred in EXCERPTS:
        matches = sorted((r for r in c.rows if r.get("status") == "ok" and pred(r)), key=lambda r: r["run_id"])
        if not matches:
            (exdir / f"{stem}.md").write_text(f"# {title}\n\nNo matching trial in the data (this outcome did not occur).\n",
                                              encoding="utf-8")
            continue
        r = matches[0]
        lp = c.logs / f"{r['run_id']}.jsonl"
        events = [json.loads(x) for x in lp.read_text(encoding="utf-8").splitlines() if x.strip()] if lp.exists() else []
        body = render_chain(events)
        text = (f"# {title}\n\nRun `{r['run_id']}` (the first matching trial by run ID; {len(matches)} trials matched). "
                f"Model: `{r['model_returned'] or r['model']}`. Target {r['target_invoice']}. Ledger-based success: {r['success']}.\n\n"
                + "\n".join(body) + "\n")
        (exdir / f"{stem}.md").write_text(text, encoding="utf-8")
        chosen[stem] = r["run_id"]
    if "box1_a5_success_d2" in chosen:
        render_box_png(exdir / "box1_a5_success_d2.md", c.root / "figures" / "fig3_a5_walkthrough")
    return chosen


def render_box_png(md: Path, stem: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lines = []
    for raw in md.read_text(encoding="utf-8").splitlines():
        raw = raw.replace("**", "").replace("`", "")
        lines += textwrap.wrap(raw, 118) or [""]
    lines = lines[:70]
    fig = plt.figure(figsize=(7.5, 0.16 * len(lines) + 0.4))
    fig.text(0.01, 0.99, "\n".join(lines), va="top", ha="left", family="monospace", fontsize=6.2, color="#0b0b0b")
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(stem.with_suffix(".png"), dpi=300, metadata={"Software": None})
    fig.savefig(stem.with_suffix(".svg"), metadata={"Date": None})
    plt.close(fig)


# ----- headline -----------------------------------------------------------------------------
def headline(c: Ctx) -> str:
    V = c.values
    need = ["headline.A1pooled.D0", "headline.A1pooled.D2", "headline.A5pooled.D1", "headline.A5pooled.D2",
            "headline.A5pooled.D3"]
    if not all(k in V for k in need):
        return "[MISSING: headline numbers; run the main experiment and analyse.py]"
    reduced = V["headline.A1pooled.D2.p"] < V["headline.A1pooled.D0.p"]
    s = (f"Per-agent signatures {'take' if reduced else 'did not reduce'} outsider ASR "
         f"{'from ' if reduced else '('}{c.v('headline.A1pooled.D0')} {'to' if reduced else 'vs'} {c.v('headline.A1pooled.D2')}{'' if reduced else ')'}. ")
    if c.has("asr.core.D1.A1g.fmt") and c.has("asr.core.D1.A1r.fmt"):
        s += (f"The shared-code handshake reaches {c.v('asr.core.D1.A1g.fmt')} against a guessing outsider, and "
              f"{c.v('asr.core.D1.A1r.fmt')} against one who reflects the code. ")
    f1_resists = V.get("asr.core.D2.A5*.k", 1) == 0 and V.get("asr.core.D1.A5*.k", 1) == 0
    f2_fooled = V.get("headline.f2.A5pooled.D2.k", 0) > 0
    m1 = V.get("model.family1", "family-1")
    m2 = V.get("model.family2", "family-2")

    def a4l_sentence() -> str:
        if c.has("asr.core.D2.A4l.fmt") and c.has("asr.core.D3.A4l.fmt"):
            return (f"An insider with a stolen data-source key diverted payments under per-agent signatures "
                    f"({c.v('asr.core.D2.A4l.fmt')}) until the external monitor stopped it ({c.v('asr.core.D3.A4l.fmt')}). ")
        return ""

    if f2_fooled:
        if V.get("verdict.H6.family2") == "supported":
            verb2 = "cut that to"
        elif V.get("headline.f2.A5pooled.D3.p", 1) < V.get("headline.f2.A5pooled.D2.p", 0):
            verb2 = "reduced that (not significantly after Holm correction) to"
        else:
            verb2 = "left it at"
        s += (f"With {m2} agents, a prompt-injected insider still succeeded {c.v('headline.f2.A5pooled.D1')} (D1) and "
              f"{c.v('headline.f2.A5pooled.D2')} (D2) of the time under the cryptographic defences; an external monitor "
              f"{verb2} {c.v('headline.f2.A5pooled.D3')}")
        s += (f", at a cost of {c.v('cost2.D3.frr_fmt')} false rejections on honest tasks. " if c.has("cost2.D3.frr_fmt") else ". ")
        if f1_resists:
            s += (f"Agents running {m1} resisted every injection ({c.v('headline.A5pooled.D0')} with no defence, "
                  f"{c.v('headline.A5pooled.D2')} under signatures): there the model, not the cryptography, stopped them. ")
        s += a4l_sentence()
        if c.has("cost.D3.frr_fmt"):
            s += f"With {m1}, the monitor cost {c.v('cost.D3.frr_fmt')} false rejections on honest tasks."
        return s.strip()
    if f1_resists:
        # Model-level resistance and no second family: the "insider" claim rests on A4-lie.
        s += (f"No prompt injection succeeded against these agents under any defence "
              f"({c.v('headline.A5pooled.D0')} with no defence, {c.v('headline.A5pooled.D2')} under signatures): the model, "
              f"not the cryptography, stopped them. ")
        s += a4l_sentence()
        if c.has("cost.D3.frr_fmt"):
            s += f"The monitor cost {c.v('cost.D3.frr_fmt')} false rejections on honest tasks."
        return s.strip()
    s += (f"A prompt-injected insider still succeeds {c.v('headline.A5pooled.D1')} (D1) and {c.v('headline.A5pooled.D2')} (D2) "
          f"of the time under the cryptographic defences. ")
    if V.get("verdict.H6") == "supported":
        verb = "cuts that to"
    elif V["headline.A5pooled.D3.p"] < V["headline.A5pooled.D2.p"]:
        verb = "reduces that (not significantly after Holm correction) to"
    else:
        verb = "leaves it at"
    s += f"An external monitor {verb} {c.v('headline.A5pooled.D3')}"
    if c.has("cost.D3.frr_fmt"):
        s += f", at a cost of {c.v('cost.D3.frr_fmt')} false rejections on honest tasks"
    return s + "."


def surprises(c: Ctx) -> list[str]:
    from oracle_table import ORACLE_TABLE
    out = []
    V = c.values
    for d in ("D0", "D1", "D2", "D3"):
        for col, o in ORACLE_TABLE[d].items():
            k = f"asr.core.{d}.{col}.p"
            if k in V and abs(V[k] - o) > 0.30:
                out.append(f"{col} under {d}: LLM ASR {c.v(f'asr.core.{d}.{col}.fmt')} vs protocol-level {'through' if o else 'stopped'}. [TO FILL: comment]")
    for key, label in (("asr.core.D1.A2f.fmt", "A2-fast under D1"), ("asr.core.D1.A1r.fmt", "A1-reflect under D1"),
                       ("asr.core.D2.A4l.fmt", "A4-lie under D2")):
        if key in V:
            out.append(f"{label}: {c.v(key)}. [TO FILL: comment]")
    for d in ("D0", "D1", "D2", "D3"):
        if V.get(f"cost.{d}.frr", 0) > 0:
            out.append(f"Non-zero FRR under {d}: {c.v(f'cost.{d}.frr_fmt')}. See docs/FALSE_REJECTIONS.md. [TO FILL: comment]")
    return out


# ----- documents ------------------------------------------------------------------------------
def results_md(c: Ctx, chosen: dict) -> str:
    res = c.csv_path
    lines = [
        "# Results: Sign and Countersign", "",
        "_Generated by `make_report.py` from `tables/values.json` and the generated tables. Do not edit numbers by hand._", "",
        "## Headline", "", headline(c), "",
        "## Hypothesis verdicts (pre-registered rules)", "", c.table("table10_hypotheses"), "",
        "## Attack success matrix", "", c.fig("fig2_asr_heatmap", "Figure 2. Attack success rate per defence and attack (k/n, family 1)."), "",
        c.table("table2b_headline_matrix"), "", "Full matrix with 95% Wilson intervals:", "", c.table("table2_asr_matrix"), "",
        c.fig("fig4_asr_forest", "Figure 4. ASR with 95% Wilson intervals, by attack and defence."), "",
        "## Significance (adjacent defences, Fisher's exact test, Holm-adjusted over 30 tests)", "", c.table("table3_significance"), "",
        "## Costs (honest runs)", "", c.table("table4_costs"), "", "Microbenchmarks of the primitives:", "", c.table("bench"), "",
        c.fig("fig5_cost_tradeoff", "Figure 5. Protection against cost: mean ASR across the 10 attack columns vs false-rejection rate."), "",
        "## Which checks and rules did the work", "", c.fig("fig7_attribution", "Figure 7. Failing transport checks under D2, and the monitor rule that blocked under D3."), "",
        c.table("table5_check_attribution"), "", c.table("table6_monitor_audit"), "",
        c.fig("fig7b_attribution_monitor_only", "Figure 7b. Monitor alone (D0+M): which rule blocked each attack."), "",
        "## Prompt injection (A5): funnel, variants, model families", "",
        c.fig("fig8_a5_funnel", "Figure 8. How far the injected text travelled through the agent chain."), "",
        c.table("table11_a5_funnel"), "", c.fig("fig6_a5_variants", "Figure 6. A5 success by variant and defence, per model family."), "",
        c.table("table7_a5_variants"), "", c.table("table7b_a5_variant_spread"), "", c.table("table8_family_compare"), "",
        "## Second model family: replication of the A5 column (Tier 2, exploratory per the pre-registration)", "",
        f"Family 1: {c.v('model.family1')}. Family 2: {c.v('model.family2')}.", "",
        c.fig("fig2c_family2_a5_heatmap", "Figure 2c. Prompt injection (A5) by defence, family 2."), "",
        c.table("table2c_family2_a5_matrix"), "", c.table("table3b_significance_family2"), "",
        c.fig("fig8b_a5_funnel_family2", "Figure 8b. How far the injected text travelled, family 2."), "",
        c.table("table11b_a5_funnel_family2"), "", "Honest-run costs, family 2:", "", c.table("table4b_costs_family2"), "",
        "## Protocol level vs model level", "", c.fig("fig9_oracle_vs_llm", "Figure 9. What each protocol lets through (top) vs what the LLM agents did (bottom)."), "",
        c.table("table12_model_resistance"), "",
        "## Ablations and extensions", "", c.fig("fig2b_ablation_heatmap", "Figure 2b. Monitor without crypto, monitor without R1, and the fixed handshake."), "",
        c.table("table2d_ablation_matrix"), "",
        c.fig("figE1_replay_delay", "Figure E1. Replay acceptance vs delay."), "", c.table("tableE1_replay_delay"), "",
        c.fig("figE2_skew_frr", "Figure E2. False rejections vs clock skew."), "", c.table("tableE2_skew_frr"), "",
        c.fig("figE3_bruteforce", "Figure E3. Brute force against the 6-digit handshake."), "", c.table("tableE3_bruteforce"), "",
        c.table("tableE_salient"), "", c.table("tableE_effort-low"), "", c.table("tableE_effort-high"), "",
        "## Log excerpts", "",
    ]
    for stem, title, _ in EXCERPTS:
        lines.append(f"- [{title}](excerpts/{stem}.md)" + (f" (run `{chosen[stem]}`)" if stem in chosen else " (did not occur)"))
    lines += ["", "## Surprises", ""] + [f"- {s}" for s in surprises(c)] + ["",
              "## Errors and exclusions", "", c.table("table9_errors"), "",
              "## Provenance", "",
              f"- results CSV: `{res.name}`, SHA-256 `{sha256(res)}`",
              f"- git commit: `{c.rows[0].get('git_sha') if c.rows else 'n/a'}`",
              f"- config SHA-256: `{c.rows[0].get('config_sha') if c.rows else 'n/a'}`",
              f"- prompt SHA-256: `{c.rows[0].get('prompt_sha') if c.rows else 'n/a'}`",
              f"- generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"]
    return "\n".join(lines) + "\n"


def paper_md(c: Ctx) -> str:
    return f"""# Sign and Countersign: Cryptographic Identity Is Necessary but Not Sufficient for Agent Swarms

[TO FILL: authors] · [TO FILL: affiliation, e.g. University of Bristol, EPSRC CDT in Cyber Security] · Swarm Alignment Sprint, Track 3 (Strengthening Agent Infrastructure), [TO FILL: sprint dates]

## Abstract (write last; claim no more than Table 10 supports)

[TO FILL after reading the verdict table.] Auto-generated headline for reference: {headline(c)}

## 1 Introduction (0.75 page)

[TO FILL: motivation in your own words: the soldier and countersign story.] Agent-to-agent protocols such as A2A {VERIFY} let agents act on each other's messages. We ask which attacks on that messaging each layer of identity defence stops, and which get past every cryptographic layer. Contributions: (1) a ground-truth testbed where success is read from a ledger, not from model text; (2) a 4 × 10 attack matrix with pre-registered success rules and 30 trials per cell; (3) a protocol-level oracle that separates what each protocol lets through from what the models resist; (4) a reusable attack suite and a minimum identity checklist for A2A deployments.

## 2 Related work (0.5 page)

Agent identity (Chan et al., IDs for AI Systems {VERIFY}); prompt injection between agents (Lee & Tiwari, Prompt Infection {VERIFY}; Greshake et al. {VERIFY}); AI control (Greenblatt et al. {VERIFY}); CaMeL-style system security (Debenedetti et al. {VERIFY}). Security protocols: TOTP (RFC 6238), Ed25519 (RFC 8032), TLS 1.3 (RFC 8446), Kerberos (RFC 4120), the Needham–Schroeder relay flaw (Lowe, 1996 {VERIFY}), reflection attacks on symmetric challenge–response, and the confused deputy (Hardy, 1988). [TO FILL: 3–4 sentences positioning the work.]

## 3 Threat model and setup (1.5 pages)

{c.fig("fig1_architecture", "Figure 1. The procurement workflow, the bus, the monitor and Mallory's entry points.")}

Three LLM agents (orchestrator, records, finance) pay fake invoices. Mallory is attack code with capabilities enforced per attack (Table: docs/THREAT_MODEL.md). Defences: D0 none; D1 shared TOTP handshake as first proposed; D2 per-agent Ed25519 keys with signed messages, nonce cache and 60 s window; D3 = D2 + rule-based reference monitor. Configuration: Table 1 (docs/CONFIG_TABLE.md). Success rules were pre-registered (PREREGISTRATION.md, tag `prereg-v1`) and read from the ledger only; an independent re-grader agreed on every trial.

## 4 Results (2.5 pages)

{c.fig("fig2_asr_heatmap", "Figure 2. Attack success rate (k/n) per defence and attack.")}

{c.table("table2b_headline_matrix")}

Verdicts: H1 {c.v('verdict.H1')}, H2 {c.v('verdict.H2')}, H3 {c.v('verdict.H3')}, H4 {c.v('verdict.H4')}, H5 {c.v('verdict.H5')}, H6 {c.v('verdict.H6')}, H7 {c.v('verdict.H7')}, H8 {c.v('verdict.H8')}, H9 {c.v('verdict.H9')} (Table 10).

Costs: {c.table("table4_costs")}

Box 1 (report/excerpts/box1_a5_success_d2.md) walks through one A5 success under D2.

[TO FILL: 2–3 paragraphs interpreting the matrix, the costs and Box 1. Separate what crypto proves (who sent a message) from what it cannot (whether the content is safe).]

## 5 Discussion (1 page)

[TO FILL. Points to cover: identity is necessary (D2 vs D1 on A3, A4-direct, A1-reflect) but not sufficient (A5, A4-lie under D2); the monitor's power comes from an independent source of truth (D0+M and -R1 ablations); the reflection flaw shows protocol details matter; costs are small (H7).]

## Appendices

A. Limitations and dual use (docs/LIMITATIONS.md, docs/DUAL_USE.md) · B. Prompts (prompts/*.txt) and A5 texts (attack_texts/) · C. Configuration (docs/CONFIG_TABLE.md) · D. Minimum identity checklist for A2A deployments (docs/A2A_MINIMUM_IDENTITY_CHECKLIST.md) · E. Pilot bugs (docs/PILOT_BUGS.md) and deviations (docs/DEVIATIONS.md)
"""


def checklist_md(c: Ctx) -> str:
    # Each item: (advice, evidence label, [(label, key_before, key_after_or_None), ...]).
    # Item 7 cites A4-lie and the family-2 A5 column: family 1 resisted every injection (0/90 under
    # D2 and D3), so its A5 numbers alone show nothing about the monitor.
    item7 = [("A4-lie, D2 → D3", "asr.core.D2.A4l.fmt", "asr.core.D3.A4l.fmt")]
    if c.has("headline.f2.A5pooled.D2"):
        item7.append(("A5 pooled, family 2, D2 → D3", "headline.f2.A5pooled.D2", "headline.f2.A5pooled.D3"))
    item7.append(("A5 pooled, family 1, D2 → D3 (the model resisted)", "headline.A5pooled.D2", "headline.A5pooled.D3"))
    items = [
        ("Give each agent its own key; never share one secret across agents.", "A4-direct: D1 vs D2",
         [("", "asr.core.D1.A4d.fmt", "asr.core.D2.A4d.fmt")]),
        ("Sign every message, covering body, recipient, task ID, nonce and timestamp.", "A3: D1 vs D2",
         [("", "asr.core.D1.A3.fmt", "asr.core.D2.A3.fmt")]),
        ("Reject replays with a nonce cache and a freshness window.", "A2-fast: D1 vs D2; E1",
         [("", "asr.core.D1.A2f.fmt", "asr.core.D2.A2f.fmt")]),
        ("Never use a handshake where both sides send the same value; bind responses to the challenge and separate the directions.",
         "A1-reflect: D1 vs D2; E4", [("", "asr.core.D1.A1r.fmt", "asr.core.D2.A1r.fmt")]),
        ("Publish an authorisation registry: which agent may send which message kinds to whom.", "A4-direct under D2 (check K6)",
         [("", "asr.core.D2.A4d.fmt", None)]),
        ("Rate-limit and lock out failed handshakes.", "E3: per-guess success probability", [("", "E3.p_attempt", None)]),
        ("Treat authenticated content as untrusted data: gate high-impact actions with an external reference monitor checked against an independent source of truth.",
         "A4-lie and A5: D2 vs D3", item7),
        ("Verify bank-detail changes out of band; a monitor cannot tell a legitimate change from an injected one.",
         "design of monitor rule R1 (E7 not run, so not measured)", []),
        ("Keep provenance from the user's task to every action, and re-verify it at the point of action.", "monitor rule R4", []),
        ("Log every decision with the rule that fired; measure false-rejection rates before deploying.", "Table 4, Table 6",
         [("", "cost.D3.frr_fmt", None)]),
        ("Set clock tolerance on purpose and measure its cost.", "E2 (Table E2, Figure E2)", []),
    ]
    lines = ["# Minimum identity checklist for A2A deployments", "",
             "One page. Each item names the experimental evidence behind it. Mappings to A2A protocol features are marked "
             f"{VERIFY} until checked against the current A2A specification.", "",
             "| # | Do this | Evidence | Numbers | A2A feature |", "| --- | --- | --- | --- | --- |"]
    for i, (text, ev, parts) in enumerate(items, 1):
        shown = []
        for label, k1, k2 in parts:
            nums = " → ".join(c.v(k) for k in (k1, k2) if k)
            shown.append(f"{label}: {nums}" if label else nums)
        lines.append(f"| {i} | {text} | {ev} | {'; '.join(shown) if shown else '-'} | {VERIFY} |")
    return "\n".join(lines) + "\n"


DUAL_USE = """# Dual-use statement

- The attacks studied are textbook: impersonation, replay, relay/tamper, reflection, stolen credentials and indirect prompt injection.
- Everything ran offline on fake data: a fictional company, fictional suppliers and fictional bank accounts. No real system, account, network, A2A deployment or person was involved. The attacker ("Mallory") is code on an in-process bus, never a model.
- The injection texts are published in generic form only (`attack_texts/`). Stronger variants produced by the escalation ladder, if any, are described but not published.
- The main finding tells attackers that insider prompt injection gets past cryptographic identity. Defenders gain more from it than attackers: the attack is already widely known, while the defensive lesson (gate high-impact actions with an external monitor that checks an independent source of truth, and verify bank-detail changes out of band) is cheap to adopt and is packaged as a checklist.
"""

LIMITATIONS = """# Limitations

- One toy workflow with three agents and synthetic data; results may not transfer to richer agent systems.
- The rule-based monitor's R1 uses a perfect source of truth (the account on file), which overstates real monitors. The D0+M and -R1 ablations quantify how much of D3's protection comes from that oracle.
- At most two model families, with default sampling (temperature cannot be set on the current Claude Haiku model; deviation V1).
- Agents are stateless between messages; real agents with memory may resist replays or injections differently.
- A simulated protocol clock; latency measured on one laptop.
- 30 trials per cell: intervals are wide, and "no significant difference" is not equivalence.
- Messages are A2A-shaped but this is not the A2A protocol itself.
- Fixed prompts and three injection texts; other phrasings may behave differently.
- [TO FILL: anything found during the runs.]
"""

REFERENCES = """# References (check every entry before use; never invent a citation)

1. Agent2Agent (A2A) Protocol specification. [VERIFY: version, URL]
2. Chan, A. et al. IDs for AI Systems. [VERIFY: year, venue/URL]
3. Lee, D. and Tiwari, M. Prompt Infection: LLM-to-LLM Prompt Injection within Multi-Agent Systems. [VERIFY: year, URL]
4. Greenblatt, R. et al. AI Control: Improving Safety Despite Intentional Subversion. [VERIFY: year, venue]
5. Debenedetti, E. et al. Defeating Prompt Injections by Design (CaMeL). [VERIFY: year, URL]
6. Greshake, K. et al. Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection. [VERIFY: year, venue]
7. OWASP Top 10 for LLM Applications (LLM01: Prompt Injection). [VERIFY: version, URL]
8. M'Raihi, D. et al. RFC 6238: TOTP: Time-Based One-Time Password Algorithm. IETF, 2011.
9. Josefsson, S. and Liusvaara, I. RFC 8032: Edwards-Curve Digital Signature Algorithm (EdDSA). IETF, 2017.
10. Rescorla, E. RFC 8446: The Transport Layer Security (TLS) Protocol Version 1.3. IETF, 2018.
11. Neuman, C. et al. RFC 4120: The Kerberos Network Authentication Service (V5). IETF, 2005.
12. Needham, R. and Schroeder, M. Using encryption for authentication in large networks of computers. Communications of the ACM, 1978.
13. Lowe, G. Breaking and fixing the Needham-Schroeder public-key protocol using FDR. TACAS, 1996. [VERIFY]
14. Hardy, N. The Confused Deputy. ACM SIGOPS Operating Systems Review, 1988.
15. Wilson, E. B. Probable inference, the law of succession, and statistical inference. JASA, 1927.
16. Newcombe, R. G. Interval estimation for the difference between independent proportions. Statistics in Medicine, 1998.
17. Holm, S. A simple sequentially rejective multiple test procedure. Scandinavian Journal of Statistics, 1979.
"""


def honest_tasks_md() -> str:
    from world import INVOICES, format_gbp, honest_task_text
    lines = ["# Honest tasks and invoice table", "", "| # | Task text | Invoice | Supplier | Amount | Account on file |",
             "| --- | --- | --- | --- | --- | --- |"]
    for i, inv in enumerate(INVOICES, 1):
        lines.append(f"| {i} | {honest_task_text(inv)} | {inv.invoice_id} | {inv.supplier} | {format_gbp(inv.amount_pence)} | {inv.account_on_file} |")
    return "\n".join(lines) + "\n"


def false_rejections_md(c: Ctx) -> str:
    rows = [r for r in c.rows if r.get("status") == "ok" and r.get("experiment") == "honest" and r.get("false_rejection") == "1"]
    lines = ["# False rejections in honest runs", ""]
    if not rows:
        return "\n".join(lines + ["None: no honest message was rejected and no honest payment was blocked."]) + "\n"
    lines += ["| run | defence | checks failed | monitor rule | reason |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| `{r['run_id']}` | {r['defence']} | {r['rejected_checks']} | {r['monitor_rule_fired'] or '-'} | [TO FILL: why] |")
    return "\n".join(lines) + "\n"


def cost_md(c: Ctx) -> str:
    return ("# Actual API cost\n\n" + c.table("table9_errors") + "\n\n"
            f"Total recorded cost: ${c.v('total_cost_usd')} over {c.v('total_llm_calls')} LLM calls.\n")


def write_docs(c: Ctx, docs: Path) -> None:
    docs.mkdir(parents=True, exist_ok=True)
    cfg_md = c.root / "tables" / "table1_config.md"
    if cfg_md.exists():
        (docs / "CONFIG_TABLE.md").write_text("# Configuration of every defence and parameter\n\n" + c.table("table1_config") + "\n",
                                              encoding="utf-8")
    (docs / "HONEST_TASKS.md").write_text(honest_tasks_md(), encoding="utf-8")
    (docs / "FALSE_REJECTIONS.md").write_text(false_rejections_md(c), encoding="utf-8")
    (docs / "COST_ACTUAL.md").write_text(cost_md(c), encoding="utf-8")
    (docs / "A2A_MINIMUM_IDENTITY_CHECKLIST.md").write_text(checklist_md(c), encoding="utf-8")
    (docs / "DUAL_USE.md").write_text(DUAL_USE, encoding="utf-8")
    lim = docs / "LIMITATIONS.md"
    if not lim.exists():
        lim.write_text(LIMITATIONS, encoding="utf-8")


def write_examples() -> None:
    import registry
    from message import AGENTS
    reg_path = ROOT / "results" / "registry_example.json"
    if not reg_path.exists():  # example public keys only; keep the committed example stable across reruns
        _, reg = registry.generate(AGENTS)
        registry.export_registry(reg, reg_path)
    cfg = load_config()
    (ROOT / "results" / "totp_setup_redacted.json").write_text(json.dumps({
        "digits": cfg.d1.totp_digits, "period_s": cfg.d1.totp_period_s, "valid_window": cfg.d1.valid_window,
        "algorithm": "HMAC-SHA1 (pyotp default)", "channel_ttl_s": cfg.d1.channel_ttl_s,
        "secret": "[REDACTED: a fresh pyotp.random_base32() per trial, held in memory only, never stored]",
        "note": "registry_example.json holds example public keys only; real keys are regenerated per trial."}, indent=2) + "\n",
        encoding="utf-8")


# ----- handoff ------------------------------------------------------------------------------------
HANDOFF_ITEMS = [
    ("(must) results/results.csv", "results/results.csv"), ("(must) logs folder, zipped", "handoff/logs.zip"),
    ("(must) code zip (and repo URL in README)", "handoff/code.zip"), ("(must) figures", "figures/fig2_asr_heatmap.png"),
    ("(must) tables", "tables/table2_asr_matrix.csv"), ("registry.json (public keys only)", "results/registry_example.json"),
    ("redacted TOTP setup", "results/totp_setup_redacted.json"), ("(must) model names, versions, settings, run dates", "results/run_manifest.json"),
    ("(must) configuration table", "docs/CONFIG_TABLE.md"), ("(must) system prompts verbatim", "prompts/orchestrator.txt"),
    ("(must) honest tasks and invoice table", "docs/HONEST_TASKS.md"), ("(must) A5 texts, all variants", "attack_texts/polite.txt"),
    ("(must) success rules written before running", "PREREGISTRATION.md"), ("trials per cell, seeds", "results/seeds.csv"),
    ("total API cost", "docs/COST_ACTUAL.md"), ("(must) pilot bugs", "docs/PILOT_BUGS.md"),
    ("(must) log excerpts: A5 under D2", "report/excerpts/box1_a5_success_d2.md"),
    ("(must) log excerpts: A3 under D1", "report/excerpts/ex2_a3_success_d1.md"),
    ("(must) log excerpts: monitor block", "report/excerpts/ex3_monitor_block_d3.md"),
    ("surprises", "report/RESULTS.md"), ("wrongly rejected honest tasks", "docs/FALSE_REJECTIONS.md"),
    ("second-family results", "tables/table8_family_compare.csv"), ("paper draft (authors/dates from C5)", "report/paper_draft.md"),
    ("references (checked)", "report/references.md"), ("dual-use appendix", "docs/DUAL_USE.md"),
    ("limitations", "docs/LIMITATIONS.md"), ("A2A minimum identity checklist", "docs/A2A_MINIMUM_IDENTITY_CHECKLIST.md"),
    ("deviations log", "docs/DEVIATIONS.md"), ("threat model", "docs/THREAT_MODEL.md"),
]


def build_handoff() -> None:
    h = ROOT / "handoff"
    h.mkdir(exist_ok=True)
    with zipfile.ZipFile(h / "logs.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in (ROOT / "logs").rglob("*.jsonl"):
            if "mock" not in p.parts:
                z.write(p, p.relative_to(ROOT))
    skip = {".venv", ".git", "logs", "handoff", "__pycache__", ".pytest_cache", ".hypothesis", "secrets"}
    with zipfile.ZipFile(h / "code.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob("*"):
            rel = p.relative_to(ROOT)
            if p.is_file() and not (set(rel.parts) & skip) and p.name != ".env" and "mock" not in rel.parts:
                z.write(p, rel)
    lines = ["# Handoff checklist (source plan, Part 2)", "", f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}.", ""]
    for label, path in HANDOFF_ITEMS:
        ok = (ROOT / path).exists()
        lines.append(f"- [{'x' if ok else ' '}] {label}: `{path}`" + ("" if ok else " (missing)"))
    lines += ["- [ ] (must) authors, affiliation, sprint dates, track: from checkpoint C5 (tick when filled in report/paper_draft.md)",
              "- [ ] motivation paragraph, extra papers, leave-outs: from checkpoint C5"]
    (h / "HANDOFF_CHECKLIST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with zipfile.ZipFile(h / "sign-countersign-handoff.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in (h / "logs.zip", h / "code.zip", h / "HANDOFF_CHECKLIST.md"):
            z.write(p, p.name)
    print(f"handoff built in {h}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--csv", default=str(ROOT / "results" / "results.csv"))
    ap.add_argument("--logs", default=str(ROOT / "logs"))
    ap.add_argument("--out", default=str(ROOT / "report"))
    ap.add_argument("--handoff", action="store_true")
    args = ap.parse_args(argv)
    c = Ctx(Path(args.root), Path(args.csv), Path(args.logs), Path(args.out))
    c.out.mkdir(parents=True, exist_ok=True)
    chosen = write_excerpts(c)
    (c.out / "RESULTS.md").write_text(results_md(c, chosen), encoding="utf-8")
    (c.out / "paper_draft.md").write_text(paper_md(c), encoding="utf-8")
    (c.out / "references.md").write_text(REFERENCES, encoding="utf-8")
    docs = (ROOT / "docs") if c.out == ROOT / "report" else (c.out / "docs")
    write_docs(c, docs)
    if c.out == ROOT / "report":
        write_examples()
    if args.handoff:
        build_handoff()
    print(f"report written to {c.out} (excerpts: {len(chosen)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
