# Bugs found and fixed (validation log)

One line each: symptom → root cause → fix → where. This list goes into the report as evidence of validation.

## Found while building (before the pilot, mock LLM only)

1. Forest plot crashed with "xerr must not contain negative values" → for k = n the Wilson upper bound came out as 0.9999999… (float rounding), giving a negative error-bar length → bounds set exactly to 0 (k = 0) and 1 (k = n) → `stats.wilson`.
2. The D2 benchmark showed 300+ µs per verify → the nonce cache was rescanned on every verification (O(cache size)) → amortised purge, plus an expiry check on lookup (behaviour unchanged; all tests pass) → `defences/d2_signed.py`.
3. The runbook's expected Wilson interval for 15/30 was [0.3313, 0.6687] → miscalculated by hand → corrected to [0.3315, 0.6685] and the test cross-checks statsmodels → `RUNBOOK.md` 8.5, `tests/test_stats.py`.
4. The pre-registered verdict rule could not mark H4 "supported" when D1 already stops A1-guess and A2-slow (0/30 vs 0/30 is never significant) → rule underspecified → "already stopped" case defined before any data → `PREREGISTRATION.md` §10.4, `docs/DEVIATIONS.md`.
5. A test's scripted fake model returned unparsed JSON, so the step-limit test failed → test-helper bug, not harness → parse the scripted text → `tests/test_agents_mock.py`.
6. `make_report.py` crashed on `{VERIFY: …}` placeholders → they sat inside an f-string → plain string → `make_report.py`.

## Found in the pilot (live LLM)

(To be filled in Phase 5.)
