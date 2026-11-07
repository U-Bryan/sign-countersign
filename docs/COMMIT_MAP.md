# Commit map: IDs before and after the history rewrite

On 7 November 2026, before the repository was made public, its history was rewritten at the author's request to remove the author's personal email address (replaced with a GitHub no-reply address in every commit and tag) and a local folder path in `RUNBOOK.md` line 13 (replaced with `sign-countersign/`). The tool was git-filter-repo 2.47.0 with a mailmap and a literal text replacement.

Rewriting changes every commit ID. IDs recorded before the rewrite therefore no longer exist in this repository. They appear in `results/results.csv` and `results/trials/*.json` (`git_sha`, the code version each trial ran on), `results/run_manifest.json`, the provenance footer of `report/RESULTS.md`, and `PROGRESS.md`. This table maps each old ID to its new one.

**What changed.** Each rewritten commit was compared file by file with its original (from a backup of the old history): in every commit the only file whose content differs is `RUNBOOK.md`, at line 13. Every other file, including all code, data, logs, `PREREGISTRATION.md` and `prompts/`, is byte-identical. The tags `prereg-v1`, `prompts-v1` and `main-run-complete` were moved to the rewritten commits.

The `git_sha` recorded in `results/results.csv` is old commit `459bc7c` (new `1d8f78f`) for 2,250 trials (honest, core, ablations, E4–E6) and old commit `f06c3d3` (new `3538744`) for the 480 family-2 trials.

| Old ID | New ID | Date | Tags | Commit message (first line) |
| --- | --- | --- | --- | --- |
| `1a33581` | `f6b2388` | 2026-11-06 | `prereg-v1`, `prompts-v1` | phase-0..4 (offline): harness, defences D0-D3 + ablations, attacks A1-A5, 539 offline tests, oracle matrix, honest pilot (40/40); prereg and prompts frozen |
| `459bc7c` | `1d8f78f` | 2026-11-06 |  | phase-4/5: live D0 check, C-3 A5 ladder (0/59, model resistance), full T1 pilot (210 trials, audit 100%), pilot audit notes, cost estimate; fix filter-dependent seeds |
| `f06c3d3` | `3538744` | 2026-11-06 |  | family 2 enabled (OpenAI credits): model check, honest pilot 10/10, family2 pilot (A5 3/3 under D0-D2, 0/3 under D3 via R1); concurrent-safe CSV writes; vacuous-verdict note and model-resistance headline branch |
| `296c15a` | `2812455` | 2026-11-06 | `main-run-complete` | phase-6: main runs complete - 2,730 trials (honest 120, core 1,200, family2 480, ablations 570, E4 90, E5 90, E6 180), 0 errors, audit 100%, total spend $4.01 |
| `b29e7e8` | `39146d3` | 2026-11-06 |  | phase-7/8: analysis (27 tables, 16 figures, deterministic), report, excerpts, docs, A2A checklist, handoff checklist |
| `5a76233` | `6d78fd7` | 2026-11-06 |  | final QA: fresh-clone reproduction identical (30 tables + values.json) |
| `7fa7e02` | `9520bca` | 2026-11-07 |  | make_report: render bench.csv in RESULTS.md; checklist item 7 cites A4-lie and family-2 A5 |
| `f3f772a` | `45da7be` | 2026-11-07 |  | analysis: ablation ASR table (table2d) with Wilson intervals; RESULTS.md shows it and Table E2 |
| `4802350` | `d8ec96b` | 2026-11-07 |  | report writing: REPORT_BRIEF.md and the upload-pack builder |
| `d003a46` | `c4eda75` | 2026-11-07 |  | Pre-publication fixes: licences, citation, README, verified references |

Full 40-character IDs, old then new:

```
1a33581734b48fe99277e3975ff75904b6a10868 f6b2388ac82ea3afb41b94b1d24df293011f0036
296c15a7300ee92704d765f9bb7ed3c6dc610bde 28124551b9ad22a29566a0797b94b9128305aa62
459bc7ca3490d13c78cfe1555f72f2148cb7ebec 1d8f78f35e61a33032bd028675880c2ec6c03228
480235032ac9fa9ea17a1d725c61a299b619abb3 d8ec96b6598edb6e4e8f14d7da0e93275df44725
5a76233deec343a64dbf0079d1676b43c84bbfde 6d78fd7c72927436f1196c225f7a99824eed1856
7fa7e0221c537474c29c126e22325bfe51074936 9520bca1b0c8e53f443c9cad31ed47af8304fcc3
b29e7e805c1095d0d7f88d4b32849564486f5a42 39146d38cfb55170c58f7a6083ff70a573f9eb0e
d003a46a3970946fc118d36cd0a75357179763e6 c4eda75e5ccb65b5d20f7cb42029424ff9a3948c
f06c3d315c3cd46d4087c3c5c60baa9f5feabc96 35387440bc21016352ff0a4a49b117c331ce7a0d
f3f772a1ce66bacb5228f26bdce2c50e8ee37cf7 45da7be2108435d1a0d0e5fc9476234842a83255
```
