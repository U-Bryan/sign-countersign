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
import sys
import textwrap
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config import ROOT, load_config



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
    # Each comment is chosen by the data, so the wording stays true if the numbers change.
    for d in ("D0", "D1", "D2", "D3"):
        for col, o in ORACLE_TABLE[d].items():
            k = f"asr.core.{d}.{col}.p"
            if k in V and abs(V[k] - o) > 0.30:
                s = f"{col} under {d}: LLM ASR {c.v(f'asr.core.{d}.{col}.fmt')} vs protocol-level {'through' if o else 'stopped'}. "
                if o and V[k] < o:
                    s += ("Model-level resistance: the protocol lets this attack through (oracle), but the family-1 agents "
                          "did not carry it out. The defence did not stop it.")
                    if f"asr.family2.{d}.{col}.fmt" in V:
                        s += f" Family 2 under the same defence: {c.v(f'asr.family2.{d}.{col}.fmt')}."
                else:
                    s += "The attack succeeded where the protocol should stop it; check the logs of this cell."
                out.append(s)
    if "asr.core.D1.A2f.p" in V:
        s = f"A2-fast under D1: {c.v('asr.core.D1.A2f.fmt')}. "
        s += ("A TOTP code stays valid for its whole acceptance window and nothing binds it to the request, so an unchanged "
              "replay inside the window reopens a channel (Figure E1)." if V["asr.core.D1.A2f.p"] > 0
              else "The handshake stopped a replay inside the code's validity window.")
        out.append(s)
    if "asr.core.D1.A1r.p" in V:
        s = f"A1-reflect under D1: {c.v('asr.core.D1.A1r.fmt')}. "
        if V["asr.core.D1.A1r.p"] > 0:
            s += "The receiver reveals the same code the caller must send back, so an outsider can reflect it."
            if "asr.ablation.D1fix.A1r.fmt" in V:
                s += f" Direction-separated codes (D1fix, extension E4): {c.v('asr.ablation.D1fix.A1r.fmt')}."
        else:
            s += "No reflection succeeded."
        out.append(s)
    if "asr.core.D2.A4l.p" in V:
        s = f"A4-lie under D2: {c.v('asr.core.D2.A4l.fmt')}. "
        if V["asr.core.D2.A4l.p"] > 0:
            s += "Per-agent keys limit what a stolen key can order"
            s += f" (A4-direct under D2: {c.v('asr.core.D2.A4d.fmt')})" if "asr.core.D2.A4d.fmt" in V else ""
            s += ", not what it can say: the signed lie is accepted"
            s += f"; the monitor's account-on-file rule stops it (D3: {c.v('asr.core.D3.A4l.fmt')})." if "asr.core.D3.A4l.fmt" in V else "."
        else:
            s += "The stolen-key lie did not succeed."
        out.append(s)
    for d in ("D0", "D1", "D2", "D3"):
        if V.get(f"cost.{d}.frr", 0) > 0:
            out.append(f"Non-zero FRR under {d}: {c.v(f'cost.{d}.frr_fmt')}. Each case is listed in docs/FALSE_REJECTIONS.md.")
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
              "- git commits recorded by the trials: " + (", ".join(f"`{s}`" for s in sorted({r.get("git_sha", "") for r in c.rows} - {""})) or "n/a")
              + (" (IDs from before the history rewrite; `docs/COMMIT_MAP.md` gives the current IDs)"
                 if (ROOT / "docs" / "COMMIT_MAP.md").exists() else ""),
              f"- config SHA-256: `{c.rows[0].get('config_sha') if c.rows else 'n/a'}`",
              f"- prompt SHA-256: `{c.rows[0].get('prompt_sha') if c.rows else 'n/a'}`",
              f"- generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"]
    return "\n".join(lines) + "\n"


