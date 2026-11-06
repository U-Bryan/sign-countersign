# Cost and time estimate

Measured from the pilot (`results/pilot/trials`). Cells without pilot data use the nearest measured cell, then a default of 6 calls at 1,000 input and 600 output tokens each.

| Tier / experiment | Trials | LLM calls | USD | Hours (at configured concurrency) | Share priced from pilot |
| --- | --- | --- | --- | --- | --- |
| T1 honest (family 1) | 120 | 720 | 0.09 | 0.1 | 100% |
| T1 core matrix (family 1) | 1200 | 7216 | 1.09 | 1.0 | 100% |
| T2 family 2 (honest + A5) | 480 | 2880 | 4.18 | 0.5 | 0% |
| T2 monitor ablations | 570 | 3329 | 0.50 | 0.4 | 0% |
| T3 E4 D1fix | 90 | 578 | 0.07 | 0.1 | 0% |
| T3 E5 salient account | 90 | 570 | 0.12 | 0.1 | 100% |
| T3 E6 effort | 180 | 1140 | 0.23 | 0.2 | 100% |
| **Total** | 2730 | 16432 | **6.27** | 2.3 | |

Budget: warning at $40, hard cap at $60 (config/experiment.toml).
