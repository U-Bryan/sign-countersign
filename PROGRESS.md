# PROGRESS: Sign and Countersign

Last updated: 2026-11-06 by Claude Code
Current phase: 4 (live part blocked) | Next step: install git -> git init + first commit -> tag prompts-v1 and prereg-v1 -> Phase 4 live D0 attack check -> Phase 5 pilot | Blocked on: Git not installed (prereg-v1 must be tagged before any live attack trial)

| Phase | Status (TODO / IN PROGRESS / DONE) | Gate result | Commit / tag | Notes |
| --- | --- | --- | --- | --- |
| 0 Setup | IN PROGRESS | FAIL only on git (not installed) | - | venv Python 3.13.15, packages pinned, skeleton, config, secret scan PASS; model check family1 OK (claude-haiku-5-5); family 2 deferred |
| 1 World, bus | DONE | PASS (gates.py 1) | - (no git yet) | 198 unit tests at the time of the gate |
| 2 Agents | IN PROGRESS | live honest D0 10/10 PASS; parse failures 0/240 calls; FAIL only on tag prompts-v1 (git) | - | prompts unchanged since written (prompts/*.txt); tag as soon as git exists |
| 3 Defences | DONE | PASS (gates.py 3): live honest D1 10/10, D2 10/10, D3 10/10, zero false rejections | - | D1, D1fix, D2, D3, D0+M, -R1 built; bench.csv written |
| 4 Attacks + prereg | IN PROGRESS | offline parts PASS | - | attacks + capabilities + oracle matrix all PASS; PREREGISTRATION.md written, must be committed + tagged prereg-v1 BEFORE any live attack trial |
| 5 Pilot | TODO | | | runner, audit, cost estimator ready |
| 6 Main runs | TODO | | | |
| 7 Analysis | READY (rehearsed on mock data) | | | analyse.py + figs.py + determinism check work end to end on mock data |
| 8 Report + handoff | READY (rehearsed on mock data) | | | make_report.py, reproduce.py, README.md written |

## Checkpoints
C1 keys: DONE for family 1 (Anthropic key works); family 2 deferred: OpenAI key valid but account has no credits (429 insufficient quota) · C2 GitHub: waiting (git and gh not installed) · C3 tiers approved: - · C4: - · C5 inputs: - · C6 publish: -

Family 2 deferred (OpenAI account has no credits; gpt-5-mini is listed and will be used once credits are added).

## Offline evidence so far
- Full offline suite: `pytest -m "not live"` (see last run in the session; all passing).
- Oracle matrix: 204 mock trials match the pre-registered table exactly; audit agreement 100% (results/oracle.csv).
- Mock rehearsal: 333 mock trials -> audit 100% -> analysis (13 figures, 19+ tables, determinism identical) -> report. Mock data lives in results/mock/ and logs/mock/ (git-ignored, never analysed as results).
- Microbenchmarks (tables/bench.csv): TOTP verify ~11 us, D1 full handshake ~0.18 ms, Ed25519 verify ~49 us, D2 sign+verify ~83 us, monitor check ~63 us.

## Background runs
| Started | Command | Output file | Status |
| --- | --- | --- | --- |

## Live results so far (pilot phase, family 1, results/pilot/)
- Honest pilot: 40 trials (10 tasks x D0-D3): 40/40 completed correctly, 0 false rejections, 0 parse failures, 0 refusals, $0.0303 total, median ~9 s per task.
- Early estimate (honest pricing): T1 core 1,200 trials ~ $1-3, ~1.2 h at concurrency 4; honest 120 trials ~ $0.09.

## Open issues
- Git is not installed. Needed before any live attack trial (tags prereg-v1, prompts-v1) and for commits. Human: `winget install --id Git.Git -e`, then restart VS Code.
- OpenAI account has no credits (family 2, Tier 2 only). Human: add credits at platform.openai.com billing if the second family is wanted.
- The keys were in `.env.txt` (Notepad added .txt); renamed to `.env` (git-ignored) on 2026-11-06; values never displayed. .gitignore now also covers `.env.*`.
- GitHub CLI (gh) not installed (optional, C2).

## Decisions log (one line each)
- 2026-11-06 Use `py -3.13` for the venv (regular install) instead of the Microsoft Store Python 3.12 that `python` resolves to.
- 2026-11-06 SDKs pinned: anthropic 2.6.0 (no temperature argument; has output_config), openai 3.46.0 (chat.completions with response_format, max_completion_tokens, reasoning_effort).
- 2026-11-06 Pilot/oracle/mock/main data in separate folders from the start (no moving files later).
- 2026-11-06 Seed rule uses a per-experiment offset (no seed collisions across experiments); recorded in PREREGISTRATION.md before data.
- 2026-11-06 Verdict rules made operational before data (see docs/DEVIATIONS.md).
- 2026-11-06 Figures use the dataviz skill's validated default palette unchanged (sequential blue for ASR; categorical slots in fixed order with marker shapes as secondary encoding).