def checklist_md(c: Ctx) -> str:
    # Each item: (advice, evidence label, [(label, key_before, key_after_or_None), ...]).
    # Item 7 cites A4-lie and the family-2 A5 column: family 1 resisted every injection (0/90 under
    # D2 and D3), so its A5 numbers alone show nothing about the monitor.
    item7 = [("A4-lie, D2 → D3", "asr.core.D2.A4l.fmt", "asr.core.D3.A4l.fmt")]
    if c.has("headline.f2.A5pooled.D2"):
        item7.append(("A5 pooled, family 2, D2 → D3", "headline.f2.A5pooled.D2", "headline.f2.A5pooled.D3"))
    item7.append(("A5 pooled, family 1, D2 → D3 (the model resisted)", "headline.A5pooled.D2", "headline.A5pooled.D3"))
    # The A2A column was checked against the A2A specification v1.0.0 (https://a2a-protocol.org/v1.0.0/specification/),
    # sections 3.3.1, 4.1.4, 4.5, 5.6.1, 7.1-7.6.4, 8.4, 13.1-13.4 and 14.1.1, read on 2026-11-07.
    items = [
        ("Give each agent its own key; never share one secret across agents.", "A4-direct: D1 vs D2",
         [("", "asr.core.D1.A4d.fmt", "asr.core.D2.A4d.fmt")],
         "Supported, not required. Each agent declares its authentication schemes in its Agent Card (§4.5); credentials "
         "are issued out of band (§7.3), MUST be kept secret and SHOULD be rotated (§13.4). Distinct credentials per "
         "agent are not required."),
        ("Sign every message, covering body, recipient, task ID, nonce and timestamp.", "A3: D1 vs D2",
         [("", "asr.core.D1.A3.fmt", "asr.core.D2.A3.fmt")],
         "Not specified. Every request is authenticated (§7.4) and production traffic MUST use TLS (§7.1), which protects "
         "each connection; only Agent Cards can be signed (§8.4), not messages."),
        ("Reject replays with a nonce cache and a freshness window.", "A2-fast: D1 vs D2; E1",
         [("", "asr.core.D1.A2f.fmt", "asr.core.D2.A2f.fmt")],
         "Partly. Agents may use `messageId` to detect duplicate messages (§3.3.1); no nonce cache or freshness window "
         "is specified."),
        ("Never use a handshake where both sides send the same value; bind responses to the challenge and separate the directions.",
         "A1-reflect: D1 vs D2; E4", [("", "asr.core.D1.A1r.fmt", "asr.core.D2.A1r.fmt")],
         "Met by the standard schemes, none of which has both sides send the same value: servers prove identity with "
         "TLS certificates (§7.2), and mutual TLS authenticates both ends (§4.5.6)."),
        ("Publish an authorisation registry: which agent may send which message kinds to whom.", "A4-direct under D2 (check K6)",
         [("", "asr.core.D2.A4d.fmt", None)],
         "Partly. Each server authorises every request under its own policy, which MAY consider the skills requested, "
         "the actions and OAuth scopes (§7.5); there is no shared registry of who may send what to whom."),
        ("Rate-limit and lock out failed handshakes.", "E3: per-guess success probability", [("", "E3.p_attempt", None)],
         "Partly. Agents SHOULD rate-limit all operations and log authentication failures to prevent brute-force "
         "attacks (§13.4); lockout is not mentioned."),
        ("Treat authenticated content as untrusted data: gate high-impact actions with an external reference monitor checked against an independent source of truth.",
         "A4-lie and A5: D2 vs D3", item7,
         "Partly. Agents MUST validate input parameters (§13.4) and sanitise user-provided content against injection "
         "attacks (§14.1.1); prompt injection, untrusted content from authenticated agents and independent checks "
         "before high-impact actions are not covered."),
        ("Verify bank-detail changes out of band; a monitor cannot tell a legitimate change from an injected one.",
         "design of monitor rule R1 (E7 not run, so not measured)", [],
         "Outside the protocol. The auth-required task state (§7.6) can pause a task while approval is obtained out of "
         "band; the state alone MUST NOT be treated as authorisation (§7.6.4)."),
        ("Keep provenance from the user's task to every action, and re-verify it at the point of action.", "monitor rule R4", [],
         "Partly. Messages carry `taskId`, `contextId` and `referenceTaskIds` (§4.1.4), and agents SHOULD keep audit "
         "trails for sensitive operations (§13.4); re-verifying provenance at the point of action is not specified."),
        ("Log every decision with the rule that fired; measure false-rejection rates before deploying.", "Table 4, Table 6",
         [("", "cost.D3.frr_fmt", None)],
         "Partly. Agents SHOULD log security-relevant events, including authentication failures and authorisation "
         "denials, and keep audit trails (§13.4); measuring false rejections is not mentioned."),
        ("Set clock tolerance on purpose and measure its cost.", "E2 (Table E2, Figure E2)", [],
         "Not applicable as specified: A2A has no message timestamp check (timestamps are data fields, §5.6.1). "
         "Applies to any freshness window added for item 3."),
    ]
    lines = ["# Minimum identity checklist for A2A deployments", "",
             "One page. Each item names the experimental evidence behind it. The A2A column was checked against the "
             "Agent2Agent (A2A) Protocol Specification, version 1.0.0 (https://a2a-protocol.org/v1.0.0/specification/, "
             "read 7 November 2026); section numbers refer to that version. In short, A2A v1.0.0 authenticates requests "
             "and encrypts connections but leaves message signing, replay protection and the treatment of authenticated "
             "content to the deployment.", "",
             "| # | Do this | Evidence | Numbers | A2A v1.0.0 |", "| --- | --- | --- | --- | --- |"]
    for i, (text, ev, parts, a2a) in enumerate(items, 1):
        shown = []
        for label, k1, k2 in parts:
            nums = " → ".join(c.v(k) for k in (k1, k2) if k)
            shown.append(f"{label}: {nums}" if label else nums)
        lines.append(f"| {i} | {text} | {ev} | {'; '.join(shown) if shown else '-'} | {a2a} |")
    return "\n".join(lines) + "\n"


