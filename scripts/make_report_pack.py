r"""Build handoff/report_pack/: the files to give Claude so it can write the final paper.

The pack is nine numbered files plus a figures/ folder, so a chat upload stays well within
file-count limits. REPORT_BRIEF.md explains what each file is for. Run make_report.py first
so that report/ and docs/ are current.

Usage:
  .\.venv\Scripts\python.exe scripts\make_report_pack.py
  .\.venv\Scripts\python.exe scripts\make_report_pack.py --source-plan path\to\plan.md

The original sprint plan is read from --source-plan, or else from handoff/SOURCE_PLAN.md.
That copy is git-ignored, so it stays local unless the author decides to publish it.
The pack and its zip (handoff/report_pack.zip) are git-ignored too.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
import textwrap
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from gitutil import git  # noqa: E402
from secret_scan import PATTERNS, env_values  # noqa: E402

PACK = ROOT / "handoff" / "report_pack"
ZIP = ROOT / "handoff" / "report_pack.zip"
DEFAULT_PLAN = ROOT / "handoff" / "SOURCE_PLAN.md"

# Every figure, in reading order, with the caption used in the figures PDF.
FIGURES = [
    ("fig1_architecture", "Figure 1. The procurement workflow, the bus, the monitor and Mallory's entry points."),
    ("fig2_asr_heatmap", "Figure 2. Attack success rate per defence and attack (k/n), family 1 (claude-haiku-5-5), n = 30 per cell."),
    ("fig2b_ablation_heatmap", "Figure 2b. Ablations, family 1: monitor without crypto (D0+M), monitor without R1 (D3-R1, D0+M-R1), "
                               "and the fixed handshake (D1fix, extension E4). A dot marks a cell that was not run."),
    ("fig2c_family2_a5_heatmap", "Figure 2c. Prompt injection (A5) by variant and defence, family 2 (gpt-5-mini-2025-08-07), n = 30 per cell."),
    ("fig3_a5_walkthrough", "Figure 3. Box 1 rendered as an image (A5 success under D2, family 2). Use Box 1 as text instead of this image."),
    ("fig4_asr_forest", "Figure 4. ASR with 95% Wilson intervals, by attack and defence, family 1."),
    ("fig5_cost_tradeoff", "Figure 5. Protection against cost, family 1: mean ASR over the 10 attack columns (A5 counts as 0 because "
                           "family 1 resisted every injection), false-rejection rate with 95% Wilson interval, added processing per "
                           "message, and LLM tokens per honest task."),
    ("fig6_a5_variants", "Figure 6. A5 success by variant and defence, per model family (n = 30 per bar; families not pooled)."),
    ("fig7_attribution", "Figure 7. Failing transport checks under D1 and D2, and the monitor rule that blocked under D3 (family 1)."),
    ("fig7b_attribution_monitor_only", "Figure 7b. Monitor alone (D0+M): which rule blocked each attack (family 1)."),
    ("fig8_a5_funnel", "Figure 8. How far the injected text travelled through the agent chain, family 1."),
    ("fig8b_a5_funnel_family2", "Figure 8b. How far the injected text travelled through the agent chain, family 2."),
    ("fig9_oracle_vs_llm", "Figure 9. What each protocol lets through (top: deterministic oracle agent) vs what the LLM agents did "
                           "(bottom: family 1)."),
    ("figE1_replay_delay", "Figure E1. Probability that a replayed countercode is accepted, against replay delay (no LLM)."),
    ("figE2_skew_frr", "Figure E2. False-rejection rate against clock skew, for D1 TOTP windows and D2 timestamp windows "
                       "(simulation, no LLM)."),
    ("figE3_bruteforce", "Figure E3. Brute force against the 6-digit handshake, with and without lockout (no LLM)."),
]

EXCERPTS = ["box1_a5_success_d2", "ex2_a3_success_d1", "ex3_monitor_block_d3", "ex4_a1_reflect_d1", "ex5_a4_lie_d2"]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def section(text: str, start: str, end: str) -> str:
    """The part of text from the line `start` up to (not including) the line `end`."""
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j].rstrip().rstrip("-").rstrip() + "\n"


def block(title: str, body: str) -> str:
    return f"\n\n---\n\n# FILE: {title}\n\n{body.strip()}\n"


def fenced(rel: str, lang: str = "") -> str:
    return block(rel, f"```{lang}\n{read(rel).rstrip()}\n```")


def fig_paths(text: str) -> str:
    """Image links in report/*.md point to ../figures/; in the pack the folder sits beside the file."""
    return text.replace("](../figures/", "](figures/")


def drop_table(text: str, name: str, note: str) -> str:
    return re.sub(rf"<!--table:{re.escape(name)}-->.*?<!--/table-->", note, text, flags=re.S)


def provenance() -> str:
    ok, sha = git("rev-parse", "--short", "HEAD")
    ok2, status = git("status", "--porcelain")
    dirty = " (with uncommitted changes)" if ok2 and status.strip() else ""
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Built from the repository at commit `{sha.strip() if ok else 'unknown'}`{dirty} on {when}."


def header(title: str, purpose: str, sources: list[str]) -> str:
    src = "\n".join(f"- `{s}`" for s in sources)
    return (f"# {title}\n\nPart of the report-writing pack for *Sign and Countersign*. {provenance()}\n\n"
            f"{purpose}\n\nThis file combines, in order:\n\n{src}\n")


def audit_summary() -> str:
    labels = [("audit_agreement.csv", "main runs (the data analysed)"),
              ("audit_agreement_oracle.csv", "oracle matrix (deterministic mock agent)"),
              ("audit_agreement_pilot.csv", "pilot (archived, never analysed)"),
              ("audit_agreement_mock.csv", "mock rehearsal of the pipeline")]
    lines = ["Independent re-grading (`audit.py`, which shares no code with `grading.py`) re-derived every trial's "
             "outcome from its JSONL log and compared it with the results CSV. Summary computed from `tables/`:", "",
             "| File | Trials re-graded | Trials | Agreed | Agreement |", "| --- | --- | --- | --- | --- |"]
    for name, label in labels:
        p = ROOT / "tables" / name
        if not p.exists():
            continue
        with open(p, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows or "agree" not in rows[0]:
            continue
        agree = sum(int(r["agree"]) for r in rows)
        lines.append(f"| `tables/{name}` | {label} | {len(rows):,} | {agree:,} | {100 * agree / len(rows):.2f}% |")
    return "\n".join(lines)


def build_texts(plan: Path | None) -> dict[str, str]:
    runbook = read("RUNBOOK.md")
    readme = read("README.md")
    out: dict[str, str] = {}

    out["00_REPORT_BRIEF.md"] = read("REPORT_BRIEF.md")

    out["01_RESULTS.md"] = (
        "<!-- Pack copy of report/RESULTS.md (generated by make_report.py). " + provenance() + " -->\n\n"
        + fig_paths(read("report/RESULTS.md")))

    out["02_values.json"] = read("tables/values.json")

    s03 = ["PREREGISTRATION.md", "docs/THREAT_MODEL.md", "docs/CONFIG_TABLE.md",
           "RUNBOOK.md sections 3.2-3.6 (defences, attacks, measurements, tiers, deliberate differences)",
           "RUNBOOK.md section 5.1 (message flow of one honest task)",
           "RUNBOOK.md sections 6.7-6.9 (defence, attack and success-rule specifications)",
           "docs/HONEST_TASKS.md", "prompts/orchestrator.txt", "prompts/records.txt", "prompts/finance.txt",
           "attack_texts/blunt.txt", "attack_texts/polite.txt", "attack_texts/disguised.json", "docs/MODEL_CHECK.md",
           "config/experiment.toml", "results/run_manifest.json", "results/registry_example.json",
           "results/totp_setup_redacted.json"]
    t = header("Design and methods", "Use it for the threat model and setup (Section 3 of the paper) and for "
               "Appendices B and C. Prompts and injection texts are verbatim.", s03)
    for rel in s03[:3]:
        t += block(rel, read(rel))
    t += block(s03[3], section(runbook, "### 3.2 Defences (rows)", "## 4. Threat model"))
    t += block(s03[4], section(runbook, "### 5.1 Message flow of one honest task", "### 5.2 Repository layout"))
    t += block(s03[5], section(runbook, "### 6.7 Defences (`defences/`)", "### 6.10 One trial, end to end (`trial.py`)"))
    t += block("docs/HONEST_TASKS.md", read("docs/HONEST_TASKS.md"))
    for rel in s03[7:10]:
        t += fenced(rel, "text")
    t += fenced("attack_texts/blunt.txt", "text") + fenced("attack_texts/polite.txt", "text")
    t += fenced("attack_texts/disguised.json", "json")
    t += block("docs/MODEL_CHECK.md", read("docs/MODEL_CHECK.md"))
    t += fenced("config/experiment.toml", "toml")
    for rel in s03[15:]:
        t += fenced(rel, "json")
    out["03_DESIGN_AND_METHODS.md"] = t

    s04 = ["audit summary (computed from tables/audit_agreement*.csv) and tables/determinism.json",
           "docs/PILOT_BUGS.md", "docs/PILOT_AUDIT.md", "docs/DEVIATIONS.md", "docs/FALSE_REJECTIONS.md",
           "docs/COST_ACTUAL.md", "README.md section \"Reproduce\"", "PROGRESS.md"]
    t = header("Validation and provenance", "Use it for validation, deviations, cost and reproducibility "
               "(Sections 3 and 4 of the paper; Appendices F and G).", s04)
    t += block(s04[0], audit_summary() + "\n\nDeterminism check (two analysis runs compared):\n\n```json\n"
               + read("tables/determinism.json").strip() + "\n```")
    for rel in s04[1:5]:
        t += block(rel, read(rel))
    t += block("docs/COST_ACTUAL.md", drop_table(read("docs/COST_ACTUAL.md"), "table9_errors",
                                                 "(The per-cell table is Table 9 in 01_RESULTS.md.)"))
    t += block(s04[6], section(readme, "## Reproduce", "## Repository map"))
    t += block("PROGRESS.md", read("PROGRESS.md"))
    out["04_VALIDATION_AND_PROVENANCE.md"] = t

    s05 = [f"report/excerpts/{e}.md" for e in EXCERPTS]
    t = header("Log excerpts", "Message-by-message traces from real trials, chosen deterministically (the first "
               "matching trial by run ID). Box 1 is the first one.", s05)
    for rel in s05:
        t += block(rel, read(rel))
    out["05_LOG_EXCERPTS.md"] = t

    s06 = ["report/paper_draft.md", "report/references.md", "docs/LIMITATIONS.md", "docs/DUAL_USE.md",
           "docs/A2A_MINIMUM_IDENTITY_CHECKLIST.md", "README.md"]
    t = header("Draft and appendix sources", "The generated paper skeleton, the reference list, and the sources "
               "for Appendices A and D. The skeleton is a starting point, not the paper.", s06)
    for rel in s06:
        t += block(rel, fig_paths(read(rel)))
    out["06_DRAFT_AND_APPENDIX_SOURCES.md"] = t

    if plan is not None:
        out["08_SOURCE_PLAN.md"] = (
            "<!-- The original sprint plan, provided by the author. Not part of the public repository. -->\n\n"
            + plan.read_text(encoding="utf-8"))
    return out


def build_figures_pdf(out: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.backends.backend_pdf import PdfPages
    from PIL import Image

    known = {stem for stem, _ in FIGURES}
    extra = sorted(p.stem for p in (ROOT / "figures").glob("*.png") if p.stem not in known)
    items = FIGURES + [(stem, f"{stem} (no caption in the pack script)") for stem in extra]
    missing = []
    with PdfPages(out) as pdf:
        for stem, caption in items:
            p = ROOT / "figures" / f"{stem}.png"
            if not p.exists():
                missing.append(stem)
                continue
            img = Image.open(p).convert("RGB")
            img.thumbnail((2400, 2400))
            w, h = img.size
            portrait = h > 1.1 * w
            fig = plt.figure(figsize=(8.27, 11.69) if portrait else (11.69, 8.27))
            fig.text(0.04, 0.975, f"figures/{stem}.png", fontsize=11, weight="bold", va="top")
            fig.text(0.04, 0.95, "\n".join(textwrap.wrap(caption, 95 if portrait else 140)), fontsize=9, va="top")
            ax = fig.add_axes((0.04, 0.03, 0.92, 0.84))
            ax.imshow(np.asarray(img))
            ax.axis("off")
            pdf.savefig(fig)
            plt.close(fig)
        info = pdf.infodict()
        info["Title"] = "Sign and Countersign: all figures"
    return missing


def scan_for_secrets(paths: list[Path]) -> list[str]:
    secrets = env_values()
    findings = []
    for p in paths:
        if p.suffix.lower() not in {".md", ".json", ".txt", ".toml"}:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for name, rx in PATTERNS.items():
            if rx.search(text):
                findings.append(f"{p.name}: {name}")
        if any(v in text for v in secrets):
            findings.append(f"{p.name}: value from .env")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-plan", type=Path, default=None, help="the original sprint plan (Markdown)")
    args = ap.parse_args()
    plan = args.source_plan or (DEFAULT_PLAN if DEFAULT_PLAN.exists() else None)
    if plan is not None and not plan.exists():
        print(f"source plan not found: {plan}")
        return 1

    if PACK.exists():
        shutil.rmtree(PACK)
    (PACK / "figures").mkdir(parents=True)

    texts = build_texts(plan)
    for name, text in texts.items():
        (PACK / name).write_text(text, encoding="utf-8")
    missing = build_figures_pdf(PACK / "07_FIGURES.pdf")
    for p in sorted((ROOT / "figures").glob("*.png")):
        shutil.copy2(p, PACK / "figures" / p.name)

    files = sorted(p for p in PACK.rglob("*") if p.is_file())
    findings = scan_for_secrets(files)
    if findings:
        print("SECRET-LIKE CONTENT in the pack; nothing zipped:")
        print("\n".join(f"  {f}" for f in findings))
        return 1

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, Path("report_pack") / p.relative_to(PACK))

    print(f"report pack: {PACK}")
    for p in sorted(PACK.glob("*")):
        if p.is_file():
            print(f"  {p.name:40s} {p.stat().st_size / 1024:8.0f} KB")
    print(f"  figures/ ({len(list((PACK / 'figures').glob('*.png')))} PNG files)")
    print(f"zip: {ZIP} ({ZIP.stat().st_size / 1024 / 1024:.1f} MB)")
    if plan is None:
        print("note: no source plan found, so 08_SOURCE_PLAN.md was not written (use --source-plan).")
    if missing:
        print(f"note: figures not found: {', '.join(missing)}")
    print("secret check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
