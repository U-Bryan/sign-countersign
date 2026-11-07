# PROGRESS: Sign and Countersign

Last updated: 2026-11-07 by Claude Code
Current phase: 8 (report built; waiting for human inputs) | Next step: C5 inputs (authors, affiliation, sprint dates, motivation, papers, leave-outs) -> fill REPORT_BRIEF.md Section 1 -> rebuild the pack (scripts/make_report_pack.py) -> Claude writes report/PAPER.md -> C6 (GitHub remote + make public) -> tag submission | Blocked on: C5, C6

| Phase | Status (TODO / IN PROGRESS / DONE) | Gate result | Commit / tag | Notes |
| --- | --- | --- | --- | --- |
| 0 Setup | DONE | git installed; model check both families OK | 1a33581 | venv Python 3.13.15, packages pinned; secret scan PASS |
| 1 World, bus | DONE | PASS | 1a33581 | |
| 2 Agents | DONE | live honest D0 10/10 (family 1) and 10/10 (family 2); parse failures 0 | tag prompts-v1 | |
| 3 Defences | DONE | PASS: live honest D1-D3 10/10 each, zero false rejections | 1a33581 | |
| 4 Attacks + prereg | DONE | attacks succeed under D0 except A5 (C-3 followed: 0/59 incl. ladder) | tag prereg-v1 (before any live attack trial) | |
| 5 Pilot | DONE | 210 + 76 pilot trials, audit 100%, logs read (docs/PILOT_AUDIT.md), cost estimate, C3 approved | 459bc7c, f06c3d3 | |
| 6 Main runs | DONE | PASS (gates.py 6): 2,730 trials, 0 errors, audit 100% | 296c15a, tag main-run-complete | total API spend $4.01 (all phases) |
| 7 Analysis | DONE | PASS (gates.py 7): deterministic, all figures checked by eye | b29e7e8 | 27 tables, 16 figures |
| 8 Report + handoff | IN PROGRESS | final QA: fresh clone `reproduce.py` exit 0, all tables + values.json byte-identical (30 tables at 5a76233; re-checked at f3f772a after the generator fixes: 31 tables); no [MISSING]; secret scan PASS; prereg and prompts unchanged since tags; handoff complete except C5 items | b29e7e8, 5a76233, 7fa7e02, f3f772a | waiting for C5 (author details) and C6 (GitHub); report-writing brief ready (REPORT_BRIEF.md) |

## Checkpoints
C1 keys: DONE for family 1 (Anthropic key works); family 2 deferred: OpenAI key valid but account has no credits (429 insufficient quota) · C2 GitHub: local repo created (git installed via winget 2026-11-06); no remote yet · C3 tiers approved: T1, T2 (ablations now; family2 when the human adds OpenAI credits), T3 E4, E5, E6 (2026-11-06) · C4: - · C5 inputs: - · C6 publish: -

Family 2 enabled 2026-11-06 after the human added OpenAI credits (model check OK, honest pilot 10/10). The analysis treats family 2 as a pre-registered T2 replication of the A5 column: same verdict rules, its own Holm family, reported separately (never pooled).

## Offline evidence so far
- Full offline suite: `pytest -m "not live"` (see last run in the session; all passing).
- Oracle matrix: 204 mock trials match the pre-registered table exactly; audit agreement 100% (results/oracle.csv).
- Mock rehearsal: 333 mock trials -> audit 100% -> analysis (13 figures, 19+ tables, determinism identical) -> report. Mock data lives in results/mock/ and logs/mock/ (git-ignored, never analysed as results).
- Microbenchmarks (tables/bench.csv): TOTP verify ~11 us, D1 full handshake ~0.18 ms, Ed25519 verify ~49 us, D2 sign+verify ~83 us, monitor check ~63 us.