DUAL_USE = """# Dual-use statement

- The attacks studied are textbook: impersonation, replay, relay/tamper, reflection, stolen credentials and indirect prompt injection.
- Everything ran offline on fake data: a fictional company, fictional suppliers and fictional bank accounts. No real system, account, network, A2A deployment or person was involved. The attacker ("Mallory") is code on an in-process bus, never a model.
- The injection texts are published in generic form only (`attack_texts/`). Stronger variants produced by the escalation ladder, if any, are described but not published.
- The main finding tells attackers that insider prompt injection gets past cryptographic identity. Defenders gain more from it than attackers: the attack is already widely known, while the defensive lesson (gate high-impact actions with an external monitor that checks an independent source of truth, and verify bank-detail changes out of band) is cheap to adopt and is packaged as a checklist.
"""

LIMITATIONS = """# Limitations

Matches Appendix A.1 of the paper.

- One toy workflow with three agents and synthetic data; results may not transfer to richer agent systems.
- The monitor's R1 uses a perfect source of truth (the account on file), which overstates real monitors. The D0+M and -R1 ablations show how much of D3's protection comes from that oracle.
- Two model families, each in one configuration, with default sampling (temperature cannot be set on the current Claude Haiku model; deviation V1). The comparison between families is exploratory and says nothing general about vendors or model safety.
- The agents are stateless between messages; real agents with memory may resist replays or injections differently.
- A simulated protocol clock; latency and microbenchmarks were measured on one laptop.
- 30 trials per cell, so intervals are wide and "no significant difference" is not equivalence. A 0/30 cell is consistent with a true rate of up to 11%, and 0/90 with up to 4%. This applies to the false-rejection rates too.
- The messages are A2A-shaped, but this is not the A2A protocol itself. The checklist's A2A column describes the A2A specification v1.0.0 as read on 7 November 2026.
- Fixed prompts and three injection texts; other phrasings may behave differently.

Found while writing the paper:

- Family 1 resisted every injection, so its A5 columns, H6 in family 1 and the A5-blunt cells of the two -R1 ablations cannot show any defence effect. E5 and E6 tested family 1 under D2 only, so they show that its resistance survived those changes, not that the changes have no effect on other models.
- E7 (legitimate bank-detail changes) and E8 (an LLM-based monitor) were not run. The monitor's false rejections on legitimate edge cases are therefore unmeasured, and checklist item 8 rests on the design of R1, not on a measurement.
- Which monitor rule blocked family 2's A5 payments under D3 is not tabulated. Denial of service (a task that fails because a defence refused a forged or tampered message) is recorded per trial but not tabulated.
- The funnel's "records relayed" stage counts any mention of the attacker's account, including in the notes, so for family 1 it overstates how far the injection got.
- Dollar costs are estimates: token counts multiplied by configured prices that were not re-checked against the providers' price lists.
- The threat model excludes poisoning the monitor's source of truth, compromise of the orchestrator's or finance agent's keys, and side channels.
- Each defence ran with one parameter setting in the LLM runs (for example a TOTP window of one step and a 60 s timestamp window). E1 and E2 vary these without an LLM.
- The reproduction pipeline was tested on Windows only.
"""

REFERENCES = """# References

The reference list of the final paper, in the paper's order and numbering. Each entry was checked against its source on 7 November 2026 (authors, title, venue, year, and pages where given). The page ranges of [5] and [14] could not be confirmed independently; their venues, authors and, for [5], the DOI match.

1. A2A Project. Agent2Agent (A2A) protocol specification, version 1.0.0. https://a2a-protocol.org/v1.0.0/specification/, 2026. Accessed 7 November 2026.
2. D. Lee and M. Tiwari. Prompt infection: LLM-to-LLM prompt injection within multi-agent systems. arXiv:2410.07283, 2024. https://arxiv.org/abs/2410.07283
3. Xiangming Gu, Xiaosen Zheng, Tianyu Pang, Chao Du, Qian Liu, Ye Wang, Jing Jiang and Min Lin. Agent Smith: A single image can jailbreak one million multimodal LLM agents exponentially fast. In Proceedings of the 41st International Conference on Machine Learning (ICML), volume 235 of PMLR, pages 16647–16672, 2024. https://proceedings.mlr.press/v235/gu24e.html
4. Zaibin Zhang, Yongting Zhang, Lijun Li, Hongzhi Gao, Lijun Wang, Huchuan Lu, Feng Zhao, Yu Qiao and Jing Shao. PsySafe: A comprehensive framework for psychological-based attack, defense, and evaluation of multi-agent system safety. In Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL), Volume 1: Long Papers, pages 15202–15231, 2024. https://aclanthology.org/2024.acl-long.812
5. Sumeet Ramesh Motwani, Mikhail Baranchuk, Martin Strohmeier, Vijay Bolina, Philip H. S. Torr, Lewis Hammond and Christian Schroeder de Witt. Secret collusion among AI agents: Multi-agent deception via steganography. In Advances in Neural Information Processing Systems 37 (NeurIPS), pages 73439–73486, 2024. https://doi.org/10.52202/079017-2336
6. Alan Chan et al. IDs for AI systems. arXiv:2406.12137, 2024. https://arxiv.org/abs/2406.12137. Version 3; RegML workshop at NeurIPS 2024.
7. Alan Chan, Carson Ezell, Max Kaufmann, Kevin Wei, Lewis Hammond, Herbie Bradley, Emma Bluemke, Nitarshan Rajkumar, David Krueger, Noam Kolt, Lennart Heim and Markus Anderljung. Visibility into AI agents. In Proceedings of the 2024 ACM Conference on Fairness, Accountability, and Transparency (FAccT), pages 958–973. ACM, 2024. https://doi.org/10.1145/3630106.3658948
8. Alan Chan, Kevin Wei, Sihao Huang, Nitarshan Rajkumar, Elija Perrier, Seth Lazar, Gillian K. Hadfield and Markus Anderljung. Infrastructure for AI agents. Transactions on Machine Learning Research, 2025. https://openreview.net/forum?id=Ckh17xN2R2
9. Tobin South, Samuele Marro, Thomas Hardjono, Robert Mahari, Cedric Deslandes Whitney, Alan Chan and Alex Pentland. Position: AI agents need authenticated delegation. In Proceedings of the 42nd International Conference on Machine Learning (ICML), volume 267 of PMLR, pages 82211–82231, 2025. https://proceedings.mlr.press/v267/south25a.html
10. Leslie Lamport, Robert Shostak and Marshall Pease. The Byzantine generals problem. ACM Transactions on Programming Languages and Systems, 4(3):382–401, 1982.
11. Pengfei He, Yuping Lin, Shen Dong, Han Xu, Yue Xing and Hui Liu. Red-teaming LLM multi-agent systems via communication attacks. In Findings of the Association for Computational Linguistics: ACL 2025, pages 6726–6747, 2025. https://aclanthology.org/2025.findings-acl.349
12. Kai Greshake et al. Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection. In Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security (AISec), pages 79–90, 2023. https://arxiv.org/abs/2302.12173
13. Qiusi Zhan, Zhixiang Liang, Zifan Ying and Daniel Kang. InjecAgent: Benchmarking indirect prompt injections in tool-integrated large language model agents. In Findings of the Association for Computational Linguistics: ACL 2024, pages 10471–10506, 2024. https://aclanthology.org/2024.findings-acl.624
14. Edoardo Debenedetti, Jie Zhang, Mislav Balunović, Luca Beurer-Kellner, Marc Fischer and Florian Tramèr. AgentDojo: A dynamic environment to evaluate prompt injection attacks and defenses for LLM agents. In Advances in Neural Information Processing Systems 37 (NeurIPS), Datasets and Benchmarks Track, pages 82895–82920, 2024. https://doi.org/10.52202/079017-2636
15. Egor Zverev, Sahar Abdelnabi, Soroush Tabesh, Mario Fritz and Christoph Lampert. Can LLMs separate instructions from data? And what do we even mean by that? In International Conference on Learning Representations (ICLR), 2025. https://arxiv.org/abs/2403.06833
16. Ryan Greenblatt, Buck Shlegeris, Kshitij Sachan and Fabien Roger. AI control: Improving safety despite intentional subversion. In Proceedings of the 41st International Conference on Machine Learning (ICML), volume 235 of PMLR, pages 16295–16336, 2024. https://arxiv.org/abs/2312.06942
17. Edoardo Debenedetti et al. Defeating prompt injections by design. arXiv:2503.18813, 2025. https://arxiv.org/abs/2503.18813
18. Zhen Xiang, Linzhi Zheng, Yanjie Li, Junyuan Hong, Qinbin Li, Han Xie, Jiawei Zhang, Zidi Xiong, Chulin Xie, Carl Yang, Dawn Song and Bo Li. GuardAgent: Safeguard LLM agents via knowledge-enabled reasoning. In Proceedings of the 42nd International Conference on Machine Learning (ICML), volume 267 of PMLR, pages 68316–68342, 2025. https://proceedings.mlr.press/v267/xiang25a.html
19. Jen-Tse Huang, Jiaxu Zhou, Tailin Jin, Xuhui Zhou, Zixi Chen, Wenxuan Wang, Youliang Yuan, Michael Lyu and Maarten Sap. On the resilience of LLM-based multi-agent collaboration with faulty agents. In Proceedings of the 42nd International Conference on Machine Learning (ICML), volume 267 of PMLR, pages 26202–26226, 2025. https://proceedings.mlr.press/v267/huang25ay.html
20. Yupei Liu, Yuqi Jia, Runpeng Geng, Jinyuan Jia and Neil Zhenqiang Gong. Formalizing and benchmarking prompt injection attacks and defenses. In 33rd USENIX Security Symposium (USENIX Security 24), pages 1831–1847. USENIX Association, 2024. https://www.usenix.org/conference/usenixsecurity24/presentation/liu-yupei
21. OWASP Foundation. OWASP Top 10 for LLM Applications 2025: LLM01:2025 Prompt Injection. Version 2025, published 18 November 2024. https://genai.owasp.org/, 2024.
22. Sizhe Chen, Julien Piet, Chawin Sitawarin and David Wagner. StruQ: Defending against prompt injection with structured queries. In 34th USENIX Security Symposium (USENIX Security 25), pages 2383–2400. USENIX Association, 2025. https://www.usenix.org/conference/usenixsecurity25/presentation/chen-sizhe
23. Yuhao Wu, Franziska Roesner, Tadayoshi Kohno, Ning Zhang and Umar Iqbal. IsolateGPT: An execution isolation architecture for LLM-based agentic systems. In Network and Distributed System Security Symposium (NDSS), 2025. https://www.ndss-symposium.org/ndss-paper/isolategpt-an-execution-isolation-architecture-for-llm-based-agentic-systems/
24. David M'Raihi et al. TOTP: Time-based one-time password algorithm. IETF RFC 6238, 2011. https://www.rfc-editor.org/rfc/rfc6238
25. Simon Josefsson and Ilari Liusvaara. Edwards-Curve digital signature algorithm (EdDSA). IETF RFC 8032, 2017. https://www.rfc-editor.org/rfc/rfc8032
26. Eric Rescorla. The transport layer security (TLS) protocol version 1.3. IETF RFC 8446, 2018. https://www.rfc-editor.org/rfc/rfc8446
27. Clifford Neuman et al. The Kerberos network authentication service (V5). IETF RFC 4120, 2005. https://www.rfc-editor.org/rfc/rfc4120
28. Gavin Lowe. Breaking and fixing the Needham-Schroeder public-key protocol using FDR. In Tools and Algorithms for the Construction and Analysis of Systems (TACAS), volume 1055 of Lecture Notes in Computer Science, pages 147–166. Springer, 1996.
29. Roger M. Needham and Michael D. Schroeder. Using encryption for authentication in large networks of computers. Communications of the ACM, 21(12):993–999, 1978.
30. Norm Hardy. The confused deputy. ACM SIGOPS Operating Systems Review, 1988.
31. Edwin B. Wilson. Probable inference, the law of succession, and statistical inference. Journal of the American Statistical Association, 1927.
32. Sture Holm. A simple sequentially rejective multiple test procedure. Scandinavian Journal of Statistics, 1979.
33. Robert G. Newcombe. Interval estimation for the difference between independent proportions. Statistics in Medicine, 1998.
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
    ("second-family results", "tables/table8_family_compare.csv"),
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
    # code.zip holds exactly the committed files (git archive), so local-only notes never leak into it.
    from gitutil import git
    ok, out = git("archive", "--format=zip", "-o", str(h / "code.zip"), "HEAD")
    if not ok:
        raise SystemExit(f"git archive failed: {out}")
    lines = ["# Handoff checklist (source plan, Part 2)", "", f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}.", ""]
    for label, path in HANDOFF_ITEMS:
        ok = (ROOT / path).exists()
        lines.append(f"- [{'x' if ok else ' '}] {label}: `{path}`" + ("" if ok else " (missing)"))
    lines += ["- [ ] (must) authors, affiliation, sprint dates, track: in the final paper",
              "- [ ] motivation paragraph, extra papers, leave-outs: in the final paper"]
    (h / "HANDOFF_CHECKLIST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with zipfile.ZipFile(h / "sign-countersign-handoff.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in (h / "logs.zip", h / "code.zip", h / "HANDOFF_CHECKLIST.md"):
            z.write(p, p.name)
    print(f"handoff built in {h}")


README_START = "<!-- results:start"
README_END = "<!-- results:end -->"


def readme_results(c: Ctx) -> str:
    """The README's "Results at a glance" block: every number comes from values.json or a generated table."""
    lines = [f"**Headline.** {headline(c)}", "",
             f"Attack success per defence and attack, family 1 ({c.v('model.family1')}), 30 trials per cell "
             "(successes/trials; A5 pools its three variants):", "", c.table("table2b_headline_matrix"), ""]
    f2 = [(d, f"headline.f2.A5pooled.{d}") for d in ("D0", "D1", "D2", "D3") if c.has(f"headline.f2.A5pooled.{d}")]
    if f2:
        lines += [f"Prompt injection (A5) with family 2 ({c.v('model.family2')}), three variants pooled: "
                  + ", ".join(f"{d} {c.v(k)}" for d, k in f2) + ".", ""]
    if (c.root / "figures" / "fig2_asr_heatmap.png").exists():
        lines += ["![Attack success rate by defence and attack, family 1](figures/fig2_asr_heatmap.png)", ""]
    return "\n".join(lines)


def update_readme(c: Ctx) -> None:
    p = ROOT / "README.md"
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    i, j = text.find(README_START), text.find(README_END)
    if i < 0 or j < i:
        return
    i = text.index("\n", i) + 1  # keep the start-marker line itself
    p.write_text(text[:i] + "\n" + readme_results(c).strip() + "\n\n" + text[j:], encoding="utf-8")


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
    (c.out / "references.md").write_text(REFERENCES, encoding="utf-8")
    docs = (ROOT / "docs") if c.out == ROOT / "report" else (c.out / "docs")
    write_docs(c, docs)
    if c.out == ROOT / "report":
        write_examples()
        update_readme(c)
    if args.handoff:
        build_handoff()
    print(f"report written to {c.out} (excerpts: {len(chosen)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