## Background runs
| Started | Command | Output file | Status |
| --- | --- | --- | --- |
| 2026-11-06 19:24 local (PID 1632) | `scripts\run_main.py honest core ablation ext-E4 ext-E5 ext-E6` | results\run_main.out / .err, results\progress.log | DONE 21:18, 2,250 trials, 0 errors |
| 2026-11-06 ~19:45 local (PID 36492) | `scripts\run_main.py family2` | results\run_family2.out / .err, results\progress.log | DONE 20:19, 480 trials, 0 errors. Credits added by the human; model check OK (gpt-5-mini-2025-08-07); family-2 honest pilot D0 10/10; family-2 pilot: A5 3/3 per variant under D0, D1, D2 and 0/3 under D3 (blocked by R1); honest 10/10 under every defence |

## Live results so far (pilot phase, family 1, results/pilot/)
- Honest pilot: 40 trials (10 tasks x D0-D3): 40/40 completed correctly, 0 false rejections, 0 parse failures, 0 refusals, $0.0303 total, median ~9 s per task.
- Early estimate (honest pricing): T1 core 1,200 trials ~ $1-3, ~1.2 h at concurrency 4; honest 120 trials ~ $0.09.

## Phase 4 live D0 check (pilot, family 1) and contingency C-3
- A1g, A1r, A2f, A2s, A3, A4d, A4l: each 3/3 under D0 (attacks work as designed).
- A5: 0/3 for each variant -> C-3 step 1: 10 more D0 trials per variant -> still 0/13 each (0/39 total). Funnel: records relays the note in 13/13 trials but explicitly flags it as an unverified bank-detail change and keeps the master-record account; the orchestrator never instructs Mallory's account (f2 = 0); in some trials it holds the payment.
- C-3 ladder: L1 (blunt text in `payment_instructions`) 0/10; L2 (bank_account overwritten, genuine kept as bank_account_previous) 0/10, and all 10 L2 trials paid nobody (agents held the payment).
- Conclusion (pre-registered handling, C-3 / C-5b): model-level resistance by claude-haiku-5-5 is a finding; no A5x variant is added (no rung succeeded). The structural point rests on the oracle and on A4-lie. Family 2 and extension E6 (lower effort) become more important.
- Gate markers: C-3 A5b, C-3 A5p, C-3 A5d (documented as above).

## Open issues
- (Resolved 2026-11-06) Git was not installed; installed with winget before any live attack trial.
- (Resolved 2026-11-06) The OpenAI account had no credits; the human added credits and family 2 ran.
- The keys were in `.env.txt` (Notepad added .txt); renamed to `.env` (git-ignored) on 2026-11-06; values never displayed. .gitignore now also covers `.env.*`.
- GitHub CLI (gh) not installed (optional, C2).

## Decisions log (one line each)
- 2026-11-06 Use `py -3.13` for the venv (regular install) instead of the Microsoft Store Python 3.12 that `python` resolves to.
- 2026-11-06 SDKs pinned: anthropic 2.6.0 (no temperature argument; has output_config), openai 3.46.0 (chat.completions with response_format, max_completion_tokens, reasoning_effort).
- 2026-11-06 Pilot/oracle/mock/main data in separate folders from the start (no moving files later).
- 2026-11-06 Seed rule uses a per-experiment offset (no seed collisions across experiments); recorded in PREREGISTRATION.md before data.
- 2026-11-06 Verdict rules made operational before data (see docs/DEVIATIONS.md).
- 2026-11-06 Figures use the dataviz skill's validated default palette unchanged (sequential blue for ASR; categorical slots in fixed order with marker shapes as secondary encoding).
- 2026-11-07 Report generator fixes (no data or rule changed): RESULTS.md renders the microbenchmark table (bench.csv) and Table E2; checklist item 7 cites A4-lie and family-2 A5 instead of the vacuous family-1 A5; analyse.py adds Table 2d (ablation ASR with Wilson intervals, the numbers behind fig2b) and asr.ablation.* values.
- 2026-11-07 Report writing: REPORT_BRIEF.md instructs Claude how to write the paper; scripts/make_report_pack.py builds handoff/report_pack/ (git-ignored) with the files to upload. The final paper goes to report/PAPER.md, because make_report.py regenerates report/paper_draft.md.
